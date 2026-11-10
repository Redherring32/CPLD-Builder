import { describe, expect, it } from "vitest";
import { placePin } from "./PinoutView";

const PACKAGES: [string, number][] = [
  ["PLCC44", 44], ["TQFP44", 44], ["PLCC68", 68], ["PLCC84", 84],
  ["TQFP100", 100], ["PQFP100", 100], ["PQFP160", 160],
];

describe("placePin", () => {
  for (const [pkg, total] of PACKAGES) {
    it(`puts every ${pkg} pin in its own slot`, () => {
      const n = total / 4;
      const seen = new Set<string>();
      const perSide: Record<string, number> = {};
      for (let k = 1; k <= total; k++) {
        const { side, idx } = placePin(pkg, k, total);
        expect(idx).toBeGreaterThanOrEqual(0);
        expect(idx).toBeLessThan(n);
        expect(Number.isInteger(idx)).toBe(true);
        seen.add(`${side}:${idx}`);
        perSide[side] = (perSide[side] ?? 0) + 1;
      }
      expect(seen.size).toBe(total);
      expect(Object.values(perSide)).toEqual([n, n, n, n]);
    });
  }

  it("keeps the 44-pin layouts unchanged", () => {
    expect(placePin("PLCC44", 1, 44)).toEqual({ side: "top", idx: 5 });
    expect(placePin("PLCC44", 7, 44)).toEqual({ side: "left", idx: 0 });
    expect(placePin("PLCC44", 29, 44)).toEqual({ side: "right", idx: 10 });
    expect(placePin("PLCC44", 44, 44)).toEqual({ side: "top", idx: 6 });
    expect(placePin("TQFP44", 1, 44)).toEqual({ side: "left", idx: 0 });
    expect(placePin("TQFP44", 34, 44)).toEqual({ side: "top", idx: 10 });
  });

  it("numbers PLCC84 from the middle of the top edge, counter-clockwise", () => {
    expect(placePin("PLCC84", 1, 84)).toEqual({ side: "top", idx: 10 });   // centre
    expect(placePin("PLCC84", 11, 84)).toEqual({ side: "top", idx: 0 });   // top-left corner
    expect(placePin("PLCC84", 12, 84)).toEqual({ side: "left", idx: 0 });
    expect(placePin("PLCC84", 33, 84)).toEqual({ side: "bottom", idx: 0 });
    expect(placePin("PLCC84", 54, 84)).toEqual({ side: "right", idx: 20 }); // bottom-right
    expect(placePin("PLCC84", 75, 84)).toEqual({ side: "top", idx: 20 });   // top-right corner
    expect(placePin("PLCC84", 84, 84)).toEqual({ side: "top", idx: 11 });   // right of pin 1
  });

  it("lays out uneven sides (GreenPAK STQFN-20 and TSSOP-20)", () => {
    // STQFN-20: 6 down the left, 4 along the bottom, 6 up the right, 4 back along the top
    const s: [number, number, number, number] = [6, 4, 6, 4];
    expect(placePin("STQFN20", 1, 20, s)).toEqual({ side: "left", idx: 0 });
    expect(placePin("STQFN20", 7, 20, s)).toEqual({ side: "bottom", idx: 0 });
    expect(placePin("STQFN20", 11, 20, s)).toEqual({ side: "right", idx: 5 });
    expect(placePin("STQFN20", 16, 20, s)).toEqual({ side: "right", idx: 0 });
    expect(placePin("STQFN20", 17, 20, s)).toEqual({ side: "top", idx: 3 });
    expect(placePin("STQFN20", 20, 20, s)).toEqual({ side: "top", idx: 0 });
    // TSSOP-20: 1-10 down the left, 11-20 up the right
    const t: [number, number, number, number] = [10, 0, 10, 0];
    expect(placePin("TSSOP20", 10, 20, t)).toEqual({ side: "left", idx: 9 });
    expect(placePin("TSSOP20", 11, 20, t)).toEqual({ side: "right", idx: 9 });
    expect(placePin("TSSOP20", 20, 20, t)).toEqual({ side: "right", idx: 0 });
  });

  it("numbers PQFP160 from the top of the left edge", () => {
    expect(placePin("PQFP160", 1, 160)).toEqual({ side: "left", idx: 0 });
    expect(placePin("PQFP160", 41, 160)).toEqual({ side: "bottom", idx: 0 });
    expect(placePin("PQFP160", 81, 160)).toEqual({ side: "right", idx: 39 });
    expect(placePin("PQFP160", 160, 160)).toEqual({ side: "top", idx: 0 });
  });
});

import { moveSignal } from "./pinMove";
import type { GenPort } from "./types";

describe("moving signals between pins", () => {
  const ports: GenPort[] = [
    { name: "A", direction: "input", net: "A", pin: 4 },
    { name: "Y", direction: "output", net: "Y", pin: 5 },
    { name: "B", direction: "input", net: "B", pin: null },
  ];
  const inputOnly = new Set([2]);
  const problem = (pin: number, s: string) =>
    inputOnly.has(pin) && ports.find((p) => p.name === s)!.direction !== "input"
      ? `Pin ${pin} is input-only` : pin === 10 ? "Pin 10 is GND" : null;

  it("puts a signal on a free pin and locks it", () => {
    expect(moveSignal({}, ports, "A", 8, problem)).toEqual({ locks: { A: 8 } });
  });
  it("swaps with the signal already on the pin, locking both", () => {
    expect(moveSignal({ Z: 9 }, ports, "A", 5, problem))
      .toEqual({ locks: { Z: 9, A: 5, Y: 4 }, swapped: "Y" });
  });
  it("refuses pins the signal can't use", () => {
    expect(moveSignal({}, ports, "Y", 2, problem)).toEqual({ error: "Pin 2 is input-only" });
    expect(moveSignal({}, ports, "A", 10, problem)).toEqual({ error: "Pin 10 is GND" });
  });
  it("refuses a swap the other signal can't take", () => {
    inputOnly.add(4);
    const r = moveSignal({}, ports, "A", 5, problem);
    inputOnly.delete(4);
    expect(r).toEqual({ error: "Can't swap with Y: Pin 4 is input-only" });
  });
  it("an unplaced signal takes the pin and the other is placed again", () => {
    expect(moveSignal({ Y: 5 }, ports, "B", 5, problem)).toEqual({ locks: { B: 5 } });
  });
  it("dropping on its own pin just locks it", () => {
    expect(moveSignal({}, ports, "Y", 5, problem)).toEqual({ locks: { Y: 5 } });
  });
});
