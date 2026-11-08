import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";
import type { Design } from "./types";
import type { SimPort, SimState } from "./api";
import { Waveform, type Sample } from "./Waveform";

const HISTORY = 64;

type V = 0 | 1 | null;

function Led({ v, label }: { v: V | undefined; label?: string }) {
  const cls = v === 1 ? "on" : v === 0 ? "off" : "z";
  return (
    <span className={`led ${cls}`} title={v == null ? "high-impedance / unknown" : String(v)}
          aria-label={`${label ?? ""} ${v == null ? "Z" : v}`}>
      {v == null ? "Z" : v}
    </span>
  );
}

export function SimPanel({ design, onNets }: {
  design: Design;
  onNets: (nets: Record<string, number | null> | null) => void;
}) {
  const [ports, setPorts] = useState<SimPort[]>([]);
  const [state, setState] = useState<SimState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [inputs, setInputs] = useState<Record<string, V>>({});
  const inputsRef = useRef(inputs);
  inputsRef.current = inputs;
  const [clock, setClock] = useState("");
  const [hz, setHz] = useState(2);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<Sample[]>([]);

  const show = useCallback((s: SimState) => {
    setState(s);
    onNets(s.nets);
  }, [onNets]);

  // Rebuild when the design changes (Yosys runs only if the logic changed).
  const build = useCallback(async (fresh = false) => {
    setBusy(true);
    try {
      if (fresh) setHistory([]);
      const b = await api.simBuild(design, fresh);
      if (!b.ok) { setError(b.error ?? "build failed"); setState(null); onNets(null); return; }
      setError("");
      setPorts(b.ports);
      const next: Record<string, V> = {};
      for (const p of b.ports) {
        if (p.direction === "output") continue;
        const old = inputsRef.current[p.name];
        // Active-low inputs (…_n) start inactive (1); inouts start released.
        next[p.name] = old !== undefined ? old
          : p.direction === "inout" ? null : /_n$/i.test(p.name) ? 1 : 0;
      }
      setInputs(next);
      show(await api.simStep([next]));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [design, onNets, show]);

  useEffect(() => {
    const t = setTimeout(() => build(), 300);
    return () => clearTimeout(t);
  }, [build]);

  useEffect(() => () => onNets(null), [onNets]);   // clear canvas values on close

  const drive = async (changes: Record<string, V>[]) => {
    let cur = { ...inputsRef.current };
    for (const c of changes) cur = { ...cur, ...c };
    setInputs(cur);
    try {
      const s = await api.simStep(changes);
      show(s);
      if (s.trace?.length) setHistory((h) => [...h, ...s.trace!].slice(-HISTORY));
    } catch (e) { setError(String(e)); }
  };

  const pulse = (name: string) => {
    const now = inputsRef.current[name] ?? 0;
    const other: V = now ? 0 : 1;
    drive([{ [name]: other }, { [name]: now }]);
  };

  // Free-running clock.
  useEffect(() => {
    if (!running || !clock) return;
    const id = setInterval(() => {
      const now = inputsRef.current[clock] ?? 0;
      drive([{ [clock]: now ? 0 : 1 }]);
    }, 1000 / hz / 2);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, clock, hz]);

  const ins = ports.filter((p) => p.direction !== "output");
  const outs = ports.filter((p) => p.direction !== "input");

  return (
    <div className="sim" data-testid="sim">
      <div className="sim-bar">
        <button onClick={() => build(true)} disabled={busy}
                title="Rebuild and reset every flip-flop and latch to unknown">Reset</button>
        <label className="small">Clock{" "}
          <select value={clock} onChange={(e) => { setClock(e.target.value); setRunning(false); }}
                  aria-label="Clock input">
            <option value="">—</option>
            {ins.filter((p) => p.direction === "input").map((p) =>
              <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </label>
        <select value={hz} onChange={(e) => setHz(Number(e.target.value))} aria-label="Clock rate"
                disabled={!clock}>
          {[1, 2, 5, 10].map((h) => <option key={h} value={h}>{h} Hz</option>)}
        </select>
        <button onClick={() => setRunning((r) => !r)} disabled={!clock}>
          {running ? "Stop" : "Run"}
        </button>
        {busy && <span className="muted small">building…</span>}
      </div>
      {error && <div className="msg error small">{error}
        {/Yosys not found|could not run Yosys/.test(error) && <>
          {" "}<button className="linkbtn" onClick={() => window.dispatchEvent(new Event("cpldglue:setup"))}>
            Open Setup</button></>}
      </div>}
      {state?.contention && (
        <div className="msg warning small">Bus contention: the CPLD and an outside driver both drive a pin.</div>
      )}

      <h3 className="simh">Inputs</h3>
      <ul className="simlist">
        {ins.map((p) => {
          const v = inputs[p.name];
          return (
            <li key={p.name}>
              <span className="mono name" title={p.net}>{p.name}</span>
              {p.direction === "inout" ? (
                <select value={v == null ? "z" : String(v)} aria-label={`Drive ${p.name}`}
                        onChange={(e) => drive([{ [p.name]: e.target.value === "z" ? null : (Number(e.target.value) as V) }])}>
                  <option value="z">Z (released)</option><option value="0">0</option><option value="1">1</option>
                </select>
              ) : (
                <button className={`switch ${v ? "on" : ""}`} role="switch" aria-checked={!!v}
                        aria-label={`Toggle ${p.name}`} data-testid={`in-${p.name}`}
                        onClick={() => drive([{ [p.name]: v ? 0 : 1 }])}>
                  {v ? 1 : 0}
                </button>
              )}
              {p.direction === "input" && (
                <button className="iconbtn" title="Pulse (toggle and back)" onClick={() => pulse(p.name)}
                        aria-label={`Pulse ${p.name}`}>⎍</button>
              )}
            </li>
          );
        })}
        {!ins.length && <li className="muted small">No inputs.</li>}
      </ul>

      <h3 className="simh">Outputs</h3>
      <ul className="simlist">
        {outs.map((p) => (
          <li key={p.name} data-testid={`out-${p.name}`}>
            <span className="mono name" title={p.net}>{p.name}</span>
            <Led v={state?.values[p.name] as V | undefined} label={p.name} />
            {p.direction === "inout" && <span className="muted small">bus</span>}
          </li>
        ))}
        {!outs.length && <li className="muted small">No outputs.</li>}
      </ul>
      <details className="wavebox" open>
        <summary>Waveform <span className="muted small">(last {HISTORY} steps)</span>
          {history.length > 0 && (
            <button className="iconbtn small" onClick={(e) => { e.preventDefault(); setHistory([]); }}>clear</button>
          )}
        </summary>
        <Waveform names={ports.map((p) => p.name)} samples={history} />
      </details>
      <p className="muted small">Net values also show on the chip view while this tab is open.</p>
    </div>
  );
}
