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

describe("variants in the editor model", () => {
  const base = () => ({ ...m.emptyDesign(), parts: { U4A: "74x377", U4B: "74x161", U5: "74x32" } });

  it("sets variants, keeps the active one valid, and clears them", () => {
    let d = m.setVariants(base(), { AxROM: ["U4A"], UxROM: ["U4B"] }, "pins");
    expect(d.variant).toBe("AxROM");
    expect(d.variant_mode).toBe("pins");
    expect(m.optionalChips(d)).toEqual({ U4A: ["AxROM"], U4B: ["UxROM"] });
    d = m.setActiveVariant(d, "UxROM");
    d = m.setVariants(d, { UxROM: ["U4B"], CNROM: [] });
    expect(d.variant).toBe("UxROM");
    d = m.setVariants(d, {});
    expect(d.variants).toBeUndefined();
  });

  it("follows chips being removed or renamed", () => {
    let d = m.setVariants(base(), { AxROM: ["U4A"], UxROM: ["U4B"] });
    d = m.renamePart(d, "U4B", "U9");
    expect(d.variants).toEqual({ AxROM: ["U4A"], UxROM: ["U9"] });
    d = m.removePart(d, "U4A");
    expect(d.variants).toEqual({ AxROM: [], UxROM: ["U9"] });
  });
});
