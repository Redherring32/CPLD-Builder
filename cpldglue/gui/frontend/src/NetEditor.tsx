import { useEffect, useState } from "react";
import type { Design, GenResult } from "./types";
import { shortNetName } from "./netContext";

export function NetEditor({ design, gen, name, onRename, onExternal, onConst,
                            onDisconnect, onDelete, onClose }: {
  design: Design; gen: GenResult | null; name: string;
  onRename: (to: string) => void; onExternal: (v: boolean) => void;
  onConst: (v: number | null) => void; onDisconnect: (ref: string, pin: string) => void;
  onDelete: () => void; onClose: () => void;
}) {
  const net = design.nets[name];
  const [draft, setDraft] = useState(name);
  useEffect(() => setDraft(name), [name]);
  if (!net) return null;
  const g = gen?.nets[name];

  const commit = () => { if (draft !== name) onRename(draft.trim()); };

  return (
    <div className="netinfo" data-testid="netinfo" onKeyDown={(e) => e.stopPropagation()}>
      <div className="netinfo-head">
        <input
          className="netname mono" value={draft} aria-label="Net name"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") { setDraft(name); (e.target as HTMLInputElement).blur(); }
          }}
        />
        <button className="iconbtn" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="netinfo-row">
        <label>
          <input type="checkbox" checked={net.external} disabled={net.const !== null}
                 onChange={(e) => onExternal(e.target.checked)} />
          {" "}Goes off-chip (needs a CPLD pin)
        </label>
      </div>
      <div className="netinfo-row">
        <label>
          Constant{" "}
          <select value={net.const === null ? "" : String(net.const)}
                  onChange={(e) => onConst(e.target.value === "" ? null : Number(e.target.value))}>
            <option value="">none</option>
            <option value="0">0 (GND)</option>
            <option value="1">1 (VCC)</option>
          </select>
        </label>
        {g?.port && (
          <span className="muted small">
            {" "}→ {g.direction} <span className="mono">{g.port}</span>
            {g.pin != null && <> on pin {g.pin}</>}
          </span>
        )}
      </div>
      <ul className="netpins">
        {net.nodes.map((n) => (
          <li key={`${n.ref}.${n.pin}`}>
            <span className="mono">{n.ref}.{n.pin}</span>
            <button className="iconbtn small" title="Disconnect this pin"
                    onClick={() => onDisconnect(n.ref, n.pin)}>×</button>
          </li>
        ))}
      </ul>
      <div className="netinfo-row end">
        <span className="muted small">{shortNetName(name) !== name ? shortNetName(name) : ""}</span>
        <button className="danger" onClick={onDelete}>Delete net</button>
      </div>
    </div>
  );
}
