import { useEffect, useState, type FormEvent } from "react";
import {
  useGetFeedQuery,
  useGetMonitorsQuery,
  useGetTimelineQuery,
  useLazySearchQuery,
} from "./api";
import { ArticleList } from "./components/ArticleList";
import { MonitorSidebar } from "./components/MonitorSidebar";
import { TimelineChart } from "./components/TimelineChart";
import { skipToken } from "@reduxjs/toolkit/query";

export default function App() {
  const { data: monitors = [] } = useGetMonitorsQuery();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState(false);
  const [runSearch, searchState] = useLazySearchQuery();

  // Default to the first monitor once monitors load.
  useEffect(() => {
    if (!selectedId && monitors.length) setSelectedId(monitors[0].id);
  }, [monitors, selectedId]);

  const selected = monitors.find((m) => m.id === selectedId) ?? null;

  const feed = useGetFeedQuery(selectedId ? { id: selectedId } : skipToken);
  const timeline = useGetTimelineQuery(
    selectedId ? { id: selectedId, interval: "1h" } : skipToken,
  );

  function submitSearch(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearchMode(true);
    runSearch({ q: query.trim() });
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="dot" /> Pulse
        </div>
        <form className="search" onSubmit={submitSearch}>
          <input
            placeholder="Search the archive…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit">Search</button>
          {searchMode && (
            <button type="button" className="ghost" onClick={() => setSearchMode(false)}>
              Back to monitor
            </button>
          )}
        </form>
      </header>

      <div className="layout">
        <MonitorSidebar selectedId={selectedId} onSelect={(id) => {
          setSelectedId(id);
          setSearchMode(false);
        }} />

        <main className="main">
          {searchMode ? (
            <section>
              <h1>Search: “{query}”</h1>
              {searchState.isFetching && <p className="empty">Searching…</p>}
              {searchState.data && (
                <>
                  <p className="count">{searchState.data.total} results</p>
                  <ArticleList articles={searchState.data.results} terms={[query]} />
                </>
              )}
            </section>
          ) : selected ? (
            <section>
              <h1>{selected.name}</h1>
              <p className="count">
                {selected.keywords.map((k) => (
                  <span key={k} className="chip">{k}</span>
                ))}
              </p>
              <h3>Mentions over time{timeline.data?.cached ? " (cached)" : ""}</h3>
              <TimelineChart points={timeline.data?.points ?? []} />
              <h3>Feed{feed.data ? ` · ${feed.data.total} matched` : ""}</h3>
              <ArticleList
                articles={feed.data?.results ?? []}
                terms={selected.keywords}
              />
            </section>
          ) : (
            <p className="empty">Create a monitor to get started.</p>
          )}
        </main>
      </div>
    </div>
  );
}
