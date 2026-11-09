import { useEffect, useState } from "react";
import * as api from "./api";
import type { BuildConfig } from "./api";
import type { Design } from "./types";

export function BuildDialog({ design, config, onClose, onSetup, greenpak = false, gal = false,
                             kind = "" }: {
  design: Design; config: BuildConfig; onClose: () => void; onSetup: () => void;
  greenpak?: boolean; gal?: boolean; kind?: string;
}) {
  const ice40 = kind === "ice40", max = kind === "max7000";
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
        {greenpak ? (
          <p className="small">GreenPAKs can't be built automatically: there is no open tool
            chain for them. Use <b>LUT sheet…</b> in the report panel to enter the design in
            Renesas Go Configure, which programs the chip. The Verilog and pin file tabs show
            the same design.</p>
        ) : <>
        {ice40 ? (
          <ul className="small build-cfg">
            <li>Yosys synthesises the design, nextpnr places and routes it, icepack makes
              the bitstream (<span className="mono">.bin</span>, for the SPI flash or
              iceprog). The synthesised netlist is simulated against the design.</li>
            <li>nextpnr: <span className="mono">{config.nextpnr ?? "not found — get it from Setup"}</span></li>
            <li className="muted">Output goes to a <span className="mono">build/</span> folder next to the project file.</li>
          </ul>
        ) : max ? (
          <ul className="small build-cfg">
            <li>Writes a Quartus project (<span className="mono">.qpf/.qsf</span> with the device
              and every pin) and, with Quartus II 13.0 SP1 installed, compiles it to a
              <span className="mono"> .pof</span> (and <span className="mono">.svf</span>).</li>
            <li>Quartus: <span className="mono">{config.quartus ?? "not found — the build stops at the project files"}</span></li>
            <li className="muted">Output goes to a <span className="mono">build/</span> folder next to the project file.</li>
          </ul>
        ) : gal ? (
          <ul className="small build-cfg">
            <li>cpldglue fits the design into the {design.device} and writes the fuse map
              (<span className="mono">.jed</span>) for any GAL programmer (TL866 / T48 /
              XGecu), plus the equations (<span className="mono">.pld</span>, galette / GALasm
              format) and the pins. Only Yosys is needed.</li>
            <li className="muted">Output goes to a <span className="mono">build/</span> folder next to the project file.</li>
          </ul>
        ) : (
        <ul className="small build-cfg">
          <li>Yosys flow: <span className="mono">{config.flow_dir ?? "not downloaded"}</span>
            {config.flow_dir && !config.flow_ok && <b className="err"> (cells.lib / techmap.v missing)</b>}</li>
          <li>Fitter: <span className="mono">{config.fitter ?? "not found — the build stops at the EDIF netlist"}</span></li>
          <li className="muted">Output goes to a <span className="mono">build/</span> folder next to the project file.</li>
        </ul>
        )}
        {result && !greenpak && (
          <pre className={`code buildlog ${result.ok ? "ok" : "bad"}`} data-testid="buildlog">{result.log}</pre>
        )}
        </>}
        <div className="modal-foot">
          {!greenpak && !gal && (ice40 ? !config.nextpnr : max ? !config.quartus
                                     : (!config.flow_dir || !config.fitter)) &&
            <button onClick={onSetup} disabled={running}>Get missing tools…</button>}
          <span className="spacer" />
          <button onClick={onClose} disabled={running}>Close</button>
          {!greenpak && <button className="primary" onClick={go}
                                disabled={running || (!gal && !ice40 && !max && !config.flow_dir)}>
            {running ? "Building…" : result ? "Build again" : "Build"}
          </button>}
        </div>
      </div>
    </div>
  );
}
