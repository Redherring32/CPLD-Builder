import type { Design, LayoutEntry, Part } from "./types";

export const ROW_H = 26;
export const HEADER_H = 44;
export const CHIP_W = 220;
/** Room either side of the chip body for net labels (part of the node box,
 *  so fit-view and selection include the labels). */
export const GUTTER = 150;
export const NODE_W = CHIP_W + 2 * GUTTER;

export function chipHeight(part: Part): number {
  return HEADER_H + (part.pins.length / 2) * ROW_H + 12;
}

/** DIP pin placement: pins 1..n/2 down the left, n..n/2+1 down the right. */
export function pinSide(part: Part, number: string): { side: "left" | "right"; row: number } {
  const n = part.pins.length;
  const k = parseInt(number, 10);
  const half = n / 2;
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
