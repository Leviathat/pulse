import type { Article } from "../types";
import { highlight } from "../lib/highlight";

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function ArticleList({
  articles,
  terms,
}: {
  articles: Article[];
  terms: string[];
}) {
  if (!articles.length) {
    return <p className="empty">No articles yet.</p>;
  }
  return (
    <ul className="feed">
      {articles.map((a) => (
        <li key={a.id} className="card">
          <a className="card-title" href={a.url} target="_blank" rel="noreferrer">
            {highlight(a.title, terms)}
          </a>
          <div className="card-meta">
            <span className="badge">{a.source}</span>
            {a.author && <span>by {a.author}</span>}
            <span>{timeAgo(a.published_at)}</span>
            {a.lang && a.lang !== "unknown" && <span className="lang">{a.lang}</span>}
          </div>
          {a.body && (
            <p className="card-body">{highlight(a.body.slice(0, 240), terms)}</p>
          )}
        </li>
      ))}
    </ul>
  );
}
