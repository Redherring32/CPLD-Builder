/** Geometry checks for the gate drawings of every library part: wires of
 *  different pins never cross or touch, every wire ends at its pin's edge,
 *  and everything stays inside the chip body. */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GateArt, artInfo } from "./GateArt";
import { CHIP_W, SYM_W, chipHeight, isSymbolPart, symbolLayout } from "./layout";
import { SymbolArt } from "./GateSymbol";
import type { Part } from "./types";
import partsJson from "./fixtures/parts.json";

const parts = (partsJson as { parts: Part[] }).parts;

type Seg = { x1: number; y1: number; x2: number; y2: number; pin: string };

/** Parse "M x,y H x V y ..." paths (absolute, axis-aligned) into segments. */
function segments(d: string, pin: string): Seg[] {
  const out: Seg[] = [];
  let x = 0, y = 0;
  for (const m of d.matchAll(/([MHV])\s*([-\d.]+)(?:,([-\d.]+))?/g)) {
    const [cmd, a, b] = [m[1], parseFloat(m[2]), m[3] !== undefined ? parseFloat(m[3]) : NaN];
    if (cmd === "M") { x = a; y = b; continue; }
    const nx = cmd === "H" ? a : x, ny = cmd === "V" ? a : y;
    if (nx !== x || ny !== y) out.push({ x1: x, y1: y, x2: nx, y2: ny, pin });
    x = nx; y = ny;
  }
  return out;
}

function touches(a: Seg, b: Seg): boolean {
  const [ax1, ax2] = [Math.min(a.x1, a.x2), Math.max(a.x1, a.x2)];
  const [ay1, ay2] = [Math.min(a.y1, a.y2), Math.max(a.y1, a.y2)];
  const [bx1, bx2] = [Math.min(b.x1, b.x2), Math.max(b.x1, b.x2)];
  const [by1, by2] = [Math.min(b.y1, b.y2), Math.max(b.y1, b.y2)];
  const gap = 1.5;   // closer than this reads as connected
  return ax1 <= bx2 + gap && bx1 <= ax2 + gap && ay1 <= by2 + gap && by1 <= ay2 + gap;
}

function wiresOf(part: Part): Seg[] {
  const html = renderToStaticMarkup(
    <GateArt refName="U1" part={part} unused={[]} wireClass={(n) => `p${n}`} />);
  const segs: Seg[] = [];
  for (const m of html.matchAll(/<path d="([^"]+)" class="wire p(\d+)/g))
    segs.push(...segments(m[1], m[2]));
  return segs;
}

describe("gate drawings", () => {
  it("covers every part", () => {
    expect(parts.length).toBe(109);
    for (const p of parts) expect(p.units.length).toBeGreaterThan(0);
  });

  for (const part of parts) {
    if (artInfo(part).style !== "gates" || isSymbolPart(part)) continue;   // symbols: below
    it(`${part.key}: wires don't cross and stay inside the chip`, () => {
      const segs = wiresOf(part);
      const pins = new Set(segs.map((s) => s.pin));
      // every hidden (drawn) pin has a wire
      expect([...artInfo(part).hidden].sort()).toEqual([...pins].sort());
      const h = chipHeight(part);
      for (const s of segs) {
        for (const v of [s.x1, s.x2]) { expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(CHIP_W); }
        for (const v of [s.y1, s.y2]) { expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(h); }
      }
      const bad: string[] = [];
      for (let i = 0; i < segs.length; i++)
        for (let j = i + 1; j < segs.length; j++)
          if (segs[i].pin !== segs[j].pin && touches(segs[i], segs[j]))
            bad.push(`pin ${segs[i].pin} ↔ pin ${segs[j].pin}`);
      expect(bad).toEqual([]);
    });
  }

  const symbols = parts.filter(isSymbolPart);
  it("draws the single gates as symbols", () => {
    expect(symbols.map((p) => p.key).sort()).toEqual(
      parts.filter((p) => /^74x[12]G/.test(p.key)).map((p) => p.key).sort());
    expect(symbols.length).toBe(32);
    expect(isSymbolPart(parts.find((p) => p.key === "74x00")!)).toBe(false);
  });

  for (const part of symbols) {
    it(`${part.key}: symbol wires reach every pin, don't cross, stay inside`, () => {
      const html = renderToStaticMarkup(
        <SymbolArt part={part} unused={[]} wireClass={(n) => `p${n}`} />);
      const segs: Seg[] = [];
      for (const m of html.matchAll(/<path d="([^"]+)" class="wire p(\d+)/g))
        segs.push(...segments(m[1], m[2]));
      const lay = symbolLayout(part);
      const signal = part.pins.filter((p) => !["gnd", "vcc", "nc"].includes(p.kind)).map((p) => p.number);
      expect([...new Set(segs.map((s) => s.pin))].sort()).toEqual(signal.sort());
      expect(Object.keys(lay.pins).sort()).toEqual(signal.sort());
      expect(chipHeight(part)).toBe(lay.height);
      for (const s of segs) {
        for (const v of [s.x1, s.x2]) { expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(SYM_W); }
        for (const v of [s.y1, s.y2]) { expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThanOrEqual(lay.height); }
      }
      // each pin's wire starts at its own row, on its side
      for (const n of signal) {
        const p = lay.pins[n];
        const first = segs.find((s) => s.pin === n)!;
        const edge = p.side === "left" ? 22 : SYM_W - 22;
        expect([first.x1, first.x2]).toContain(edge);
        expect([first.y1, first.y2]).toContain(p.y);
      }
      const bad: string[] = [];
      for (let i = 0; i < segs.length; i++)
        for (let j = i + 1; j < segs.length; j++)
          if (segs[i].pin !== segs[j].pin && touches(segs[i], segs[j]))
            bad.push(`pin ${segs[i].pin} ↔ pin ${segs[j].pin}`);
      expect(bad).toEqual([]);
      if (/[12]G(00|02|04|06|10|14|27|240)$/.test(part.key)) expect(html).toContain("<circle");
    });
  }

  it("draws flip-flops, decoders and counters as blocks", () => {
    for (const key of ["74x74", "74x138", "74x139", "74x153", "74x161", "74x273", "74x595", "4021"])
      expect(artInfo(parts.find((p) => p.key === key)!).style).toBe("blocks");
  });

  it("fades unused gates", () => {
    const or = parts.find((p) => p.key === "74x32")!;
    const html = renderToStaticMarkup(<GateArt refName="U1" part={or} unused={[1, 2, 3]} wireClass={() => ""} />);
    expect(html.match(/class="gate unused"/g)?.length).toBe(3);
    expect(html.match(/class="gate"/g)?.length).toBe(1);
  });
});
