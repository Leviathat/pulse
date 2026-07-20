// Package event defines the normalized article event published to Kafka and
// the pure functions that map source-specific payloads onto it.
package event

import (
	"fmt"
	"html"
	"strings"
	"time"

	"pulse/ingestor/internal/hn"
)

// SourceHackerNews is the canonical source name for Hacker News items.
const SourceHackerNews = "hackernews"

// Article is the normalized event written to the raw_articles topic.
// The JSON shape is the contract with the Python processor (see pulse-tz.md 4.1).
type Article struct {
	Source      string    `json:"source"`
	SourceID    string    `json:"source_id"`
	URL         string    `json:"url"`
	Title       string    `json:"title"`
	Body        string    `json:"body"`
	Author      string    `json:"author"`
	PublishedAt time.Time `json:"published_at"`
	FetchedAt   time.Time `json:"fetched_at"`
}

// FromHNItem maps a Hacker News item onto an Article. The bool reports whether
// the item is worth publishing: deleted/dead items and non-stories (comments,
// polls without a title) are dropped. It is pure so it can be unit-tested
// without touching the network.
func FromHNItem(item hn.Item, fetchedAt time.Time) (Article, bool) {
	if item.Deleted || item.Dead {
		return Article{}, false
	}
	// Only stories and job posts carry a title/URL worth indexing.
	if item.Type != "story" && item.Type != "job" {
		return Article{}, false
	}
	title := strings.TrimSpace(html.UnescapeString(item.Title))
	if title == "" {
		return Article{}, false
	}

	url := strings.TrimSpace(item.URL)
	if url == "" {
		// Text posts (Ask/Show HN) have no external URL; link to the HN thread.
		url = fmt.Sprintf("https://news.ycombinator.com/item?id=%d", item.ID)
	}

	return Article{
		Source:      SourceHackerNews,
		SourceID:    fmt.Sprintf("%d", item.ID),
		URL:         url,
		Title:       title,
		Body:        strings.TrimSpace(html.UnescapeString(item.Text)),
		Author:      item.By,
		PublishedAt: time.Unix(item.Time, 0).UTC(),
		FetchedAt:   fetchedAt.UTC(),
	}, true
}
