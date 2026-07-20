import type { ReactNode } from "react";

/** Wrap occurrences of any term in <mark>, case-insensitively, on word content. */
export function highlight(text: string, terms: string[]): ReactNode {
  const cleaned = terms.map((t) => t.trim()).filter(Boolean);
  if (!cleaned.length || !text) return text;
  const escaped = cleaned.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const splitter = new RegExp(`(${escaped.join("|")})`, "gi");
  const isMatch = new RegExp(`^(?:${escaped.join("|")})$`, "i");
  return text.split(splitter).map((part, i) =>
    isMatch.test(part) ? <mark key={i}>{part}</mark> : part,
  );
}
