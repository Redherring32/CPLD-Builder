import { useCallback, useEffect, useState } from "react";
import * as api from "./api";
import type { DepInfo, DepJob } from "./api";

function fmt(n: number): string {
  return n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;
}

/** Optional tools: what's installed, and buttons to download what isn't. */
export function SetupDialog({ onClose }: { onClose: () => void }) {
  const [deps, setDeps] = useState<DepInfo[]>([]);
  const [jobs, setJobs] = useState<Record<string, DepJob>>({});
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const r = await api.deps();
      setDeps(r.deps); setJobs(r.jobs); setError("");
    } catch (e) { setError(String(e)); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Poll while a download is running.
  const running = Object.values(jobs).some((j) => j.state === "running");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(refresh, 400);
    return () => clearInterval(t);
  }, [running, refresh]);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  const start = async (id: string) => {
    try { await api.fetchDep(id); await refresh(); }
    catch (e) { setError(String(e)); }
  };

  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal setup" role="dialog" aria-modal="true" aria-label="Setup">
        <div className="modal-head">
          <h2>Optional tools</h2>
          <button className="iconbtn" onClick={onClose} aria-label="Close">×</button>
        </div>
        <p className="small muted">
          Editing and pin assignment work without any of these. Downloads are
          checked against fixed SHA-256 checksums and kept in your user folder.
        </p>
        {error && <div className="msg error small">{error}</div>}
        <ul className="deplist">
          {deps.map((d) => {
            const j = jobs[d.id];
            const busy = j?.state === "running";
            return (
              <li key={d.id} data-testid={`dep-${d.id}`}>
                <div className="dep-head">
                  <span className={`dep-state ${d.found ? "ok" : "missing"}`}>
                    {d.found ? "✓" : "–"}
                  </span>
                  <b>{d.title}</b>
                  <span className="muted small"> · for {d.needed_for}</span>
                  <span className="spacer" />
                  {!d.found && d.url && (
                    <a href={d.url} target="_blank" rel="noreferrer">
                      {d.id === "kicad" ? "Get KiCad" : "Get it"}</a>
                  )}
                  {d.can_fetch && (
                    <button onClick={() => start(d.id)} disabled={busy}
                            className={d.found ? "" : "primary"}>
                      {busy ? "Working…" : d.found ? "Download again" : "Download"}
                    </button>
                  )}
                  {d.id === "fitter" && d.installer && !d.found && !busy && (
                    <button onClick={() => api.openInstaller().catch((e) => setError(String(e)))}>
                      Open installer
                    </button>
                  )}
                </div>
                <div className="small dep-where mono">
                  {d.found ? d.where : d.download}
                </div>
                {j && (j.state !== "running" || j.message) && (
                  <div className={`small dep-msg ${j.state}`}>
                    {j.state === "running" && j.total
                      ? <progress value={j.done} max={j.total} aria-label={`${d.title} download`} />
                      : null}
                    {" "}{j.message}
                    {j.state === "running" && j.total ? ` (${fmt(j.done)} / ${fmt(j.total)})` : ""}
                  </div>
                )}
              </li>
            );
          })}
          {!deps.length && !error && <li className="muted small">Checking…</li>}
        </ul>
        <div className="modal-foot">
          <button onClick={refresh}>Check again</button>
          <span className="spacer" />
          <button className="primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
