/** Draws the gates inside a chip: gate symbols wired to their pins for
 *  simple logic and buffers, labelled blocks for flip-flops, decoders,
 *  counters and shift registers. Unused gates (nothing uses their outputs,
 *  so the generator leaves them out) are drawn faded. */
import type { ReactNode } from "react";
import type { Part } from "./types";
import { CHIP_W, HEADER_H, ROW_H, pinSide } from "./layout";

const EDGE = 24;                        // where wires leave the pin column
const BUBBLE = 3;
const INVERTED = new Set(["nand", "nor", "not", "tri_not"]);

type Side = "left" | "right";
interface PinPos { name: string; num: string; side: Side; row: number; y: number }

export interface ArtInfo {
  style: "gates" | "blocks";
  hidden: Set<string>;                  // pin numbers whose names the drawing replaces
}

const rowY = (row: number) => HEADER_H + row * ROW_H + ROW_H / 2;
const edgeX = (side: Side) => (side === "left" ? EDGE : CHIP_W - EDGE);

function pinPositions(part: Part): Record<string, PinPos> {
  const out: Record<string, PinPos> = {};
  for (const p of part.pins) {
    const { side, row } = pinSide(part, p.number);
    out[p.name] = { name: p.name, num: p.number, side, row, y: rowY(row) };
  }
  return out;
}

/** Control pins used by more than one unit (shared enables/selects/clocks). */
function sharedPins(part: Part): Set<string> {
  const count: Record<string, number> = {};
  for (const u of part.units) for (const c of u.controls) count[c] = (count[c] ?? 0) + 1;
  return new Set(Object.keys(count).filter((c) => count[c] > 1));
}

export function artInfo(part: Part): ArtInfo {
  if (!part.units?.length) return { style: "blocks", hidden: new Set() };
  const blocks = part.units.some((u) => u.symbol === "block");
  if (blocks) return { style: "blocks", hidden: new Set() };
  const pos = pinPositions(part);
  const shared = sharedPins(part);
  const hidden = new Set<string>();
  for (const u of part.units)
    for (const n of [...u.inputs, ...u.outputs, ...u.controls.filter((c) => !shared.has(c))])
      if (pos[n]) hidden.add(pos[n].num);
  return { style: "gates", hidden };
}

// ---- gate shapes, drawn pointing down (+y) around (0, 0) ------------------
function shape(sym: string, w: number, l: number): ReactNode {
  const h = w / 2, t = -l / 2, b = l / 2;
  const curve = l * 0.3;
  switch (sym) {
    case "and": case "nand":
      return <path d={`M${-h},${t} H${h} V${b - h} A${h},${h} 0 0 1 ${-h},${b - h} Z`} />;
    case "or": case "nor": case "xor":
      return <>
        <path d={`M${-h},${t} Q0,${t + curve} ${h},${t} Q${h},${b * 0.3} 0,${b} Q${-h},${b * 0.3} ${-h},${t} Z`} />
        {sym === "xor" && <path className="open" d={`M${-h},${t - 4} Q0,${t + curve - 4} ${h},${t - 4}`} />}
      </>;
    case "mux":
      return <path d={`M${-h},${t} H${h} L${h * 0.6},${b} H${-h * 0.6} Z`} />;
    case "bidir":
      return <>
        <path d={`M${-h},${t} H0 L${-h / 2},${b} Z`} />
        <path d={`M0,${b} H${h} L${h / 2},${t} Z`} />
      </>;
    default:                                          // not, buf, tri, tri_not
      return <path d={`M${-h},${t} H${h} L0,${b} Z`} />;
  }
}

/** y of the gate's input edge at offset x (OR-type gates have a curved back). */
function inputEdge(sym: string, x: number, w: number, l: number): number {
  const t = -l / 2;
  if (sym !== "or" && sym !== "nor" && sym !== "xor") return t;
  const s = (x + w / 2) / w;                          // 0..1 across the gate
  return t + 2 * s * (1 - s) * l * 0.3;
}

interface WireProps { d: string; pin: string; ref_: string }

