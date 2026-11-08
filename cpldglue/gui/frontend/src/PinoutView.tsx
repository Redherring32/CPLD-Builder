import { useMemo, useState } from "react";
import type { DragEvent } from "react";
import type { Design, DeviceInfo, GenPort, GenResult } from "./types";

export const SIGNAL_MIME = "application/x-cpldglue-signal";

type Side = "top" | "left" | "bottom" | "right";
type PinType = "io" | "input" | "jtag" | "power" | "nc";

/** Where pin k of an n-pin package sits, as (side, index along the side in
 *  drawing order: left-to-right for top/bottom, top-to-bottom for left/right).
 *  PLCC: pin 1 in the middle of the top edge, counter-clockwise (seen from
 *  above). QFP: pin 1 at the top of the left edge, counter-clockwise. */
export function placePin(pkg: string, k: number, total = 44): { side: Side; idx: number } {
  const n = total / 4;
  if (pkg.startsWith("PLCC")) {
    const a = (n + 1) / 2;                       // pins 1..a on the top-left half
    if (k <= a) return { side: "top", idx: a - k };
    if (k > total - (n - a)) return { side: "top", idx: a + (total - k) };
    if (k <= a + n) return { side: "left", idx: k - a - 1 };
    if (k <= a + 2 * n) return { side: "bottom", idx: k - a - n - 1 };
    return { side: "right", idx: a + 3 * n - k };
  }
  if (k <= n) return { side: "left", idx: k - 1 };
  if (k <= 2 * n) return { side: "bottom", idx: k - n - 1 };
  if (k <= 3 * n) return { side: "right", idx: 3 * n - k };
  return { side: "top", idx: 4 * n - k };
}

interface PinInfo {
  num: number;
  type: PinType;
  role: string;            // e.g. "I/O", "GCLK1 (input only)", "TDI (JTAG)", "VCC"
  port?: GenPort;
  locked: boolean;
}

/** Drawing geometry: 44-pin packages keep their roomy pitch; bigger ones
 *  get a tighter pitch and a larger body. */
function geometry(total: number) {
  const n = total / 4;
  const PITCH = n <= 11 ? 360 / 11 : 20;
  const BODY = PITCH * n, BODY0 = 200;
  return { n, PITCH, BODY, BODY0, S: BODY + 2 * BODY0, pinW: Math.min(16, PITCH * 0.7) };
}

