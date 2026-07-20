// Package poller drives the fetch → normalize → produce loop for Hacker News.
package poller

import (
	"context"
	"log/slog"
	"sort"
	"sync"
	"time"

	"pulse/ingestor/internal/event"
	"pulse/ingestor/internal/hn"
	"pulse/ingestor/internal/metrics"
)

// Fetcher is the slice of the HN client the poller needs (satisfied by *hn.Client).
type Fetcher interface {
	NewStories(ctx context.Context) ([]int64, error)
	Item(ctx context.Context, id int64) (hn.Item, error)
}

// Publisher writes a normalized article somewhere durable (satisfied by *producer.Producer).
type Publisher interface {
	Publish(ctx context.Context, a event.Article) error
}

// Config tunes the poll loop.
type Config struct {
	Interval    time.Duration // wait between poll cycles
	MaxPerPoll  int           // cap on newest ids considered per cycle
	FetchWorker int           // concurrent item fetches
}

// Poller polls Hacker News for new stories and publishes them exactly once.
type Poller struct {
	cfg     Config
	fetcher Fetcher
	pub     Publisher

	// maxSeen is the highest item id already handled. HN ids increase
	// monotonically, so we only process ids greater than it — no unbounded
	// "seen" set, and the first cycle backfills the current newest batch.
	maxSeen int64
}

// New constructs a Poller with defaults filled in for any zero Config field.
func New(cfg Config, fetcher Fetcher, pub Publisher) *Poller {
	if cfg.Interval <= 0 {
		cfg.Interval = 15 * time.Second
	}
	if cfg.MaxPerPoll <= 0 {
		cfg.MaxPerPoll = 60
	}
	if cfg.FetchWorker <= 0 {
		cfg.FetchWorker = 8
	}
	return &Poller{cfg: cfg, fetcher: fetcher, pub: pub}
}

// Run polls until ctx is cancelled.
func (p *Poller) Run(ctx context.Context) {
	ticker := time.NewTicker(p.cfg.Interval)
	defer ticker.Stop()

	p.pollOnce(ctx) // fire immediately, don't wait a full interval
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			p.pollOnce(ctx)
		}
	}
}

func (p *Poller) pollOnce(ctx context.Context) {
	ids, err := p.fetcher.NewStories(ctx)
	if err != nil {
		metrics.SourceErrors.WithLabelValues(event.SourceHackerNews, "newstories").Inc()
		slog.Error("fetch newstories", "error", err)
		return
	}

	fresh := p.selectFresh(ids)
	if len(fresh) > 0 {
		p.fetchAndPublish(ctx, fresh)
	}
	metrics.LastPollUnix.Set(float64(time.Now().Unix()))
}

// selectFresh keeps only ids newer than maxSeen, capped and processed oldest
// first so maxSeen advances monotonically. It also updates maxSeen.
func (p *Poller) selectFresh(ids []int64) []int64 {
	fresh := make([]int64, 0, len(ids))
	for _, id := range ids {
		if id > p.maxSeen {
			fresh = append(fresh, id)
		}
	}
	sort.Slice(fresh, func(i, j int) bool { return fresh[i] < fresh[j] })
	if len(fresh) > p.cfg.MaxPerPoll {
		// Keep the newest MaxPerPoll ids (the tail, since sorted ascending).
		fresh = fresh[len(fresh)-p.cfg.MaxPerPoll:]
	}
	if len(fresh) > 0 {
		p.maxSeen = fresh[len(fresh)-1]
	}
	return fresh
}

func (p *Poller) fetchAndPublish(ctx context.Context, ids []int64) {
	sem := make(chan struct{}, p.cfg.FetchWorker)
	var wg sync.WaitGroup
	for _, id := range ids {
		wg.Add(1)
		sem <- struct{}{}
		go func(id int64) {
			defer wg.Done()
			defer func() { <-sem }()
			p.handle(ctx, id)
		}(id)
	}
	wg.Wait()
}

func (p *Poller) handle(ctx context.Context, id int64) {
	item, err := p.fetcher.Item(ctx, id)
	if err != nil {
		metrics.SourceErrors.WithLabelValues(event.SourceHackerNews, "item").Inc()
		slog.Warn("fetch item", "id", id, "error", err)
		return
	}
	article, ok := event.FromHNItem(item, time.Now())
	if !ok {
		metrics.ItemsSkipped.Inc()
		return
	}
	if err := p.pub.Publish(ctx, article); err != nil {
		metrics.SourceErrors.WithLabelValues(event.SourceHackerNews, "publish").Inc()
		slog.Error("publish", "id", id, "error", err)
		return
	}
	metrics.ArticlesProduced.WithLabelValues(event.SourceHackerNews).Inc()
	slog.Debug("published", "id", id, "title", article.Title)
}
