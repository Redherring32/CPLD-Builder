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

  it("numbers PQFP160 from the top of the left edge", () => {
    expect(placePin("PQFP160", 1, 160)).toEqual({ side: "left", idx: 0 });
    expect(placePin("PQFP160", 41, 160)).toEqual({ side: "bottom", idx: 0 });
    expect(placePin("PQFP160", 81, 160)).toEqual({ side: "right", idx: 39 });
    expect(placePin("PQFP160", 160, 160)).toEqual({ side: "top", idx: 0 });
  });
});
