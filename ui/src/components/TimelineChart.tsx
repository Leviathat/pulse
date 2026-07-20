import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TimelinePoint } from "../types";

export function TimelineChart({ points }: { points: TimelinePoint[] }) {
  const data = points.map((p) => ({
    label: new Date(p.time).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
    }),
    count: p.count,
  }));

  if (!data.length) {
    return <p className="empty">No mentions in this window.</p>;
  }

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#8b93a7" }} minTickGap={24} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#8b93a7" }} />
          <Tooltip
            contentStyle={{ background: "#12151c", border: "1px solid #2a2f3a" }}
            labelStyle={{ color: "#c8cede" }}
          />
          <Bar dataKey="count" fill="#5b8cff" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
