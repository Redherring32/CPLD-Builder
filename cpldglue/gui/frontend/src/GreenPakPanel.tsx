/** GreenPAK resource check: maps the design onto LUTs and DFFs (Yosys on
 *  the server), shows one meter per kind of logic cell, and opens the sheet
 *  to enter the design in Renesas Go Configure. */
import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import type { GreenPakResult } from "./api";
import type { Design, DeviceInfo, GenResult } from "./types";

export function GreenPakPanel({ design, device, gen }: {
  design: Design; device: DeviceInfo; gen: GenResult | null;
}) {
  const [res, setRes] = useState<GreenPakResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (!gen?.ok) { setRes(null); return; }
    let stale = false;
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await api.greenpak(design);
        if (!stale) setRes(r);
      } catch (e) {
        if (!stale) setRes({ ok: false, error: String(e) } as GreenPakResult);
      } finally {
        if (!stale) setBusy(false);
      }
    }, 600);
    return () => { stale = true; clearTimeout(t); };
  }, [design, gen?.ok, gen?.verilog]);

  const download = (name: string, content: string | Uint8Array, type: string) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([content as BlobPart], { type }));
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  const b64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const bits = res?.bitstream;
  const base = `${design.name}-${design.device}`;

  const save = () => {
    if (!res?.sheet) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([res.sheet], { type: "text/html" }));
    a.download = `${design.name}-${design.device}-greenpak.html`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  return (
    <div className="mcbar gpbar" data-testid="gpbar">
      <div className="mcbar-head">
        <span className="mcbar-title">Logic cells</span>
        <span className="muted small">{device.device} · GreenPAK · {device.supply}</span>
        {busy && <span className="muted small">checking…</span>}
        {res?.ok && (res.fits
          ? <span className="gp-ok">✓ fits</span>
          : <span className="mcbar-over" role="status">⚠ doesn't fit</span>)}
      </div>
      {!gen?.ok && <div className="muted small">Fix the report errors to check the logic.</div>}
      {res && !res.ok && (
        <div className="msg error small">{res.error}
          {/Yosys not found|could not run Yosys/.test(res.error ?? "") && <>
            {" "}<button className="linkbtn"
                         onClick={() => window.dispatchEvent(new Event("cpldglue:setup"))}>
              Open Setup</button></>}
        </div>
      )}
      {res?.ok && (
        <>
          <table className="gp-cells small">
            <tbody>
              {res.cells.map((c) => (
                <tr key={c.type}>
                  <td>{c.title}</td>
                  <td className="gp-meter">
                    <span className="gp-track" role="img"
                          aria-label={`${c.title}: ${c.used} of ${c.total} used`}>
                      <span className="gp-fill" style={{ width: `${(100 * c.used) / Math.max(1, c.total)}%` }} />
                    </span>
                  </td>
                  <td className="num">{c.used} / {c.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="small muted">
            {res.luts} LUT{res.luts === 1 ? "" : "s"} · {res.flops} DFF/latch{res.flops === 1 ? "" : "es"}
            {res.oe ? ` · ${res.oe} pin output enable${res.oe === 1 ? "" : "s"}` : ""}
          </div>
          {res.unplaced.map((u) => <div key={u} className="msg error small">No room for {u}</div>)}
          {res.notes.map((n) => <div key={n} className="muted small">{n}</div>)}
          {bits && (
            <div className="gp-bits small" data-testid="gp-bitstream">
              <b>Bitstream</b>{" "}
              {bits.ok
                ? <span className="gp-ok">✓ {bits.check}</span>
                : <span className="mcbar-over">{bits.errors.join("; ") || bits.check}</span>}
              {bits.files && bits.ok && (
                <div className="gp-actions">
                  <button onClick={() => download(`${base}_programmer.ino`, bits.files!.ino, "text/plain")}
                          title="Arduino sketch that programs the chip over I2C (keeps its I2C address and factory data)">
                    Arduino programmer…
                  </button>
                  <button onClick={() => download(`${base}.txt`, bits.files!.txt, "text/plain")}
                          title="One line per NVM bit (index, value), as GreenPAK Designer's bit list">
                    Bit list (.txt)
                  </button>
                  <button onClick={() => download(`${base}.bin`, b64(bits.files!.bin), "application/octet-stream")}
                          title="The 256-byte configuration image; the _mask.bin marks the bits this design defines">
                    Image (.bin)
                  </button>
                  <button onClick={() => download(`${base}_mask.bin`, b64(bits.files!.mask), "application/octet-stream")}>
                    Mask
                  </button>
                </div>
              )}
            </div>
          )}
          <div className="gp-actions">
            <button onClick={() => setSheet(true)}
                    title="Every LUT's truth table, the DFFs and the pins, to enter in Renesas Go Configure">
              LUT sheet…
            </button>
            <span className="muted small">{device.note}</span>
          </div>
        </>
      )}
      {sheet && res?.sheet && (
        <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) setSheet(false); }}>
          <div className="modal gp-sheet" role="dialog" aria-modal="true" aria-label="GreenPAK sheet">
            <div className="modal-head">
              <h2>GreenPAK sheet</h2>
              <button className="iconbtn" onClick={() => setSheet(false)} aria-label="Close">×</button>
            </div>
            <iframe ref={frame} title="GreenPAK sheet" srcDoc={res.sheet} className="gp-frame" />
            <div className="modal-foot">
              <button onClick={save}>Save HTML</button>
              <button onClick={() => frame.current?.contentWindow?.print()}>Print</button>
              <span className="spacer" />
              <button className="primary" onClick={() => setSheet(false)}>Done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
