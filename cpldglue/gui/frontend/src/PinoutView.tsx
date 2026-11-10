import { useMemo, useRef, useState } from "react";
import type { DragEvent, PointerEvent as RPointerEvent } from "react";
import { moveSignal } from "./pinMove";
import type { Design, DeviceInfo, GenPort, GenResult } from "./types";
import * as api from "./api";

export const SIGNAL_MIME = "application/x-cpldglue-signal";

type Side = "top" | "left" | "bottom" | "right";
type PinType = "io" | "input" | "jtag" | "reserved" | "power" | "nc";
type Sides = [number, number, number, number];   // left, bottom, right, top

/** Where pin k of an n-pin package sits, as (side, index along the side in
 *  drawing order: left-to-right for top/bottom, top-to-bottom for left/right).
 *  PLCC: pin 1 in the middle of the top edge, counter-clockwise (seen from
 *  above). QFP: pin 1 at the top of the left edge, counter-clockwise. */
export function placePin(pkg: string, k: number, total = 44,
                         sides?: Sides | null): { side: Side; idx: number } {
  if (sides) {                                   // QFN/SOP with uneven sides
    const [L, B, R] = sides;
    if (k <= L) return { side: "left", idx: k - 1 };
    if (k <= L + B) return { side: "bottom", idx: k - L - 1 };
    if (k <= L + B + R) return { side: "right", idx: L + B + R - k };
    return { side: "top", idx: total - k };
  }
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
function geometry(total: number, sides?: Sides | null) {
  const n = total / 4;
  const PITCH = n <= 11 ? 360 / 11 : 20;
  const [L, B, R, T] = sides ?? [n, n, n, n];
  const BW = PITCH * Math.max(B, T, 4), BH = PITCH * Math.max(L, R);
  const M = total <= 20 ? 130 : 200;              // room for labels
  return { PITCH, BW, BH, X0: M, Y0: M, W: BW + 2 * M, H: BH + 2 * M,
           pinW: Math.min(16, PITCH * 0.7) };
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
  const [copying, setCopying] = useState(false);
  const [manual, setManual] = useState<string | null>(null);

  const copyKicad = async () => {
    setCopying(true);
    try {
      const k = await api.kicadSymbol(design);
      const note = k.warnings.length ? ` Note: ${k.warnings.join(" ")}` : "";
      if (await api.copyText(k.clipboard)) {
        onFlash(`Copied ${design.device} with ${k.labels} labels: paste into KiCad's schematic editor with Ctrl+V.${note}`);
      } else {
        setManual(k.clipboard);
        if (note) onFlash(note.trim());
      }
    } catch (e) {
      onFlash(`Could not make the KiCad symbol: ${e instanceof Error ? e.message : e}`);
    } finally {
      setCopying(false);
    }
  };
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
    const reservedRole = Object.fromEntries(Object.entries(device.reserved ?? {}).map(([n, p]) => [p, n]));
    const outOnly = new Set(device.out_only ?? []), noOe = new Set(device.no_oe ?? []);
    const names = device.pin_names ?? {};
    return Array.from({ length: device.pin_count }, (_, i) => {
      const num = i + 1;
      let type: PinType = "io", role = names[String(num)] ?? "I/O";
      if (outOnly.has(num)) role += " (output only)";
      else if (noOe.has(num)) role += " (no output enable: not 3-state)";
      if (device.power[String(num)]) { type = "power"; role = names[String(num)] ?? device.power[String(num)]; }
      else if (reservedRole[num]) { type = "reserved"; role = `${reservedRole[num]} (I2C / programming)`; }
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
    if (pin.type === "reserved") return `Pin ${pin.num} is ${pin.role}`;
    if (port.direction !== "output" && (device?.out_only ?? []).includes(pin.num))
      return `Pin ${pin.num} is output-only; ${signal} is an ${port.direction}`;
    const needsOe = port.direction === "inout" || port.drive === "tri";
    if (needsOe && ((device?.no_oe ?? []).includes(pin.num) || (device?.out_only ?? []).includes(pin.num)))
      return `Pin ${pin.num} has no output enable, so it can't carry the 3-state ${signal}`;
    if (pin.type === "input" && port.direction !== "input")
      return `Pin ${pin.num} is input-only; ${signal} is an ${port.direction}`;
    return null;
  };

  /** Put a signal on a pin: a free pin takes it, a used one swaps. */
  const place = (signal: string, num: number) => {
    const r = moveSignal(design.pin_locks, ports, signal, num,
                         (n, s) => canDrop(pins[n - 1], s));
    if ("error" in r) { onFlash(r.error); return; }
    onSetLocks(r.locks);
    if (r.swapped) onFlash(`Swapped ${signal} and ${r.swapped} (both locked)`);
  };

  const onDrop = (e: DragEvent, pin: PinInfo) => {
    e.preventDefault();
    setDropTarget(null);
    const signal = e.dataTransfer.getData(SIGNAL_MIME);
    if (!signal) return;
    place(signal, pin.num);
  };

  // Dragging a signal's label on the drawing to another pin (pointer events:
  // SVG elements can't use HTML drag and drop). A short press is a click.
  const [drag, setDrag] = useState<{ signal: string; from: number; x: number; y: number;
                                     moved: boolean } | null>(null);
  const pinAt = (x: number, y: number): number | null => {
    const el = document.elementFromPoint(x, y)?.closest("[data-pin]");
    return el ? Number(el.getAttribute("data-pin")) : null;
  };
  const startDrag = (e: RPointerEvent, p: PinInfo) => {
    if (!p.port || e.button !== 0) return;
    // The drag lives in this closure (events can arrive before React renders).
    const cur = { signal: p.port.name, from: p.num, x: e.clientX, y: e.clientY, moved: false };
    const sx = e.clientX, sy = e.clientY;
    const move = (ev: PointerEvent) => {
      cur.x = ev.clientX; cur.y = ev.clientY;
      cur.moved = cur.moved || Math.hypot(ev.clientX - sx, ev.clientY - sy) > 5;
      if (cur.moved) {
        setDrag({ ...cur });
        setDropTarget(pinAt(ev.clientX, ev.clientY));
      }
    };
    const up = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setDrag(null);
      setDropTarget(null);
      const moved = cur.moved || Math.hypot(ev.clientX - sx, ev.clientY - sy) > 5;
      if (!moved) return;
      suppressClick.current = true;
      const to = pinAt(ev.clientX, ev.clientY);
      if (to != null && to !== cur.from) place(cur.signal, to);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const suppressClick = useRef(false);

  if (!device) {
    return <div className="pinout empty muted">
      No pin table for {design.device} {design.package}.
    </div>;
  }

  const sides = (device.sides ?? null) as Sides | null;
  const { W, H, X0, Y0, BW, BH, PITCH, pinW } = geometry(device.pin_count, sides);
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
        <svg viewBox={`0 0 ${W} ${H}`} role="img"
             width={fit ? undefined : W * 0.85} height={fit ? undefined : H * 0.85}
             aria-label={`${design.device} ${design.package} pinout`}>
          <rect x={X0} y={Y0} width={BW} height={BH} rx={plcc ? 18 : 4}
                className="pkg-body" />
          <circle cx={plcc ? W / 2 : X0 + 22}
                  cy={Y0 + 22} r={7} className="pkg-dot" />
          {/* small packages (GreenPAK STQFN-8/12/14): smaller name so it fits the body */}
          <text x={W / 2} y={H / 2 - 8} className="pkg-name"
                style={device.pin_count <= 14 ? { fontSize: 13 } : undefined}>{design.device}</text>
          <text x={W / 2} y={H / 2 + 16} className="pkg-sub"
                style={device.pin_count <= 14 ? { fontSize: 10 } : undefined}>{design.package}</text>
          {pins.map((p) => {
            const { side, idx } = placePin(design.package, p.num, device.pin_count, sides);
            const horiz = side === "top" || side === "bottom";
            // centre each side's pins along its edge
            const count = sides ? (side === "left" ? sides[0] : side === "bottom" ? sides[1]
                                   : side === "right" ? sides[2] : sides[3]) : device.pin_count / 4;
            const edge = horiz ? BW : BH;
            const along = (horiz ? X0 : Y0) + (edge - PITCH * count) / 2 + PITCH * (idx + 0.5);
            const w = horiz ? pinW : 26, h = horiz ? 26 : pinW;
            const x = horiz ? along - w / 2 : side === "left" ? X0 - w : X0 + BW;
            const y = horiz ? (side === "top" ? Y0 - h : Y0 + BH) : along - h / 2;
            // label outside the pin
            const lx = horiz ? along : side === "left" ? x - 6 : x + w + 6;
            const ly = horiz ? (side === "top" ? y - 6 : y + h + 6) : along;
            const anchor = horiz ? "start" : side === "left" ? "end" : "start";
            const rot = horiz ? (side === "top" ? `rotate(-90 ${lx} ${ly})` : `rotate(90 ${lx} ${ly})`) : undefined;
            const numX = horiz ? along : side === "left" ? X0 + 6 : X0 + BW - 6;
            const numY = horiz ? (side === "top" ? Y0 + 14 : Y0 + BH - 6) : along + 4;
            const label = p.port ? p.port.name : p.type === "power" ? p.role
                        : p.type === "nc" ? "NC"
                        : p.type === "jtag" || p.type === "reserved" ? p.role.split(" ")[0] : "";
            const sel = !!p.port && p.port.net === selectedNet;
            const dragging = !!drag?.moved && drag.from === p.num;
            const bad = !!drag?.moved && dropTarget === p.num && p.num !== drag.from &&
                        !!canDrop(p, drag.signal);
            const cls = ["pin", `t-${p.type}`, p.port ? `d-${p.port.direction}` : "free",
                         p.locked ? "locked" : "", sel ? "sel" : "", dragging ? "dragging" : "",
                         dropTarget === p.num ? (bad ? "nodrop" : "drop") : ""].join(" ");
            return (
              <g key={p.num} className={cls} data-pin={p.num}
                 onMouseEnter={() => setHover(p.num)} onMouseLeave={() => setHover(null)}
                 onPointerDown={(e) => startDrag(e, p)}
                 onClick={() => {
                   if (suppressClick.current) { suppressClick.current = false; return; }
                   if (p.port) { onSelectNet(sel ? null : p.port.net); return; }
                   // Free pin + a selected signal: lock the signal here.
                   const s = ports.find((x) => x.net === selectedNet);
                   if (!s || p.type === "power" || p.type === "nc") return;
                   place(s.name, p.num);
                 }}
                 onDragOver={(e) => { e.preventDefault(); setDropTarget(p.num); }}
                 onDragLeave={() => setDropTarget(null)}
                 onDrop={(e) => onDrop(e, p)}>
                <title>{`Pin ${p.num}: ${p.role}${p.port ? ` — ${p.port.name} (${p.port.direction})` : ""}${p.locked ? ", locked" : ""}`}</title>
                <rect x={x} y={y} width={w} height={h} rx={2} />
                <text x={numX} y={numY} className="pinno"
                      textAnchor={horiz ? "middle" : side === "left" ? "start" : "end"}>{p.num}</text>
                {label && (
                  <text x={lx} y={ly} className={`plabel${p.port ? " grab" : ""}`} textAnchor={anchor}
                        dominantBaseline="middle" transform={rot}>
                    {p.locked ? "🔒 " : ""}{label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {drag?.moved && (
          <div className="pin-ghost mono" style={{ left: drag.x + 12, top: drag.y + 8 }}>
            {drag.signal}{dropTarget && dropTarget !== drag.from ? ` → ${dropTarget}` : ""}
          </div>
        )}
        </div>
        <div className="pin-detail small">
          <button className="iconbtn small zoombtn" onClick={() => setZoom(fit ? "full" : "fit")}
                  title={fit ? "Draw at full size (scroll to move around)" : "Fit the whole package in the panel"}>
            {fit ? "Full size" : "Fit"}
          </button>{" "}
          {hp ? <>Pin <b>{hp.num}</b> · {hp.role}
                  {hp.port && <> · <span className="mono">{hp.port.name}</span> ({hp.port.direction}){hp.locked && " · locked"}</>}</>
              : <span className="muted">
                  Drag a pin's label (or a signal from the list) onto another pin to move it there;
                  onto a used pin to swap the two.
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
                    gen.macrocells.estimate > gen.macrocells.total ? " over" : ""}`}
                  title="Estimate; the per-chip breakdown is in the report panel. The fitter report has the real figure.">
              ≈{gen.macrocells.estimate}
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
          <button onClick={copyKicad} disabled={!gen?.ok || copying} data-testid="copy-kicad"
                  title="Copy the CPLD as a KiCad symbol with wires and net labels; paste it into your schematic with Ctrl+V">
            {copying ? "Copying…" : "Copy for KiCad"}
          </button>
        </div>
        {manual && (
          <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) setManual(null); }}>
            <div className="modal" role="dialog" aria-modal="true" aria-label="KiCad symbol">
              <div className="modal-head">
                <h2>KiCad symbol</h2>
                <button className="iconbtn" onClick={() => setManual(null)} aria-label="Close">×</button>
              </div>
              <p className="small">The clipboard isn't available here. Press Ctrl+C to copy the
                text below, then paste it into a KiCad schematic with Ctrl+V.</p>
              <textarea className="code kicad-text" readOnly value={manual} aria-label="KiCad schematic text"
                        ref={(t) => { if (t) { t.focus(); t.select(); } }} />
              <div className="modal-foot"><span className="spacer" />
                <button className="primary" onClick={() => setManual(null)}>Done</button></div>
            </div>
          </div>
        )}
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
