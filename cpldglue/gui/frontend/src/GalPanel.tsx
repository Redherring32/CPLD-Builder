/** GAL fit: places the design in the GAL16V8/22V10's output macrocells
 *  (Yosys + the cpldglue GAL fitter on the server) and shows each OLMC's
 *  product terms, the mode, the fitted pins and the fuse-map check. */
import { useEffect, useState } from "react";
import * as api from "./api";
import type { GalResult } from "./api";
import type { Design, DeviceInfo, GenResult } from "./types";

export function GalPanel({ design, device, gen, onSetLocks }: {
  design: Design; device: DeviceInfo; gen: GenResult | null;
  onSetLocks?: (locks: Record<string, number>) => void;
}) {
  const [res, setRes] = useState<GalResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [eqns, setEqns] = useState(false);

  useEffect(() => {
    if (!gen?.ok) { setRes(null); return; }
    let stale = false;
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await api.galFit(design);
        if (!stale) setRes(r);
      } catch (e) {
        if (!stale) setRes({ ok: false, error: String(e) } as GalResult);
      } finally {
        if (!stale) setBusy(false);
      }
    }, 600);
    return () => { stale = true; clearTimeout(t); };
  }, [design, gen?.ok, gen?.verilog]);

  // Ports whose fitted pin differs from the editor's (the editor doesn't know
  // the GAL's pin rules: clock on pin 1, /OE on pin 11, product-term sizes).
  const ports = new Set((gen?.ports ?? []).map((p) => p.name));
  const moved = res?.ok && res.fits
    ? (gen?.ports ?? []).filter((p) => res.pins[p.name] !== undefined && res.pins[p.name] !== p.pin)
    : [];
  const useFitted = () => {
    if (!res?.ok || !onSetLocks) return;
    const locks: Record<string, number> = { ...design.pin_locks };
    for (const [sig, pin] of Object.entries(res.pins)) if (ports.has(sig)) locks[sig] = pin;
    onSetLocks(locks);
  };
  const used = res?.cells.filter((c) => c.kind === "reg" || c.kind === "comb").length ?? 0;

  return (
    <div className="mcbar galbar" data-testid="galbar">
      <div className="mcbar-head">
        <span className="mcbar-title">Output macrocells</span>
        {res?.ok && res.fits && <span className="mcbar-count">{used} / {res.cells.length}</span>}
        <span className="muted small">{device.device} · GAL{res?.mode ? ` · ${res.mode} mode` : ""}</span>
        {busy && <span className="muted small">fitting…</span>}
        {res?.ok && (res.fits
          ? <span className="gp-ok">✓ fits</span>
          : <span className="mcbar-over" role="status">⚠ doesn't fit</span>)}
      </div>
      {!gen?.ok && <div className="muted small">Fix the report errors to fit the design.</div>}
      {res && !res.ok && (
        <div className="msg error small">{res.error}
          {/Yosys not found|could not run Yosys/.test(res.error ?? "") && <>
            {" "}<button className="linkbtn"
                         onClick={() => window.dispatchEvent(new Event("cpldglue:setup"))}>
              Open Setup</button></>}
        </div>
      )}
      {res?.ok && !res.fits && res.errors.map((e) => <div key={e} className="msg error small">{e}</div>)}
      {res?.ok && res.fits && (
        <>
          <div className="gal-cells" role="list" aria-label="Output macrocells">
            {res.cells.map((c) => {
              const on = c.kind === "reg" || c.kind === "comb";
              const tip = on
                ? `pin ${c.pin}: ${c.name} (${c.what}), ${c.terms} of ${c.capacity} product terms`
                  + (c.active_high ? "" : ", active low") + (c.oe ? ", output enable" : "")
                : c.kind === "input" ? `pin ${c.pin}: input ${c.name}` : `pin ${c.pin}: free`;
              return (
                <div key={c.pin} role="listitem" className={`gal-cell ${c.kind}`} title={tip}>
                  <span className="gal-pin">{c.pin}</span>
                  <span className="gal-name mono">{on || c.kind === "input" ? c.name : "—"}</span>
                  {on && (
                    <span className="gp-track" aria-label={`${c.terms} of ${c.capacity} product terms`}>
                      <span className="gp-fill" style={{ width: `${(100 * c.terms) / Math.max(1, c.capacity)}%` }} />
                    </span>
                  )}
                  <span className="gal-kind small muted">
                    {c.kind === "reg" ? `reg · ${c.terms}/${c.capacity}`
                      : c.kind === "comb" ? `${c.terms}/${c.capacity}` : c.kind === "input" ? "in" : ""}
                  </span>
                </div>
              );
            })}
          </div>
          {moved.length > 0 && (
            <div className="small gal-moved">
              The GAL needs different pins for {moved.map((p) => `${p.name} (${res.pins[p.name]})`).join(", ")}.
              {onSetLocks && <> <button className="linkbtn" onClick={useFitted}>Use the fitted pins</button></>}
            </div>
          )}
          {res.notes.map((n) => <div key={n} className="muted small">{n}</div>)}
          <div className={`small ${res.check_ok ? "muted" : "msg error"}`}>{res.check}</div>
          <div className="gp-actions">
            <button onClick={() => setEqns(true)} title="The equations, as a galette / GALasm source file">
              Equations…
            </button>
            <span className="muted small">{device.note}</span>
          </div>
        </>
      )}
      {eqns && res?.pld && (
        <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) setEqns(false); }}>
          <div className="modal gp-sheet" role="dialog" aria-modal="true" aria-label="GAL equations">
            <div className="modal-head">
              <h2>GAL equations ({design.device})</h2>
              <button className="iconbtn" onClick={() => setEqns(false)} aria-label="Close">×</button>
            </div>
            <pre className="code gal-pld">{res.pld}</pre>
            <div className="modal-foot">
              <span className="muted small">Build writes this as a .pld next to the .jed.</span>
              <span className="spacer" />
              <button className="primary" onClick={() => setEqns(false)}>Done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
