import type { Design, LayoutEntry, Part } from "./types";

export const ROW_H = 26;
export const HEADER_H = 44;
export const CHIP_W = 220;
/** Room either side of the chip body for net labels (part of the node box,
 *  so fit-view and selection include the labels). */
export const GUTTER = 150;
export const NODE_W = CHIP_W + 2 * GUTTER;

// ---- single-gate parts, drawn as a logic symbol (GateSymbol.tsx) ----
export const SYM_W = 132;               // symbol body width (inside the chip column)
export const SYM_HEADER = 34;           // reference + part number above the symbol

/** Parts drawn as symbols: one gate or flip-flop, or two gates, in a small
 *  (up to 8-pin) package. */
export function isSymbolPart(part: Part): boolean {
  const us = part.units ?? [];
  if (!(us.length === 1 || (us.length === 2 && us.every((u) => u.symbol !== "block"))))
    return false;
  const named = new Set(us.flatMap((u) => [...u.inputs, ...u.outputs, ...u.controls]));
  return part.pins.length <= 8 &&
    part.pins.every((p) => ["gnd", "vcc", "nc"].includes(p.kind) || named.has(p.name));
}

export interface SymPin { side: "left" | "right"; y: number }   // y = row centre

/** Where each signal pin sits, and the symbol's height. Enables go above
 *  the inputs (they enter the buffer from the top); the output faces the
 *  middle of the inputs. */
export function symbolLayout(part: Part): { pins: Record<string, SymPin>; height: number } {
  const byName: Record<string, string> = {};
  for (const p of part.pins) byName[p.name] = p.number;
  const pins: Record<string, SymPin> = {};
  let top = SYM_HEADER;
  part.units.forEach((u, i) => {                   // a dual part stacks its gates
    if (i > 0) top += 10;
    const block = u.symbol === "block";
    const left = block ? [...u.inputs, ...u.controls] : [...u.controls, ...u.inputs];
    left.forEach((n, k) => { pins[byName[n]] = { side: "left", y: top + k * ROW_H + ROW_H / 2 }; });
    const ins = block ? left : u.inputs;
    const first = left.indexOf(ins[0]);
    const mid = top + ((first + left.length - 1) / 2) * ROW_H + ROW_H / 2;
    for (const o of u.outputs) pins[byName[o]] = { side: "right", y: mid };
    top += Math.max(left.length, 1) * ROW_H;
  });
  return { pins, height: top + 10 };
}

export function chipHeight(part: Part): number {
  if (isSymbolPart(part)) return symbolLayout(part).height;
  return HEADER_H + Math.ceil(part.pins.length / 2) * ROW_H + 12;
}

/** DIP/SOT pin placement: pins 1..ceil(n/2) down the left, the rest back up the right. */
export function pinSide(part: Part, number: string): { side: "left" | "right"; row: number } {
  const n = part.pins.length;
  const k = parseInt(number, 10);
  const half = Math.ceil(n / 2);           // SOT-23-5: 1-3 left, 5-4 right
  return k <= half ? { side: "left", row: k - 1 } : { side: "right", row: n - k };
}

/** Nearest spot at or to the right of `pos` where a new chip of `part`
 *  doesn't overlap an existing one. */
export function findFreeSpot(design: Design, parts: Record<string, Part>, part: Part,
                             pos: { x: number; y: number }): { x: number; y: number } {
  const placed = placeChips(design, parts);
  const boxes = Object.entries(placed).map(([ref, p]) => {
    const pt = parts[design.parts[ref]];
    return { x: p.x, y: p.y, w: NODE_W, h: pt ? chipHeight(pt) : 200 };
  });
  const h = chipHeight(part);
  const hits = (x: number, y: number) =>
    boxes.some((b) => x < b.x + b.w + 20 && x + NODE_W + 20 > b.x &&
                      y < b.y + b.h + 20 && y + h + 20 > b.y);
  let { x, y } = pos;
  for (let i = 0; i < 200 && hits(x, y); i++) {
    x += NODE_W / 2;
    if (i % 6 === 5) { x = pos.x; y += h / 2 + 40; }
  }
  return { x, y };
}

/** Saved positions, falling back to a grid ordered by reference. */
export function placeChips(design: Design, parts: Record<string, Part>): Record<string, LayoutEntry> {
  const out: Record<string, LayoutEntry> = {};
  const refs = Object.keys(design.parts).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  );
  const cols = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(refs.length))));
  const colW = NODE_W + 40;
  const rowHeights: number[] = [];
  refs.forEach((ref, i) => {
    const part = parts[design.parts[ref]];
    const row = Math.floor(i / cols);
    rowHeights[row] = Math.max(rowHeights[row] ?? 0, part ? chipHeight(part) : 200);
  });
  refs.forEach((ref, i) => {
    const saved = design.layout?.[ref];
    if (saved && typeof saved.x === "number") {
      out[ref] = saved;
      return;
    }
    const row = Math.floor(i / cols);
    const y = rowHeights.slice(0, row).reduce((s, h) => s + h + 80, 0);
    out[ref] = { x: (i % cols) * colW, y };
  });
  return out;
}
