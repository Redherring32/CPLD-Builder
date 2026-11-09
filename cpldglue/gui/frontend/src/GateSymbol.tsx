/** Single and dual gate parts (74x1G00, 74x2G04 ...) are drawn as their logic
 *  symbols instead of a chip: inputs on the left, the output on the right, an
 *  output enable on top of the buffer, bubbles for inverting outputs and
 *  active-low enables. A dual part stacks its two gates. Power pins aren't
 *  drawn (the symbol implies them). */
import type { ReactNode } from "react";
import type { Part, PartUnit } from "./types";
import { ROW_H, SYM_W, symbolLayout, type SymPin } from "./layout";
import { gateShape, gateInputEdge } from "./GateArt";

const EDGE = 22;                        // where wires leave the pin column
const BUBBLE = 3;
const INVERTED = new Set(["nand", "nor", "not", "tri_not"]);

interface Drawn { wires: { d: string; pin: string }[]; sym: ReactNode[] }

function unitArt(part: Part, u: PartUnit, key: string, pins: Record<string, SymPin>,
                 num: Record<string, string>): Drawn {
  const wires: Drawn["wires"] = [];
  const sym: ReactNode[] = [];
  const outPin = num[u.outputs[0]];
  const cy = pins[outPin].y;
  const cx = SYM_W / 2;
  const schmitt = /schmitt/i.test(part.title);
  const openDrain = part.pins.some((p) => p.kind === "oc");

  if (u.symbol === "block") {                       // D flip-flop
    const ys = [...u.inputs, ...u.controls].map((n) => pins[num[n]].y);
    const top = Math.min(...ys, cy) - ROW_H / 2 + 3, bot = Math.max(...ys, cy) + ROW_H / 2 - 3;
    const x0 = cx - 24, x1 = cx + 24;
    sym.push(<rect key={`${key}box`} x={x0} y={top} width={x1 - x0} height={bot - top} rx={2} />);
    for (const n of u.inputs) {
      const y = pins[num[n]].y;
      wires.push({ d: `M${EDGE},${y} H${x0}`, pin: num[n] });
      sym.push(<text key={`${key}l${n}`} x={x0 + 5} y={y} dominantBaseline="middle">
        {n.replace(/\d+$/, "").toUpperCase()}</text>);
    }
    for (const n of u.controls) {
      const y = pins[num[n]].y;
      wires.push({ d: `M${EDGE},${y} H${x0}`, pin: num[n] });
      sym.push(<path key={`${key}c${n}`} className="open" d={`M${x0},${y - 5} L${x0 + 7},${y} L${x0},${y + 5}`} />);
    }
    const inv = u.outputs[0].endsWith("_n");
    sym.push(<text key={`${key}q`} x={x1 - 5} y={cy} textAnchor="end" dominantBaseline="middle"
                   className={inv ? "overbar" : ""}>Q</text>);
    wires.push({ d: `M${x1},${cy} H${SYM_W - EDGE}`, pin: outPin });
    return { wires, sym };
  }
  const n = u.inputs.length;
  const buffer = n === 1;
  const w = buffer ? 24 : 12 * n + 8;               // width across the signal
  const l = buffer ? 28 : Math.max(34, Math.round(w * 0.85));   // length along it
  const back = cx - l / 2, tip = cx + l / 2;
  const inv = INVERTED.has(u.symbol);
  // gateShape draws pointing down; rotate(-90) points it right.
  sym.push(<g key={`${key}s`} transform={`translate(${cx} ${cy}) rotate(-90)`}>{gateShape(u.symbol, w, l)}</g>);
  if (inv) sym.push(<circle key={`${key}ob`} cx={tip + BUBBLE} cy={cy} r={BUBBLE} />);
  const ox = tip + (inv ? 2 * BUBBLE : 0);
  wires.push({ d: `M${ox},${cy} H${SYM_W - EDGE}`, pin: outPin });
  const jx = back - 10;
  u.inputs.forEach((name, k) => {
    const y = pins[num[name]].y;
    const ey = n === 1 ? cy : cy + (k - (n - 1) / 2) * (w / (n + 0.5));
    // local x across the gate is -(global y - cy) after the rotation
    const ex = cx + gateInputEdge(u.symbol, cy - ey, w, l);
    wires.push({ d: n === 1 && y === cy ? `M${EDGE},${y} H${ex}`
                                        : `M${EDGE},${y} H${jx} V${ey} H${ex}`, pin: num[name] });
  });
  u.controls.forEach((name) => {                    // output enable, into the top
    const y = pins[num[name]].y;
    const bub = name.endsWith("_n");
    const top = cy - w / 4;                         // triangle edge at its middle
    const ey = top - (bub ? 2 * BUBBLE : 0);
    if (bub) sym.push(<circle key={`${key}cb`} cx={cx} cy={top - BUBBLE} r={BUBBLE} />);
    wires.push({ d: `M${EDGE},${y} H${cx} V${ey}`, pin: num[name] });
  });
  if (schmitt) {                                    // hysteresis glyph
    const s = 4, gx = cx - (buffer ? 5 : 3);
    sym.push(<path key={`${key}h`} className="open glyph"
                   d={`M${gx - s},${cy + s / 2} H${gx + s / 2} V${cy - s / 2} M${gx - s / 2},${cy + s / 2} V${cy - s / 2} H${gx + s}`} />);
  }
  if (openDrain) {                                  // open-drain mark next to the output
    const gx = ox + 9, gy = cy - 9;
    sym.push(<path key={`${key}od`} className="open glyph"
                   d={`M${gx},${gy - 3} L${gx + 3},${gy} L${gx},${gy + 3} L${gx - 3},${gy} Z M${gx - 3},${gy + 3} H${gx + 3}`} />);
  }
  return { wires, sym };
}

export function SymbolArt({ part, unused, wireClass }: {
  part: Part; unused: number[]; wireClass: (pinNum: string) => string;
}) {
  const { pins, height } = symbolLayout(part);
  const num: Record<string, string> = {};
  for (const p of part.pins) num[p.name] = p.number;
  const dead = new Set(unused);
  return (
    <svg className="gate-art symbol-art" width={SYM_W} height={height} aria-hidden="true">
      {part.units.map((u, i) => {
        const { wires, sym } = unitArt(part, u, `u${i}`, pins, num);
        return (
          <g key={i} className={dead.has(i) ? "unused" : undefined}>
            <title>{`${u.name}${dead.has(i) ? ": unused, left out" : ""}`}</title>
            {wires.map((wp, k) => <path key={`w${k}`} d={wp.d} className={`wire ${wireClass(wp.pin)}`} />)}
            <g className="sym">{sym}</g>
          </g>);
      })}
    </svg>
  );
}
