/** Macrocell usage: one thin segmented bar (a segment per chip, the rest of
 *  the device as the track) plus a list giving each chip's share. Colors
 *  follow the chip (its place in the project), never its size, and fold
 *  into "Other" past eight chips. */
import type { Design, GenResult } from "./types";

export const SLOTS = 8;

/** Color slot (1..8) of each chip, or 0 for "Other". A chip keeps the slot
 *  it had in `prev` (so deleting or adding chips never repaints the others);
 *  new chips take the lowest free slot, in project order. */
export function chipSlots(design: Design, prev: Record<string, number> = {}): Record<string, number> {
  const out: Record<string, number> = {};
  const taken = new Set<number>();
  for (const ref of Object.keys(design.parts))
    if (prev[ref]) { out[ref] = prev[ref]; taken.add(prev[ref]); }
  for (const ref of Object.keys(design.parts)) {
    if (out[ref] !== undefined) continue;
    let s = 1;
    while (s <= SLOTS && taken.has(s)) s++;
    out[ref] = s <= SLOTS ? s : 0;
    if (out[ref]) taken.add(s);
  }
  return out;
}

export function slotColor(slot: number): string {
  return slot ? `var(--series-${slot})` : "var(--series-other)";
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

export function MacrocellBar({ design, gen, slots }: {
  design: Design; gen: GenResult | null; slots: Record<string, number>;
}) {
  const mc = gen?.macrocells;
  if (!mc || !mc.parts) return null;
  const total = mc.total;
  const used = mc.estimate;
  const scale = Math.max(total ?? 0, used, 1);
  const over = total !== null && used > total;

  // One row per chip, in project order; chips past slot 8 fold into "Other".
  const rows = Object.keys(design.parts).filter((ref) => mc.parts[ref]).map((ref) => ({
    ref, key: design.parts[ref], slot: slots[ref], ...mc.parts[ref],
  }));
  const other = rows.filter((r) => r.slot === 0);
  const segs = [
    ...rows.filter((r) => r.slot > 0 && r.estimate > 0)
      .map((r) => ({ id: r.ref, label: `${r.ref} (${r.key})`, value: r.estimate, slot: r.slot })),
    ...(other.length && other.some((r) => r.estimate > 0)
      ? [{ id: "other", label: `Other (${other.map((r) => r.ref).join(", ")})`,
           value: other.reduce((s, r) => s + r.estimate, 0), slot: 0 }]
      : []),
  ];
  const free = total !== null ? Math.max(0, total - used) : 0;
  const summary = `Macrocells: about ${fmt(used)}${total !== null ? ` of ${total}` : ""} used` +
    segs.map((s) => `; ${s.label} ${fmt(s.value)}`).join("");

  return (
    <div className="mcbar" data-testid="mcbar">
      <div className="mcbar-head">
        <span className="mcbar-title">Macrocells</span>
        <span className="mcbar-value">
          ≈{fmt(used)}{total !== null ? ` / ${total}` : ""}
          {total !== null && <span className="muted"> ({Math.round((used / total) * 100)}%)</span>}
        </span>
        {over && <span className="mcbar-over" role="status">⚠ over by {fmt(used - total!)}</span>}
      </div>
      <div className="mcbar-track" role="img" aria-label={summary}>
        {segs.map((s) => (
          <span key={s.id} className="mcbar-seg" tabIndex={0}
                style={{ flexGrow: s.value / scale, background: slotColor(s.slot) }}
                title={`${s.label}: ≈${fmt(s.value)} macrocells (${Math.round((s.value / scale) * 100)}%)`}
                aria-label={`${s.label}: about ${fmt(s.value)} macrocells`} />
        ))}
        {free > 0 && <span className="mcbar-free" style={{ flexGrow: free / scale }}
                           title={`Free: ${fmt(free)} macrocells`} />}
      </div>
      <table className="mcbar-table small">
        <tbody>
          {rows.map((r) => (
            <tr key={r.ref} className={r.estimate === 0 ? "muted" : ""}>
              <td><span className="mcbar-swatch" style={{ background: slotColor(r.slot) }} /></td>
              <td className="mono">{r.ref}</td>
              <td className="muted">{r.key}</td>
              <td className="num">{fmt(r.estimate)}</td>
              <td className="muted why">
                {r.estimate === 0 ? "unused or internal only" : [
                  r.outputs ? `${fmt(r.outputs)} output pin${r.outputs === 1 ? "" : "s"}` +
                    (Number.isInteger(r.outputs) ? "" : " (bus pins shared with other chips)") : "",
                  r.storage - r.shared ? `${r.storage - r.shared} buried flip-flop${r.storage - r.shared === 1 ? "" : "s"}` : "",
                  r.shared ? `${r.shared} at ${r.shared === 1 ? "its pin" : "their pins"}` : "",
                ].filter(Boolean).join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small mcbar-note">
        Estimate: one per output pin plus one per flip-flop or latch that doesn't
        sit at its own pin. Gate logic folds into the product terms. The fitter
        report has the real figure.
      </p>
    </div>
  );
}