export function PinoutView({ design, device, gen, selectedNet, onSelectNet,
                             onLock, onUnlock, onSetLocks, onFlash }: {
  design: Design; device: DeviceInfo | undefined; gen: GenResult | null;
  selectedNet: string | null; onSelectNet: (n: string | null) => void;
  onLock: (signal: string, pin: number) => void; onUnlock: (signal: string) => void;
  onSetLocks: (locks: Record<string, number>) => void; onFlash: (msg: string) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const [zoom, setZoom] = useState<"fit" | "full" | null>(null);   // null = by size
  const ports = gen?.ports ?? [];
  const portByName = useMemo(() => Object.fromEntries(ports.map((p) => [p.name, p])), [ports]);

  const pins: PinInfo[] = useMemo(() => {
    if (!device) return [];
    const inputRole = Object.fromEntries(Object.entries(device.inputs).map(([n, p]) => [p, n]));
    const jtagRole = Object.fromEntries(Object.entries(device.jtag).map(([n, p]) => [p, n]));
    const portAt = Object.fromEntries(ports.filter((p) => p.pin != null).map((p) => [p.pin!, p]));
    const lockedPins = new Set(Object.values(design.pin_locks));
    const nc = new Set(device.nc ?? []);
    return Array.from({ length: device.pin_count }, (_, i) => {
      const num = i + 1;
      let type: PinType = "io", role = "I/O";
      if (device.power[String(num)]) { type = "power"; role = device.power[String(num)]; }
      else if (nc.has(num)) { type = "nc"; role = "not connected"; }
      else if (inputRole[num]) { type = "input"; role = `${inputRole[num]} (input only)`; }
      else if (jtagRole[num]) {
        type = design.keep_jtag ? "jtag" : "io";
        role = design.keep_jtag ? `${jtagRole[num]} (JTAG, reserved)` : `I/O (${jtagRole[num]} freed)`;
      }
      return { num, type, role, port: portAt[num], locked: lockedPins.has(num) && !!portAt[num] };
    });
  }, [device, ports, design.pin_locks, design.keep_jtag]);

  const staleLocks = Object.entries(design.pin_locks).filter(([s]) => !portByName[s]);

  const canDrop = (pin: PinInfo, signal: string): string | null => {
    const port = portByName[signal];
    if (!port) return "Unknown signal";
    if (pin.type === "power") return `Pin ${pin.num} is ${pin.role}`;
    if (pin.type === "nc") return `Pin ${pin.num} is not connected inside the chip`;
    if (pin.type === "jtag") return `Pin ${pin.num} is a JTAG pin (untick JTAG to use it)`;
    if (pin.type === "input" && port.direction !== "input")
      return `Pin ${pin.num} is input-only; ${signal} is an ${port.direction}`;
    return null;
  };

  const onDrop = (e: DragEvent, pin: PinInfo) => {
    e.preventDefault();
    setDropTarget(null);
    const signal = e.dataTransfer.getData(SIGNAL_MIME);
    if (!signal) return;
    const why = canDrop(pin, signal);
    if (why) onFlash(why);
    else onLock(signal, pin.num);
  };

  if (!device) {
    return <div className="pinout empty muted">
      No pin table for {design.device} {design.package}.
    </div>;
  }

  const { S, BODY0, BODY, PITCH, pinW } = geometry(device.pin_count);
  const plcc = design.package.startsWith("PLCC");
  // Up to 44 pins fit the panel; bigger packages are drawn near full size
  // (scrollable) so the labels stay readable.
  const fit = (zoom ?? (device.pin_count <= 44 ? "fit" : "full")) === "fit";
  const shown = hover ?? null;
  const hp = shown ? pins[shown - 1] : null;
  const cap = gen?.capacity ?? null;

  return (
    <div className="pinout" data-testid="pinout">
      <div className="pinout-drawing">
        <div className={`pinout-scroll${fit ? "" : " full"}`}>
        <svg viewBox={`0 0 ${S} ${S}`} role="img"
             width={fit ? undefined : S * 0.85} height={fit ? undefined : S * 0.85}
             aria-label={`${design.device} ${design.package} pinout`}>
          <rect x={BODY0} y={BODY0} width={BODY} height={BODY} rx={plcc ? 18 : 4}
                className="pkg-body" />
          <circle cx={plcc ? S / 2 : BODY0 + 22}
                  cy={BODY0 + 22} r={7} className="pkg-dot" />
          <text x={S / 2} y={S / 2 - 8} className="pkg-name">{design.device}</text>
          <text x={S / 2} y={S / 2 + 16} className="pkg-sub">{design.package}</text>
          {pins.map((p) => {
            const { side, idx } = placePin(design.package, p.num, device.pin_count);
            const along = BODY0 + PITCH * (idx + 0.5);
            const horiz = side === "top" || side === "bottom";
            const w = horiz ? pinW : 26, h = horiz ? 26 : pinW;
            const x = horiz ? along - w / 2 : side === "left" ? BODY0 - w : BODY0 + BODY;
            const y = horiz ? (side === "top" ? BODY0 - h : BODY0 + BODY) : along - h / 2;
            // label outside the pin
            const lx = horiz ? along : side === "left" ? x - 6 : x + w + 6;
            const ly = horiz ? (side === "top" ? y - 6 : y + h + 6) : along;
            const anchor = horiz ? "start" : side === "left" ? "end" : "start";
            const rot = horiz ? (side === "top" ? `rotate(-90 ${lx} ${ly})` : `rotate(90 ${lx} ${ly})`) : undefined;
            const numX = horiz ? along : side === "left" ? BODY0 + 6 : BODY0 + BODY - 6;
            const numY = horiz ? (side === "top" ? BODY0 + 14 : BODY0 + BODY - 6) : along + 4;
            const label = p.port ? p.port.name : p.type === "power" ? p.role
                        : p.type === "nc" ? "NC"
                        : p.type === "jtag" ? p.role.split(" ")[0] : "";
            const sel = !!p.port && p.port.net === selectedNet;
            const cls = ["pin", `t-${p.type}`, p.port ? `d-${p.port.direction}` : "free",
                         p.locked ? "locked" : "", sel ? "sel" : "",
                         dropTarget === p.num ? "drop" : ""].join(" ");
            return (
              <g key={p.num} className={cls} data-pin={p.num}
                 onMouseEnter={() => setHover(p.num)} onMouseLeave={() => setHover(null)}
                 onClick={() => {
                   if (p.port) { onSelectNet(sel ? null : p.port.net); return; }
                   // Free pin + a selected signal: lock the signal here.
                   const s = ports.find((x) => x.net === selectedNet);
                   if (!s || p.type === "power" || p.type === "nc") return;
                   const why = canDrop(p, s.name);
                   if (why) onFlash(why); else onLock(s.name, p.num);
                 }}
                 onDragOver={(e) => { e.preventDefault(); setDropTarget(p.num); }}
                 onDragLeave={() => setDropTarget(null)}
                 onDrop={(e) => onDrop(e, p)}>
                <title>{`Pin ${p.num}: ${p.role}${p.port ? ` — ${p.port.name} (${p.port.direction})` : ""}${p.locked ? ", locked" : ""}`}</title>
                <rect x={x} y={y} width={w} height={h} rx={2} />
                <text x={numX} y={numY} className="pinno"
                      textAnchor={horiz ? "middle" : side === "left" ? "start" : "end"}>{p.num}</text>
                {label && (
                  <text x={lx} y={ly} className="plabel" textAnchor={anchor}
                        dominantBaseline="middle" transform={rot}>
                    {p.locked ? "🔒 " : ""}{label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        </div>
        <div className="pin-detail small">
          <button className="iconbtn small zoombtn" onClick={() => setZoom(fit ? "full" : "fit")}
                  title={fit ? "Draw at full size (scroll to move around)" : "Fit the whole package in the panel"}>
            {fit ? "Full size" : "Fit"}
          </button>{" "}
          {hp ? <>Pin <b>{hp.num}</b> · {hp.role}
                  {hp.port && <> · <span className="mono">{hp.port.name}</span> ({hp.port.direction}){hp.locked && " · locked"}</>}</>
              : <span className="muted">
                  Drag a signal onto a pin to lock it there, or select a signal and click a free pin.
                </span>}
        </div>
      </div>

      <div className="pinout-side">
        <div className="pinout-actions">
          <span className={`pincount${cap !== null && ports.length > cap ? " over" : ""}`}>
            {ports.length}{cap !== null ? ` / ${cap}` : ""} pins
          </span>
          {gen?.macrocells && (
            <span className={`pincount${gen.macrocells.total !== null &&
                    gen.macrocells.outputs + gen.macrocells.storage > gen.macrocells.total ? " over" : ""}`}
                  title={`Estimate: ${gen.macrocells.outputs} outputs + ${gen.macrocells.storage} flip-flops/latches. The fitter report has the real figure.`}>
              ≤{gen.macrocells.outputs + gen.macrocells.storage}
              {gen.macrocells.total !== null ? ` / ${gen.macrocells.total}` : ""} macrocells
            </span>
          )}
          <button onClick={() => onSetLocks(Object.fromEntries(
                    ports.filter((p) => p.pin != null).map((p) => [p.name, p.pin!])))}
                  disabled={!ports.length}
                  title="Lock every signal where it is now, so later edits don't move pins">
            Lock all
          </button>
          <button onClick={() => onSetLocks({})} disabled={!Object.keys(design.pin_locks).length}>
            Unlock all
          </button>
        </div>
        <ul className="siglist">
          {[...ports].sort((a, b) => a.name.localeCompare(b.name)).map((p) => {
            const locked = design.pin_locks[p.name] !== undefined;
            return (
              <li key={p.name} draggable
                  className={p.net === selectedNet ? "sel" : ""}
                  onDragStart={(e) => { e.dataTransfer.setData(SIGNAL_MIME, p.name); e.dataTransfer.effectAllowed = "move"; }}
                  onClick={() => onSelectNet(p.net === selectedNet ? null : p.net)}
                  data-testid={`sig-${p.name}`}
                  title="Drag onto a pin to lock it there">
                <span className={`dir ${p.direction}`}>{p.direction === "input" ? "in" : p.direction === "output" ? "out" : "io"}</span>
                <span className="mono name">{p.name}</span>
                <span className="num">{p.pin ?? "?"}</span>
                <button className="iconbtn" aria-label={locked ? `Unlock ${p.name}` : `Lock ${p.name}`}
                        title={locked ? "Locked: click to let the tool place it" : "Lock it on its current pin"}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (locked) onUnlock(p.name);
                          else if (p.pin != null) onLock(p.name, p.pin);
                        }}>
                  {locked ? "🔒" : "🔓"}
                </button>
              </li>
            );
          })}
          {!ports.length && <li className="muted small">No signals need pins yet.</li>}
        </ul>
        {staleLocks.length > 0 && (
          <div className="msgs warning">
            <h3>Locks for missing signals</h3>
            <ul>
              {staleLocks.map(([s, pin]) => (
                <li key={s}><span className="mono">{s}</span> → {pin}{" "}
                  <button className="iconbtn" onClick={() => onUnlock(s)}>remove</button></li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
