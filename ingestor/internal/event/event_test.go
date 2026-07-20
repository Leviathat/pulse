package event

import (
	"testing"
	"time"

	"pulse/ingestor/internal/hn"
)

func TestFromHNItem_Story(t *testing.T) {
	fetched := time.Date(2026, 7, 3, 10, 0, 5, 0, time.UTC)
	item := hn.Item{
		ID:    38912345,
		Type:  "story",
		By:    "pg",
		Time:  1720000000,
		Title: "Show HN: Pulse &amp; friends",
		URL:   "https://example.com/x",
		Text:  "hello &lt;b&gt;",
	}

	got, ok := FromHNItem(item, fetched)
	if !ok {
		t.Fatal("expected item to be published")
	}
	if got.Source != SourceHackerNews {
		t.Errorf("source = %q", got.Source)
	}
	if got.SourceID != "38912345" {
		t.Errorf("source_id = %q", got.SourceID)
	}
	if got.Title != "Show HN: Pulse & friends" {
		t.Errorf("title not unescaped/trimmed: %q", got.Title)
	}
	if got.Body != "hello <b>" {
		t.Errorf("body not unescaped: %q", got.Body)
	}
	if got.URL != "https://example.com/x" {
		t.Errorf("url = %q", got.URL)
	}
	if !got.PublishedAt.Equal(time.Unix(1720000000, 0).UTC()) {
		t.Errorf("published_at = %v", got.PublishedAt)
	}
	if !got.FetchedAt.Equal(fetched) {
		t.Errorf("fetched_at = %v", got.FetchedAt)
	}
}

func TestFromHNItem_TextPostFallsBackToThreadURL(t *testing.T) {
	item := hn.Item{ID: 42, Type: "story", Title: "Ask HN: anything?"}
	got, ok := FromHNItem(item, time.Now())
	if !ok {
		t.Fatal("expected published")
	}
	if got.URL != "https://news.ycombinator.com/item?id=42" {
		t.Errorf("expected HN thread url, got %q", got.URL)
	}
}

func TestFromHNItem_Dropped(t *testing.T) {
	cases := map[string]hn.Item{
		"deleted":  {ID: 1, Type: "story", Title: "x", Deleted: true},
		"dead":     {ID: 2, Type: "story", Title: "x", Dead: true},
		"comment":  {ID: 3, Type: "comment", Text: "reply"},
		"no title": {ID: 4, Type: "story", Title: "   "},
	}
	for name, item := range cases {
		t.Run(name, func(t *testing.T) {
			if _, ok := FromHNItem(item, time.Now()); ok {
				t.Errorf("expected %s item to be dropped", name)
			}
		})
	}
}
