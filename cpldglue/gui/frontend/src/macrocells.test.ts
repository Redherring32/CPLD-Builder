import { describe, expect, it } from "vitest";
import { chipSlots, slotColor } from "./MacrocellBar";
import * as m from "./model";

describe("chip colors for the macrocell bar", () => {
  it("follow the chip's place in the project and fold into Other past eight", () => {
    let d = m.emptyDesign();
    for (let i = 1; i <= 10; i++) d = { ...d, parts: { ...d.parts, [`U${i}`]: "74x00" } };
    const slots = chipSlots(d);
    expect(slots.U1).toBe(1);
    expect(slots.U8).toBe(8);
    expect(slots.U9).toBe(0);
    expect(slots.U10).toBe(0);
    expect(slotColor(3)).toBe("var(--series-3)");
    expect(slotColor(0)).toBe("var(--series-other)");
  });

  it("never repaint the other chips when one is removed or added", () => {
    const d = { ...m.emptyDesign(), parts: { U1: "74x00", U2: "74x04", U3: "74x08" } };
    const before = chipSlots(d);
    const removed = chipSlots({ ...d, parts: { U1: "74x00", U3: "74x08" } }, before);
    expect(removed).toEqual({ U1: 1, U3: 3 });
    const added = chipSlots({ ...d, parts: { U1: "74x00", U3: "74x08", U9: "74x32" } }, removed);
    expect(added).toEqual({ U1: 1, U3: 3, U9: 2 });      // the freed slot is reused
  });
});
