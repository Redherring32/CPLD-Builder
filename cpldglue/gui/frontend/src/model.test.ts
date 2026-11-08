import { describe, expect, it } from "vitest";
import * as m from "./model";
import type { Design } from "./types";
import tinytendo from "./fixtures/tinytendo.json";

const TT = tinytendo as unknown as Design;

/** Rebuild a design using only the operations the editor UI performs. */
function rebuildLikeAUser(target: Design): Design {
  let d = m.emptyDesign(target.name);
  d = m.setDesignField(d, "device", target.device);
  d = m.setDesignField(d, "package", target.package);
  Object.entries(target.parts).forEach(([ref, key], i) => {
    d = m.addPart(d, key, { x: i * 400, y: 0 }, ref);
  });
  for (const net of Object.values(target.nets)) {
    if (net.const !== null) {
      for (const n of net.nodes) d = m.tiePin(d, n.ref, n.pin, net.const as 0 | 1);
      continue;
    }
    const [first, ...rest] = net.nodes;
    if (!rest.length) {
      d = m.makeExternal(d, first.ref, first.pin, net.name);
      if (!net.external) d = m.setExternal(d, net.name, false);
      continue;
    }
    for (const n of rest) d = m.connect(d, first, n);
    const made = m.netOfPin(d, first.ref, first.pin)!;
    d = m.renameNet(d, made.name, net.name);
    if (net.external) d = m.setExternal(d, net.name, true);
  }
  return d;
}

describe("editing model", () => {
  it("rebuilds the TinyTendo example exactly", () => {
    const d = rebuildLikeAUser(TT);
    expect(m.canonical(d)).toBe(m.canonical(TT));
  });

  it("never mutates its input", () => {
    const before = JSON.stringify(TT);
    m.removePart(TT, "U8");
    m.connect(TT, { ref: "U7", pin: "6" }, { ref: "U8", pin: "9" });
    m.renameNet(TT, "M2", "PHI2");
    m.tiePin(TT, "U7", "6", 1);
    expect(JSON.stringify(TT)).toBe(before);
  });

  it("connect creates, extends and merges nets", () => {
    let d = m.addPart(m.addPart(m.emptyDesign(), "74x00", { x: 0, y: 0 }), "74x04", { x: 0, y: 0 });
    d = m.connect(d, { ref: "U1", pin: "3" }, { ref: "U2", pin: "1" });
    expect(Object.keys(d.nets)).toEqual(["N1"]);
    expect(d.nets.N1.named).toBe(false);
    d = m.connect(d, { ref: "U1", pin: "4" }, { ref: "U2", pin: "3" });
    d = m.renameNet(d, "N2", "CLK");
    d = m.connect(d, { ref: "U2", pin: "1" }, { ref: "U2", pin: "3" });   // merge N1 into CLK
    expect(Object.keys(d.nets)).toEqual(["CLK"]);
    expect(d.nets.CLK.nodes.map(m.pinKey).sort()).toEqual(["U1.3", "U1.4", "U2.1", "U2.3"]);
  });

  it("removing a chip removes its pins and empty nets", () => {
    const d = m.removePart(TT, "U8");
    expect("U8" in d.parts).toBe(false);
    expect("4017-D0" in d.nets).toBe(false);              // only U8 was on it
    expect(d.nets["CPU-D0"].nodes.map(m.pinKey)).toEqual(["U9.3"]);
    expect(Object.values(d.nets).every((n) => n.nodes.every((x) => x.ref !== "U8"))).toBe(true);
  });

  it("disconnecting the last pin deletes the net", () => {
    const d = m.disconnectPin(TT, "U7", "14");
    expect("M2" in d.nets).toBe(false);
  });

  it("rename validates and sets power constants", () => {
    expect(() => m.renameNet(TT, "M2", "bad name")).toThrow();
    expect(() => m.renameNet(TT, "M2", "CPU-A13")).toThrow(/already exists/);
    const d = m.renameNet(TT, "M2", "VCC2");
    expect(d.nets.VCC2.const).toBeNull();
    const g = m.renameNet(m.deleteNet(TT, "GND"), "M2", "GND");
    expect(g.nets.GND.const).toBe(0);
  });

  it("tiePin moves a pin onto the existing power net", () => {
    const d = m.tiePin(TT, "U7", "14", 0);
    expect(d.nets.GND.nodes.map(m.pinKey)).toContain("U7.14");
    expect("M2" in d.nets).toBe(false);
  });

  it("renamePart updates nets and layout", () => {
    let d: Design = { ...TT, layout: { U7: { x: 5, y: 6 } } };
    d = m.renamePart(d, "U7", "U70");
    expect(d.parts.U70).toBe("74x139");
    expect(d.layout.U70).toEqual({ x: 5, y: 6 });
    expect(d.nets.M2.nodes[0].ref).toBe("U70");
    expect(() => m.renamePart(d, "U8", "U9")).toThrow();
  });

  it("undo and redo walk the history", () => {
    let h = m.historyInit(m.emptyDesign());
    const a = m.addPart(h.present, "74x00", { x: 0, y: 0 });
    h = m.historyPush(h, a);
    const b = m.addPart(a, "74x04", { x: 0, y: 0 });
    h = m.historyPush(h, b);
    h = m.historyUndo(h);
    expect(h.present).toBe(a);
    h = m.historyUndo(h);
    expect(Object.keys(h.present.parts)).toEqual([]);
    h = m.historyRedo(m.historyRedo(h));
    expect(h.present).toBe(b);
    h = m.historyUndo(h);
    h = m.historyPush(h, m.addPart(a, "74x32", { x: 0, y: 0 }));
    expect(h.future).toEqual([]);                          // new edit drops redo
  });
});

describe("pin locks", () => {
  it("sanitize matches the Python generator", () => {
    // Expected values produced by cpldglue.generate.sanitize
    const py: Record<string, string> = {
      "/CPU-A13": "CPU_A13", "/WRAM-~{CE}": "WRAM_CE_n", "/~{ROMSEL}": "ROMSEL_n",
      "/4016-D0": "s4016_D0", "input": "input_", "~RESET": "RESET_n",
      "Net-(U7A-E)": "Net_U7A_E", "PPU-~{A13}": "PPU_A13_n", "a.b": "a_b",
      "__x__": "x", "reg": "reg_", "---": "net",
    };
    for (const [k, v] of Object.entries(py)) expect(m.sanitize(k)).toBe(v);
  });

  it("lock, move and unlock", () => {
    let d = m.lockPin(TT, "CPU_A13", 33);
    d = m.lockPin(d, "M2", 33);                    // taking a pin evicts the old lock
    expect(d.pin_locks).toEqual({ M2: 33 });
    d = m.unlockPin(d, "M2");
    expect(d.pin_locks).toEqual({});
    expect(m.unlockPin(d, "nope")).toBe(d);
  });

  it("renaming a net carries its lock", () => {
    let d = m.lockPin(TT, "WRAM_CE_n", 20);
    d = m.renameNet(d, "WRAM-~{CE}", "RAM_SEL");
    expect(d.pin_locks).toEqual({ RAM_SEL: 20 });
  });
});
