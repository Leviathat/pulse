package poller

import (
	"context"
	"errors"
	"sync"
	"testing"

	"pulse/ingestor/internal/event"
	"pulse/ingestor/internal/hn"
)

type fakeFetcher struct {
	ids   []int64
	items map[int64]hn.Item
	err   error
}

func (f *fakeFetcher) NewStories(context.Context) ([]int64, error) {
	return f.ids, f.err
}

func (f *fakeFetcher) Item(_ context.Context, id int64) (hn.Item, error) {
	it, ok := f.items[id]
	if !ok {
		return hn.Item{}, errors.New("not found")
	}
	return it, nil
}

type fakePublisher struct {
	mu       sync.Mutex
	articles []event.Article
}

func (p *fakePublisher) Publish(_ context.Context, a event.Article) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.articles = append(p.articles, a)
	return nil
}

func TestSelectFresh_AdvancesWatermarkAndCaps(t *testing.T) {
	p := New(Config{MaxPerPoll: 2}, &fakeFetcher{}, &fakePublisher{})

	// Newest-first, as HN returns them.
	fresh := p.selectFresh([]int64{50, 40, 30, 20, 10})
	if len(fresh) != 2 || fresh[0] != 40 || fresh[1] != 50 {
		t.Fatalf("expected newest 2 ascending [40 50], got %v", fresh)
	}
	if p.maxSeen != 50 {
		t.Fatalf("maxSeen = %d, want 50", p.maxSeen)
	}
	// A second poll with nothing newer yields nothing.
	if again := p.selectFresh([]int64{50, 40}); len(again) != 0 {
		t.Fatalf("expected no fresh ids, got %v", again)
	}
}

func TestPollOnce_PublishesOnlyStories(t *testing.T) {
	f := &fakeFetcher{
		ids: []int64{3, 2, 1},
		items: map[int64]hn.Item{
			1: {ID: 1, Type: "story", Title: "keep me"},
			2: {ID: 2, Type: "comment", Text: "drop me"},
			3: {ID: 3, Type: "story", Title: "keep me too"},
		},
	}
	pub := &fakePublisher{}
	p := New(Config{}, f, pub)

	p.pollOnce(context.Background())

	if len(pub.articles) != 2 {
		t.Fatalf("expected 2 published, got %d", len(pub.articles))
	}
	if p.maxSeen != 3 {
		t.Fatalf("maxSeen = %d, want 3", p.maxSeen)
	}
}

func TestPollOnce_FetchErrorIsSwallowed(t *testing.T) {
	p := New(Config{}, &fakeFetcher{err: errors.New("boom")}, &fakePublisher{})
	p.pollOnce(context.Background()) // must not panic
	if p.maxSeen != 0 {
		t.Fatalf("maxSeen advanced on error: %d", p.maxSeen)
	}
}
