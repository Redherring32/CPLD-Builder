/** In-app file browser for the plain-browser editor, where a page can't learn
 *  a picked file's real path: the local server lists folders and the KiCad
 *  files in them (.kicad_sch, .net). The desktop app uses its native dialog. */
import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import type { DirListing } from "./api";

export function FileBrowser({ start, title, onPick, onCancel }: {
  start: string; title: string; onPick: (path: string) => void; onCancel: () => void;
}) {
  const [dir, setDir] = useState<DirListing | null>(null);
  const [typed, setTyped] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [error, setError] = useState("");
  const list = useRef<HTMLUListElement>(null);

  const go = async (path: string) => {
    setError("");
    try {
      const d = await api.listDir(path);
      setDir(d); setTyped(d.path); setSel(null);
      list.current?.scrollTo(0, 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  useEffect(() => { go(start); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopImmediatePropagation(); onCancel(); } };
    window.addEventListener("keydown", esc, true);
    return () => window.removeEventListener("keydown", esc, true);
  }, [onCancel]);

  const join = (name: string) =>
    dir ? (dir.path.endsWith(dir.sep) ? dir.path + name : dir.path + dir.sep + name) : name;

  return (
    <div className="modal-back fb-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div className="modal fb" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="iconbtn" onClick={onCancel} aria-label="Close">×</button>
        </div>
        <div className="row">
          <button onClick={() => dir?.parent && go(dir.parent)} disabled={!dir?.parent}
                  aria-label="Up one folder" title="Up one folder">↑</button>
          <input className="grow mono" value={typed} aria-label="Folder"
                 onChange={(e) => setTyped(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") go(typed); }} />
          <button onClick={() => go(typed)}>Go</button>
        </div>
        {dir && dir.roots.length > 1 && (
          <div className="row small fb-roots">
            {dir.roots.map((r) => <button key={r} className="linkbtn" onClick={() => go(r)}>{r}</button>)}
          </div>
        )}
        {error && <div className="msg error small">{error}</div>}
        <ul className="fb-list" ref={list} role="listbox" aria-label="Folders and files">
          {dir?.dirs.map((d) => (
            <li key={`d${d}`} role="option" aria-selected={false} className="fb-dir"
                onClick={() => go(join(d))} title="Open folder">
              <span className="fb-icon" aria-hidden="true">📁</span>{d}
            </li>
          ))}
          {dir?.files.map((f) => (
            <li key={`f${f}`} role="option" aria-selected={sel === f}
                className={`fb-file${sel === f ? " selected" : ""}`}
                onClick={() => setSel(f)} onDoubleClick={() => onPick(join(f))}>
              <span className="fb-icon" aria-hidden="true">📄</span>{f}
            </li>
          ))}
          {dir && !dir.dirs.length && !dir.files.length && (
            <li className="muted small fb-empty">No folders or KiCad files here.</li>
          )}
        </ul>
        <div className="modal-foot">
          <span className="muted small">{dir ? `${dir.files.length} KiCad file(s)` : "Loading…"}</span>
          <span className="spacer" />
          <button onClick={onCancel}>Cancel</button>
          <button className="primary" disabled={!sel} onClick={() => sel && onPick(join(sel))}>Open</button>
        </div>
      </div>
    </div>
  );
}
