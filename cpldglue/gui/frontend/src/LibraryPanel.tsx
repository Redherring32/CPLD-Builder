import { useMemo, useState } from "react";
import type { Part } from "./types";

export const PART_MIME = "application/x-cpldglue-part";

export function LibraryPanel({ parts, onAdd }: {
  parts: Part[]; onAdd: (key: string) => void;
}) {
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return parts;
    return parts.filter((p) => p.key.toLowerCase().includes(s) ||
                               p.title.toLowerCase().includes(s));
  }, [parts, q]);

  return (
    <aside className="library" aria-label="Part library">
      <input
        className="search" type="search" placeholder="Search parts (139, latch…)"
        value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search parts"
      />
      <div className="hint muted small">Drag onto the canvas, or double-click to add.</div>
      <ul className="partlist">
        {shown.map((p) => (
          <li key={p.key}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(PART_MIME, p.key);
                e.dataTransfer.effectAllowed = "copy";
              }}
              onDoubleClick={() => onAdd(p.key)}
              onKeyDown={(e) => { if (e.key === "Enter") onAdd(p.key); }}
              tabIndex={0}
              title={`${p.title} (${p.package})${p.warning ? `\n⚠ ${p.warning}` : ""}`}
              data-testid={`part-${p.key}`}>
            <span className="pkey">{p.key}</span>
            <span className="ptitle">{p.title}</span>
            {p.warning && <span className="pwarn" aria-label="has a warning">!</span>}
          </li>
        ))}
        {!shown.length && <li className="muted small">No match</li>}
      </ul>
    </aside>
  );
}
