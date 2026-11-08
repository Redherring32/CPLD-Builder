/** Variants: boards where you fit one of several chips (a 74x377 *or* a
 *  74x161...). Each variant lists the optional chips fitted in it; chips in
 *  no variant are always fitted. Either build one design per variant (same
 *  pins in each), or put every variant in the CPLD and choose with VAR_SEL
 *  pins on the board. */
import { useEffect, useState } from "react";
import type { Design } from "./types";

type Row = { name: string; refs: Set<string> };

function natural(a: string, b: string) {
  return a.localeCompare(b, undefined, { numeric: true });
}

export function VariantsDialog({ design, onApply, onClose }: {
  design: Design;
  onApply: (variants: Record<string, string[]>, mode: "build" | "pins") => void;
  onClose: () => void;
}) {
  const [rows, setRows] = useState<Row[]>(() =>
    Object.entries(design.variants ?? {}).map(([name, refs]) => ({ name, refs: new Set(refs) })));
  const [mode, setMode] = useState<"build" | "pins">(design.variant_mode ?? "build");
  const [error, setError] = useState("");
  const chips = Object.keys(design.parts).sort(natural);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  const nsel = Math.max(1, Math.ceil(Math.log2(Math.max(2, rows.length))));
  const code = (i: number) =>
    Array.from({ length: nsel }, (_, k) => (i >> (nsel - 1 - k)) & 1).join("");

  const toggle = (vi: number, ref: string) => setRows((rs) => rs.map((r, i) => {
    if (i !== vi) return r;
    const refs = new Set(r.refs);
    if (refs.has(ref)) refs.delete(ref); else refs.add(ref);
    return { ...r, refs };
  }));
  const add = () => setRows((rs) => {
    let n = rs.length + 1;
    while (rs.some((r) => r.name === `Variant ${n}`)) n++;
    return [...rs, { name: `Variant ${n}`, refs: new Set() }];
  });

  const apply = () => {
    const names = rows.map((r) => r.name.trim());
    if (names.some((n) => !n)) return setError("Every variant needs a name.");
    if (new Set(names).size !== names.length) return setError("Variant names must differ.");
    if (rows.length === 1) return setError("Add at least two variants (or remove them all).");
    onApply(Object.fromEntries(rows.map((r) => [r.name.trim(), chips.filter((c) => r.refs.has(c))])), mode);
  };

  const optional = new Set(rows.flatMap((r) => [...r.refs]));

  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal variants" role="dialog" aria-modal="true" aria-label="Variants">
        <div className="modal-head">
          <h2>Variants</h2>
          <button className="iconbtn" onClick={onClose} aria-label="Close">×</button>
        </div>
        <p className="small muted">
          For boards where you fit one of several chips. Tick the chips each variant fits;
          a chip ticked in no variant is always fitted.
        </p>
        <div className="row small variant-mode" role="radiogroup" aria-label="How variants are chosen">
          <label><input type="radio" checked={mode === "build"} onChange={() => setMode("build")} />
            {" "}<b>One build per variant</b> <span className="muted">— program the .jed for the board; same pins in each</span></label>
          <label><input type="radio" checked={mode === "pins"} onChange={() => setMode("pins")} />
            {" "}<b>Select pins</b> <span className="muted">— every variant in the CPLD, chosen by {nsel} VAR_SEL pin{nsel > 1 ? "s" : ""} (jumpers to GND/VCC)</span></label>
        </div>
        <div className="comp-table">
          <table className="variant-grid">
            <thead>
              <tr>
                <th>Chip</th>
                {rows.map((r, i) => (
                  <th key={i}>
                    <input className="mono" value={r.name} aria-label={`Variant ${i + 1} name`}
                           onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
                    <button className="iconbtn" aria-label={`Remove ${r.name}`} title="Remove this variant"
                            onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>×</button>
                    {mode === "pins" && <div className="muted small">VAR_SEL = {code(i)}</div>}
                  </th>
                ))}
                <th><button onClick={add}>+ Variant</button></th>
              </tr>
            </thead>
            <tbody>
              {chips.map((c) => (
                <tr key={c} className={optional.has(c) ? "" : "muted"}>
                  <td className="mono">{c} <span className="small muted">{design.parts[c]}</span></td>
                  {rows.map((r, i) => (
                    <td key={i} className="center">
                      <input type="checkbox" checked={r.refs.has(c)} onChange={() => toggle(i, c)}
                             aria-label={`${c} fitted in ${r.name}`} />
                    </td>
                  ))}
                  <td className="small muted">{optional.has(c) ? "" : "always fitted"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {error && <div className="msg error small">{error}</div>}
        <div className="modal-foot">
          {rows.length > 0 && <button onClick={() => setRows([])}>Remove all variants</button>}
          <span className="spacer" />
          <button onClick={onClose}>Cancel</button>
          <button className="primary" onClick={apply}>Apply</button>
        </div>
      </div>
    </div>
  );
}
