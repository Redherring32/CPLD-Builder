import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api";
import type { KiComponent, KiPreview } from "./api";
import type { Design, Part } from "./types";

/** Pick chips from a KiCad schematic and replace the project's chips with them. */
export function ImportDialog({ design, parts, onImport, onClose }: {
  design: Design; parts: Part[];
  onImport: (d: Design) => void; onClose: () => void;
}) {
  const [path, setPath] = useState("");
  const [found, setFound] = useState<string[]>([]);
  const [comps, setComps] = useState<KiComponent[] | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<KiPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [onlyLogic, setOnlyLogic] = useState(true);
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.kicadFind().then((f) => { setFound(f); if (f.length && !path) setPath(f[0]); })
      .catch(() => {});
    dialog.current?.querySelector<HTMLInputElement>("input")?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = async () => {
    setLoading(true); setError(""); setComps(null); setPreview(null);
    try {
      const r = await api.kicadComponents(path.trim().replace(/^"|"$/g, ""));
      setPath(r.path);
      setComps(r.components);
      // Tick every logic chip the library knows (the pin count then shows
      // whether they all fit), except alternatives: of chips that drive the
      // same nets, only the first is ticked.
      const skip = new Set((r.alternatives ?? []).flatMap((g) => g.refs.slice(1)));
      setPicked(new Set(r.components.filter((c) => c.part && !skip.has(c.ref)).map((c) => c.ref)));
      setAlts(r.alternatives ?? []);
      setKept(new Set());
      setOverrides({});
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const refs = useMemo(() => [...picked].sort(), [picked]);
  const [alts, setAlts] = useState<api.KiAlternatives[]>([]);
  // Alternatives groups kept as variants instead of picking one chip.
  const [kept, setKept] = useState<Set<number>>(new Set());
  const variants = useMemo(() => {
    const groups = alts.filter((_, i) => kept.has(i))
      .map((g) => g.refs.filter((r) => picked.has(r))).filter((g) => g.length > 1);
    if (!groups.length) return undefined;
    // every combination of one chip per group (capped at 8 variants)
    let combos: string[][] = [[]];
    for (const g of groups) combos = combos.flatMap((c) => g.map((r) => [...c, r]));
    const value = (r: string) => comps?.find((c) => c.ref === r)?.value ?? "";
    return Object.fromEntries(combos.slice(0, 8).map((c) =>
      [c.map((r) => `${r} ${value(r)}`.trim()).join(" + "), c]));
  }, [alts, kept, picked, comps]);

  // Live preview of the pin count as chips are ticked.
  useEffect(() => {
    if (!comps) return;
    if (!refs.length) { setPreview(null); return; }
    let stale = false;
    const t = setTimeout(() => {
      api.kicadPreview(path, refs, overrides, design, variants)
        .then((p) => { if (!stale) { setPreview(p); setError(""); } })
        .catch((e) => { if (!stale) { setPreview(null); setError(String(e.message ?? e)); } });
    }, 200);
    return () => { stale = true; clearTimeout(t); };
  }, [comps, refs, overrides, path, design, variants]);

  const toggle = (ref: string) => setPicked((s) => {
    const n = new Set(s);
    if (n.has(ref)) n.delete(ref); else n.add(ref);
    return n;
  });

  const shown = (comps ?? []).filter((c) => !onlyLogic || c.part || overrides[c.ref] ||
                                           /^U\d/i.test(c.ref));
  const over = preview && preview.capacity !== null && preview.pins > preview.capacity;

  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Import from KiCad" ref={dialog}>
        <div className="modal-head">
          <h2>Import chips from KiCad</h2>
          <button className="iconbtn" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="row">
          <input className="grow mono" list="kicad-files" value={path} aria-label="Schematic path"
                 placeholder="C:\path\to\board.kicad_sch"
                 onChange={(e) => setPath(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") load(); }} />
          <datalist id="kicad-files">{found.map((f) => <option key={f} value={f} />)}</datalist>
          <button className="primary" onClick={load} disabled={!path.trim() || loading}>
            {loading ? "Reading…" : "Load"}
          </button>
        </div>
        {!comps && !loading && (
          <p className="muted small">
            {found.length ? `Found ${found.length} schematic(s) near the project; pick one or paste a path.`
                          : "Paste the path of a .kicad_sch file (KiCad 7+ must be installed)."}
          </p>
        )}
        {error && <div className="msg error small">{error}</div>}

        {comps && (
          <>
            <div className="row small">
              <label><input type="checkbox" checked={onlyLogic}
                            onChange={(e) => setOnlyLogic(e.target.checked)} /> Only show chips</label>
              <span className="spacer" />
              <span>{refs.length} selected</span>
              {preview && (
                <span className={`pincount${over ? " over" : ""}`} data-testid="import-pins">
                  {preview.pins}{preview.capacity !== null ? ` / ${preview.capacity}` : ""} pins on {design.device} {design.package}
                </span>
              )}
            </div>
            {alts.map((g, i) => (
              <div key={g.refs.join()} className="msg note small" data-testid="import-alts">
                {g.refs.join(", ")} drive the same nets ({g.nets.slice(0, 3).join(", ")}
                {g.nets.length > 3 ? ", …" : ""}), so they look like alternatives for one place
                on the board.{" "}
                {kept.has(i)
                  ? <>All are kept as variants: the CPLD covers each one (see <b>Variants…</b> after importing).</>
                  : <>Only {g.refs[0]} is ticked; tick the one you fit instead, or keep them all as variants.</>}
                {" "}<button className="linkbtn" onClick={() => {
                  const next = new Set(kept);
                  if (next.has(i)) {
                    next.delete(i);
                    setPicked((s) => { const n = new Set(s); g.refs.slice(1).forEach((r) => n.delete(r)); return n; });
                  } else {
                    next.add(i);
                    setPicked((s) => new Set([...s, ...g.refs]));
                  }
                  setKept(next);
                }}>{kept.has(i) ? "Pick one instead" : "Keep all as variants"}</button>
              </div>
            ))}
            <div className="comp-table">
              <table>
                <thead><tr><th></th><th>Ref</th><th>Value</th><th>Model</th></tr></thead>
                <tbody>
                  {shown.map((c) => {
                    const model = overrides[c.ref] || c.part;
                    return (
                      <tr key={c.ref} className={model ? "" : "nomodel"}>
                        <td><input type="checkbox" aria-label={`Include ${c.ref}`}
                                   checked={picked.has(c.ref)} disabled={!model}
                                   onChange={() => toggle(c.ref)} /></td>
                        <td className="mono">{c.ref}</td>
                        <td className="mono small">{c.value}
                          {c.alternatives && c.alternatives.length > 0 &&
                            <span className="muted"> · or {c.alternatives.join(" / ")}</span>}</td>
                        <td>
                          <select value={model ?? ""} aria-label={`Model for ${c.ref}`}
                                  onChange={(e) => {
                                    const v = e.target.value;
                                    setOverrides((o) => ({ ...o, [c.ref]: v }));
                                    if (v) setPicked((s) => new Set(s).add(c.ref));
                                  }}>
                            <option value="">{c.part ? c.part : "— none —"}</option>
                            {parts.map((p) => <option key={p.key} value={p.key}>{p.key} · {p.title}</option>)}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {preview && preview.errors.length > 0 && (
              <div className="msgs error"><ul>{preview.errors.map((m, i) => <li key={i}>{m}</li>)}</ul></div>
            )}
          </>
        )}

        <div className="modal-foot">
          <span className="muted small">Replaces the chips and nets in this project (Undo restores them).
            Name and device are kept.</span>
          <span className="spacer" />
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!preview || !refs.length}
                  onClick={() => preview && onImport(preview.design)}>
            Import {refs.length || ""} chip{refs.length === 1 ? "" : "s"}
          </button>
        </div>
      </div>
    </div>
  );
}
