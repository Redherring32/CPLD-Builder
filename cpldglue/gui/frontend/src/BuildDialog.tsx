import { useEffect, useState } from "react";
import * as api from "./api";
import type { BuildConfig } from "./api";
import type { Design } from "./types";

export function BuildDialog({ design, config, onClose, onSetup }: {
  design: Design; config: BuildConfig; onClose: () => void; onSetup: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; log: string } | null>(null);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape" && !running) onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose, running]);

  const go = async () => {
    setRunning(true); setResult(null);
    try { setResult(await api.runBuild(design)); }
    catch (e) { setResult({ ok: false, log: String(e) }); }
    finally { setRunning(false); }
  };

  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget && !running) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Build">
        <div className="modal-head">
          <h2>Build {design.name} for {design.device} {design.package}</h2>
          <button className="iconbtn" onClick={onClose} aria-label="Close" disabled={running}>×</button>
        </div>
        <ul className="small build-cfg">
          <li>Yosys flow: <span className="mono">{config.flow_dir ?? "not downloaded"}</span>
            {config.flow_dir && !config.flow_ok && <b className="err"> (cells.lib / techmap.v missing)</b>}</li>
          <li>Fitter: <span className="mono">{config.fitter ?? "not found — the build stops at the EDIF netlist"}</span></li>
          <li className="muted">Output goes to a <span className="mono">build/</span> folder next to the project file.</li>
        </ul>
        {result && (
          <pre className={`code buildlog ${result.ok ? "ok" : "bad"}`} data-testid="buildlog">{result.log}</pre>
        )}
        <div className="modal-foot">
          {(!config.flow_dir || !config.fitter) &&
            <button onClick={onSetup} disabled={running}>Get missing tools…</button>}
          <span className="spacer" />
          <button onClick={onClose} disabled={running}>Close</button>
          <button className="primary" onClick={go} disabled={running || !config.flow_dir}>
            {running ? "Building…" : result ? "Build again" : "Build"}
          </button>
        </div>
      </div>
    </div>
  );
}
