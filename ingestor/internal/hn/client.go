// Package hn is a thin client for the public Hacker News Firebase API.
// https://github.com/HackerNews/API — no auth, JSON over HTTPS.
package hn

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

const defaultBaseURL = "https://hacker-news.firebaseio.com/v0"

// Item is the subset of a Hacker News item we care about. Unused fields
// (kids, score, descendants, …) are ignored by the JSON decoder.
type Item struct {
	ID      int64  `json:"id"`
	Type    string `json:"type"`
	By      string `json:"by"`
	Time    int64  `json:"time"` // unix seconds
	Title   string `json:"title"`
	URL     string `json:"url"`
	Text    string `json:"text"`
	Dead    bool   `json:"dead"`
	Deleted bool   `json:"deleted"`
}

// Client fetches new-story ids and individual items.
type Client struct {
	baseURL string
	http    *http.Client
}

// NewClient returns a Client with a sane timeout on the underlying transport.
func NewClient() *Client {
	return &Client{
		baseURL: defaultBaseURL,
		http:    &http.Client{Timeout: 10 * time.Second},
	}
}

// NewStories returns the ids of the newest stories, newest first (up to ~500).
func (c *Client) NewStories(ctx context.Context) ([]int64, error) {
	var ids []int64
	if err := c.getJSON(ctx, c.baseURL+"/newstories.json", &ids); err != nil {
		return nil, fmt.Errorf("newstories: %w", err)
	}
	return ids, nil
}

// Item fetches a single item by id.
func (c *Client) Item(ctx context.Context, id int64) (Item, error) {
	var it Item
	url := fmt.Sprintf("%s/item/%d.json", c.baseURL, id)
	if err := c.getJSON(ctx, url, &it); err != nil {
		return Item{}, fmt.Errorf("item %d: %w", id, err)
	}
	return it, nil
}

func (c *Client) getJSON(ctx context.Context, url string, dst any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status %d", resp.StatusCode)
	}
	return json.NewDecoder(resp.Body).Decode(dst)
}