export function GateArt({ refName, part, unused, wireClass }: {
  refName: string; part: Part; unused: number[];
  wireClass: (pinNum: string) => string;            // highlight / sim value
}) {
  const info = artInfo(part);
  const pos = pinPositions(part);
  const height = HEADER_H + (part.pins.length / 2) * ROW_H + 12;
  const dead = new Set(unused);
  const items: ReactNode[] = [];

  if (info.style === "blocks") {
    const shared = new Set<string>();
    const owner: Record<string, string> = {};
    const groups: { label: string; pins: string[]; idx: number[] }[] = [];
    part.units.forEach((u, i) => {
      const label = u.group || u.name;
      let g = groups.find((x) => x.label === label);
      if (!g) groups.push(g = { label, pins: [], idx: [] });
      g.idx.push(i);
      for (const n of [...u.inputs, ...u.controls, ...u.outputs]) {
        if (owner[n] !== undefined && owner[n] !== label) shared.add(n);
        owner[n] = label;
        if (!g.pins.includes(n)) g.pins.push(n);
      }
    });
    groups.forEach((g, gi) => {
      const own = g.pins.filter((n) => !shared.has(n) && pos[n]);
      if (!own.length) return;
      const rows = own.map((n) => pos[n].row);
      const sides = new Set(own.map((n) => pos[n].side));
      const top = HEADER_H + Math.min(...rows) * ROW_H + 2;
      const bottom = HEADER_H + (Math.max(...rows) + 1) * ROW_H - 2;
      const both = sides.size > 1;
      const x0 = both || sides.has("left") ? EDGE - 2 : CHIP_W / 2 + 3;
      const x1 = both || sides.has("right") ? CHIP_W - EDGE + 2 : CHIP_W / 2 - 3;
      const allDead = g.idx.every((i) => dead.has(i));
      const someDead = !allDead && g.idx.some((i) => dead.has(i));
      const title = allDead ? `${g.label}: unused, left out of the CPLD`
        : someDead ? `${g.label}: ${g.idx.filter((i) => dead.has(i)).map((i) => part.units[i].name).join(", ")} unused`
        : g.label;
      const lx = both ? CHIP_W / 2 : sides.has("left") ? x1 - 8 : x0 + 8;
      const ly = (top + bottom) / 2;
      items.push(
        <g key={`b${gi}`} className={`gblock${allDead ? " unused" : ""}`}>
          <title>{title}</title>
          <rect x={x0} y={top} width={x1 - x0} height={bottom - top} rx={4} />
          <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle"
                transform={both ? undefined : `rotate(-90 ${lx} ${ly})`}>
            {allDead ? "unused" : g.label}{someDead ? " *" : ""}
          </text>
        </g>);
    });
  } else {
    const shared = sharedPins(part);
    part.units.forEach((u, i) => {
      const out = pos[u.outputs[0]];
      const ins = u.inputs.map((n) => pos[n]).filter(Boolean);
      const ctrls = u.controls.filter((c) => !shared.has(c)).map((n) => pos[n]).filter(Boolean);
      if (!out || !ins.length) return;
      const wires: WireProps[] = [];
      const parts: ReactNode[] = [];
      const inv = INVERTED.has(u.symbol);
      const inRows = [...ins, ...ctrls].map((p) => p.row);
      // Straight across when every input is on the far side (octal buffers);
      // otherwise top-to-bottom like a datasheet drawing.
      const across = ins.every((p) => p.side !== out.side);
      const vertical = across ? null
                     : out.row > Math.max(...inRows) ? "down"
                     : out.row < Math.min(...inRows) ? "up" : null;
      const w = u.symbol === "not" || u.symbol === "buf" || u.symbol.startsWith("tri")
        ? 14 : Math.max(16, 7 * ins.length + 2);

      if (vertical) {
        const down = vertical === "down";
        const near = down ? Math.max(...inRows) : Math.min(...inRows);
        const gapTop = down ? rowY(near) + 4 : rowY(out.row) + 4 + (inv ? 2 * BUBBLE : 0);
        const gapBot = down ? rowY(out.row) - 4 - (inv ? 2 * BUBBLE : 0) : rowY(near) - 4;
        const l = Math.max(10, gapBot - gapTop);
        const cy = (gapTop + gapBot) / 2;
        const cx = out.side === "left" ? EDGE + 22 + w / 2 + (ctrls.length ? 0 : 6)
                                       : CHIP_W - EDGE - 22 - w / 2 - (ctrls.length ? 0 : 6);
        // Order inputs so their wires don't cross (see units.py docs).
        const L = ins.filter((p) => p.side === "left").sort((a, b) => down ? b.row - a.row : a.row - b.row);
        const R = ins.filter((p) => p.side === "right").sort((a, b) => down ? a.row - b.row : b.row - a.row);
        const ordered = [...L, ...R];
        ordered.forEach((p, k) => {
          const x = cx - w / 2 + (w * (k + 0.5)) / ordered.length;
          const local = inputEdge(u.symbol, x - cx, w, l);
          const ey = down ? cy + local : cy - local;
          wires.push({ d: `M${edgeX(p.side)},${p.y} H${x} V${ey}`, pin: p.num, ref_: refName });
        });
        const tip = down ? cy + l / 2 : cy - l / 2;
        const oy = down ? tip + (inv ? 2 * BUBBLE : 0) : tip - (inv ? 2 * BUBBLE : 0);
        if (inv) parts.push(<circle key="ob" cx={cx} cy={down ? tip + BUBBLE : tip - BUBBLE} r={BUBBLE} />);
        wires.push({ d: `M${cx},${oy} V${out.y} H${edgeX(out.side)}`, pin: out.num, ref_: refName });
        ctrls.forEach((p, k) => {
          // Enter the gate from the side away from the control's pin column.
          const dir = p.side === "left" ? 1 : -1;
          const sx = cx + dir * (w / 4 + 1);
          const jx = cx + dir * (w / 2 + 6 + 5 * k);
          const bub = p.name.endsWith("_n");
          if (bub) parts.push(<circle key={`cb${k}`} cx={sx + dir * BUBBLE} cy={cy} r={BUBBLE} />);
          wires.push({ d: `M${edgeX(p.side)},${p.y} H${jx} V${cy} H${sx + dir * (bub ? 2 * BUBBLE : 0)}`,
                       pin: p.num, ref_: refName });
        });
        parts.unshift(<g key="s" transform={`translate(${cx} ${cy})${down ? "" : " rotate(180)"}`}>
          {shape(u.symbol, w, l)}</g>);
      } else {
        // Horizontal: input on one side, output on the other.
        const right = out.side === "right";
        const p = ins[0];
        const l = 18;
        const cx = CHIP_W / 2;
        const cy = (p.y + out.y) / 2;
        const dir = right ? 1 : -1;
        const back = cx - dir * l / 2, tip = cx + dir * l / 2;
        const ox = tip + dir * (inv ? 2 * BUBBLE : 0);
        const jin = back - dir * 8, jout = ox + dir * 8;
        wires.push({ d: `M${edgeX(p.side)},${p.y} H${jin} V${cy} H${back}`, pin: p.num, ref_: refName });
        if (inv) parts.push(<circle key="ob" cx={tip + dir * BUBBLE} cy={cy} r={BUBBLE} />);
        wires.push({ d: `M${ox},${cy} H${jout} V${out.y} H${edgeX(out.side)}`, pin: out.num, ref_: refName });
        parts.unshift(<g key="s" transform={`translate(${cx} ${cy}) rotate(${right ? -90 : 90})`}>
          {shape(u.symbol, w, l)}</g>);
      }
      items.push(
        <g key={`u${i}`} className={`gate${dead.has(i) ? " unused" : ""}`}>
          <title>{`${u.name}${dead.has(i) ? ": unused, left out of the CPLD" : ""}`}</title>
          {wires.map((wp, k) => <path key={`w${k}`} d={wp.d} className={`wire ${wireClass(wp.pin)}`} />)}
          <g className="sym">{parts}</g>
        </g>);
    });
  }

  return (
    <svg className="gate-art" width={CHIP_W} height={height} aria-hidden="true">
      {items}
    </svg>
  );
}
