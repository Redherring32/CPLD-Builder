import { MacrocellBar } from "./MacrocellBar";
import { useState } from "react";
import type { Design, GenResult } from "./types";
import { shortNetName } from "./netContext";
import { SimPanel } from "./SimPanel";

type Tab = "report" | "verilog" | "pins" | "sim";
const TAB_NAMES: Record<Tab, string> = {
  report: "Report", verilog: "Verilog", pins: "Pin file", sim: "Simulate",
};

export function ReportPanel({ design, gen, genError, slots, selectedNet, onSelectNet, onSimNets }: {
  design: Design; gen: GenResult | null; genError: string; slots: Record<string, number>;
  selectedNet: string | null; onSelectNet: (n: string | null) => void;
  onSimNets: (nets: Record<string, number | null> | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("report");
  const used = gen?.ports.length ?? 0;
  const cap = gen?.capacity ?? null;
  const over = cap !== null && used > cap;

  return (
    <section className="report" aria-label="Report">
      <div className="report-tabs" role="tablist">
        {(Object.keys(TAB_NAMES) as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t}
                  className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {TAB_NAMES[t]}
          </button>
        ))}
        <span className="spacer" />
        {gen && (
          <span className={`pincount${over ? " over" : ""}`} data-testid="pincount">
            Pins {used}{cap !== null ? ` / ${cap}` : ""} · {design.device} {design.package}
          </span>
        )}
      </div>

      <MacrocellBar design={design} gen={gen} slots={slots} />
      <div className="report-body">
        {genError && <div className="msg error">{genError}</div>}
        {!gen && !genError && <div className="muted">Generating…</div>}

        {gen && tab === "report" && (
          <>
            <Messages title="Errors" cls="error" items={gen.errors} />
            <Messages title="Warnings" cls="warning" items={gen.warnings} />
            <table className="ports">
              <thead>
                <tr><th>Pin</th><th>Dir</th><th>Signal</th><th>Net</th></tr>
              </thead>
              <tbody>
                {[...gen.ports]
                  .sort((a, b) => (a.pin ?? 999) - (b.pin ?? 999))
                  .map((p) => (
                    <tr key={p.name}
                        className={p.net === selectedNet ? "selected" : ""}
                        onClick={() => onSelectNet(p.net === selectedNet ? null : p.net)}>
                      <td className="num">{p.pin ?? "?"}</td>
                      <td className={`dir ${p.direction}`}>{p.direction}</td>
                      <td className="mono">{p.name}</td>
                      <td className="mono muted">{shortNetName(p.net)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <Messages title="Notes" cls="note" items={gen.notes} />
          </>
        )}
        {gen && tab === "verilog" && <pre className="code">{gen.verilog || "(no output)"}</pre>}
        {gen && tab === "pins" && <pre className="code">{gen.pin_file || "(no output)"}</pre>}
        {tab === "sim" && <SimPanel design={design} onNets={onSimNets} />}
      </div>
    </section>
  );
}

function Messages({ title, cls, items }: { title: string; cls: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className={`msgs ${cls}`}>
      <h3>{title} ({items.length})</h3>
      <ul>{items.map((m, i) => <li key={i}>{m}</li>)}</ul>
    </div>
  );
}
