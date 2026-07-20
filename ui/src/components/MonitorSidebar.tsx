import { useState, type FormEvent } from "react";
import {
  useCreateMonitorMutation,
  useDeleteMonitorMutation,
  useGetMonitorsQuery,
} from "../api";

export function MonitorSidebar({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { data: monitors = [], isLoading } = useGetMonitorsQuery();
  const [createMonitor, { isLoading: creating }] = useCreateMonitorMutation();
  const [deleteMonitor] = useDeleteMonitorMutation();

  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const kw = keywords.split(",").map((k) => k.trim()).filter(Boolean);
    if (!name.trim() || !kw.length) return;
    const created = await createMonitor({ name: name.trim(), keywords: kw }).unwrap();
    setName("");
    setKeywords("");
    onSelect(created.id);
  }

  return (
    <aside className="sidebar">
      <form className="create" onSubmit={submit}>
        <h2>New monitor</h2>
        <input
          placeholder="Name (e.g. Tech watch)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          placeholder="Keywords, comma-separated"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
        <button type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create monitor"}
        </button>
      </form>

      <h2>Monitors</h2>
      {isLoading && <p className="empty">Loading…</p>}
      {!isLoading && !monitors.length && <p className="empty">No monitors yet.</p>}
      <ul className="monitor-list">
        {monitors.map((m) => (
          <li
            key={m.id}
            className={m.id === selectedId ? "monitor active" : "monitor"}
            onClick={() => onSelect(m.id)}
          >
            <div className="monitor-name">{m.name}</div>
            <div className="monitor-kw">{m.keywords.join(", ")}</div>
            <button
              className="delete"
              title="Delete monitor"
              onClick={(e) => {
                e.stopPropagation();
                deleteMonitor(m.id);
              }}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
