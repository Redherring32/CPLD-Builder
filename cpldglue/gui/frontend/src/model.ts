/**
 * Editing operations on a Design. Every function is pure: it returns a new
 * Design and never mutates its input, so undo/redo is just a list of
 * snapshots.
 */
import type { Design, Net, NetNode } from "./types";

export const GND_RE = /^\/?(GND|VSS|DGND|AGND|0)$/i;
export const VCC_RE = /^\/?(VCC|VDD|\+5V|\+3V3|\+3\.3V|5V|1)$/i;

export function emptyDesign(name = "glue"): Design {
  return {
    name, parts: {}, nets: {}, device: "ATF1502AS", package: "PLCC44",
    pin_locks: {}, keep_jtag: true, layout: {},
  };
}

function clone(d: Design): Design {
  return {
    ...d,
    parts: { ...d.parts },
    nets: Object.fromEntries(
      Object.entries(d.nets).map(([k, n]) => [k, { ...n, nodes: n.nodes.map((x) => ({ ...x })) }]),
    ),
    pin_locks: { ...d.pin_locks },
    layout: Object.fromEntries(Object.entries(d.layout ?? {}).map(([k, v]) => [k, { ...v }])),
  };
}

export function constForName(name: string): number | null {
  if (GND_RE.test(name)) return 0;
  if (VCC_RE.test(name)) return 1;
  return null;
}

/** A net name must work in a .cg file and as a Verilog-ish label. */
export function validNetName(name: string): string | null {
  if (!name.trim()) return "Name can't be empty";
  if (/[\s:#]/.test(name)) return "No spaces, ':' or '#'";
  return null;
}

export const pinKey = (n: NetNode) => `${n.ref}.${n.pin}`;

export function netOfPin(d: Design, ref: string, pin: string): Net | undefined {
  return Object.values(d.nets).find((n) => n.nodes.some((x) => x.ref === ref && x.pin === pin));
}

export function nextRef(d: Design, prefix = "U"): string {
  let i = 1;
  while (`${prefix}${i}` in d.parts) i++;
  return `${prefix}${i}`;
}

export function nextNetName(d: Design): string {
  let i = 1;
  while (`N${i}` in d.nets) i++;
  return `N${i}`;
}

// ---------------------------------------------------------------------------
// Chips
// ---------------------------------------------------------------------------
export function addPart(d: Design, key: string, pos: { x: number; y: number }, ref?: string): Design {
  const out = clone(d);
  const r = ref ?? nextRef(d);
  if (r in out.parts) throw new Error(`${r} already exists`);
  out.parts[r] = key;
  out.layout[r] = { x: Math.round(pos.x), y: Math.round(pos.y) };
  return out;
}

export function removePart(d: Design, ref: string): Design {
  const out = clone(d);
  delete out.parts[ref];
  delete out.layout[ref];
  for (const [name, net] of Object.entries(out.nets)) {
    net.nodes = net.nodes.filter((n) => n.ref !== ref);
    if (!net.nodes.length) delete out.nets[name];
  }
  return out;
}

export function movePart(d: Design, ref: string, pos: { x: number; y: number }): Design {
  const out = clone(d);
  out.layout[ref] = { ...out.layout[ref], x: Math.round(pos.x), y: Math.round(pos.y) };
  return out;
}

export function renamePart(d: Design, ref: string, newRef: string): Design {
  if (ref === newRef) return d;
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(newRef)) throw new Error("Reference must be like U12");
  if (newRef in d.parts) throw new Error(`${newRef} already exists`);
  const out = clone(d);
  out.parts = Object.fromEntries(Object.entries(out.parts).map(([k, v]) => [k === ref ? newRef : k, v]));
  if (out.layout[ref]) { out.layout[newRef] = out.layout[ref]; delete out.layout[ref]; }
  for (const net of Object.values(out.nets))
    for (const n of net.nodes) if (n.ref === ref) n.ref = newRef;
  return out;
}

// ---------------------------------------------------------------------------
// Nets
// ---------------------------------------------------------------------------
function detach(out: Design, ref: string, pin: string): void {
  for (const [name, net] of Object.entries(out.nets)) {
    const before = net.nodes.length;
    net.nodes = net.nodes.filter((n) => !(n.ref === ref && n.pin === pin));
    if (net.nodes.length !== before && !net.nodes.length) delete out.nets[name];
  }
}

/** Connect two pins. Joins existing nets; the first pin's net name wins,
 *  unless only the second pin's net carries a real (user) name. */
export function connect(d: Design, a: NetNode, b: NetNode): Design {
  if (a.ref === b.ref && a.pin === b.pin) return d;
  const na = netOfPin(d, a.ref, a.pin);
  const nb = netOfPin(d, b.ref, b.pin);
  if (na && nb && na.name === nb.name) return d;
  const out = clone(d);
  if (!na && !nb) {
    const name = nextNetName(d);
    out.nets[name] = { name, nodes: [{ ...a }, { ...b }], external: false, const: null, named: false };
    return out;
  }
  if (na && !nb) { out.nets[na.name].nodes.push({ ...b }); return out; }
  if (!na && nb) { out.nets[nb.name].nodes.push({ ...a }); return out; }
  // Merge two nets.
  let keep = out.nets[na!.name], drop = out.nets[nb!.name];
  if (!keep.named && drop.named) [keep, drop] = [drop, keep];
  keep.nodes.push(...drop.nodes);
  keep.external = keep.external || drop.external;
  keep.const = keep.const ?? drop.const;
  delete out.nets[drop.name];
  return out;
}

export function disconnectPin(d: Design, ref: string, pin: string): Design {
  const out = clone(d);
  detach(out, ref, pin);
  return out;
}

export function deleteNet(d: Design, name: string): Design {
  const out = clone(d);
  delete out.nets[name];
  return out;
}

export function renameNet(d: Design, name: string, newName: string): Design {
  if (name === newName) return d;
  const err = validNetName(newName);
  if (err) throw new Error(err);
  if (newName in d.nets) throw new Error(`A net called ${newName} already exists`);
  const out = clone(d);
  const net = out.nets[name];
  delete out.nets[name];
  const c = constForName(newName);
  out.nets = { ...out.nets, [newName]: { ...net, name: newName, named: true, const: c ?? net.const } };
  const oldSig = sanitize(name), newSig = sanitize(newName);
  if (oldSig !== newSig && oldSig in out.pin_locks && !(newSig in out.pin_locks)) {
    out.pin_locks[newSig] = out.pin_locks[oldSig];
    delete out.pin_locks[oldSig];
  }
  return out;
}

// ---------------------------------------------------------------------------
// Signal names and pin locks
// ---------------------------------------------------------------------------
const VERILOG_KEYWORDS = new Set(`always and assign begin buf case default else end
endcase endmodule for function if initial inout input integer module nand
negedge nor not or output parameter posedge reg supply0 supply1 tri wire xor
xnor generate genvar localparam signed`.split(/\s+/));

/** Same as cpldglue.generate.sanitize: net name -> CPLD signal name. */
export function sanitize(name: string): string {
  let s = name.replace(/^\/+/, "");
  const neg = s.includes("~{") || s.startsWith("~");
  s = s.replace(/~\{([^}]*)\}/g, "$1").replace(/^~+/, "");
  s = s.replace(/[^A-Za-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "") || "net";
  if (neg) s += "_n";
  if (/^[0-9]/.test(s)) s = "s" + s;
  if (VERILOG_KEYWORDS.has(s.toLowerCase())) s += "_";
  return s;
}

export function lockPin(d: Design, signal: string, pin: number): Design {
  const out = clone(d);
  for (const [s, p] of Object.entries(out.pin_locks)) if (p === pin) delete out.pin_locks[s];
  out.pin_locks[signal] = pin;
  return out;
}

export function unlockPin(d: Design, signal: string): Design {
  if (!(signal in d.pin_locks)) return d;
  const out = clone(d);
  delete out.pin_locks[signal];
  return out;
}

export function setLocks(d: Design, locks: Record<string, number>): Design {
  const out = clone(d);
  out.pin_locks = { ...locks };
  return out;
}

export function setExternal(d: Design, name: string, external: boolean): Design {
  const out = clone(d);
  out.nets[name].external = external;
  return out;
}

export function setConst(d: Design, name: string, value: number | null): Design {
  const out = clone(d);
  out.nets[name].const = value;
  return out;
}

/** Tie a pin to the GND (0) or VCC (1) net, creating that net if needed. */
export function tiePin(d: Design, ref: string, pin: string, value: 0 | 1): Design {
  const out = clone(d);
  detach(out, ref, pin);
  const existing = Object.values(out.nets).find((n) => n.const === value);
  if (existing) {
    existing.nodes.push({ ref, pin });
  } else {
    const name = value ? "VCC" : "GND";
    out.nets[name] = { name, nodes: [{ ref, pin }], external: false, const: value, named: true };
  }
  return out;
}

/** Give a pin its own external net (a CPLD pin), named after the pin. */
export function makeExternal(d: Design, ref: string, pin: string, suggested: string): Design {
  const cur = netOfPin(d, ref, pin);
  if (cur) return setExternal(d, cur.name, true);
  const out = clone(d);
  let name = suggested.replace(/[\s:#]/g, "_") || `${ref}_${pin}`;
  let i = 2;
  while (name in out.nets) name = `${suggested}_${i++}`;
  out.nets[name] = { name, nodes: [{ ref, pin }], external: true, const: null, named: true };
  return out;
}

export function setDesignField<K extends "name" | "device" | "package" | "keep_jtag">(
  d: Design, key: K, value: Design[K],
): Design {
  const out = clone(d);
  out[key] = value;
  return out;
}

// ---------------------------------------------------------------------------
// Comparison
// ---------------------------------------------------------------------------
/** Order-independent description of a design's logic (ignores layout). */
export function canonical(d: Design): string {
  const nets = Object.values(d.nets)
    .map((n) => [n.name, n.external, n.const, n.nodes.map(pinKey).sort()] as const)
    .sort((a, b) => a[0].localeCompare(b[0]));
  const parts = Object.entries(d.parts).sort(([a], [b]) => a.localeCompare(b));
  return JSON.stringify({ name: d.name, device: d.device, package: d.package,
                          jtag: d.keep_jtag, parts, nets,
                          locks: Object.entries(d.pin_locks).sort() });
}

// ---------------------------------------------------------------------------
// Undo / redo
// ---------------------------------------------------------------------------
export interface History {
  past: Design[];
  present: Design;
  future: Design[];
}

export const LIMIT = 200;

export function historyInit(d: Design): History {
  return { past: [], present: d, future: [] };
}

export function historyPush(h: History, d: Design): History {
  if (d === h.present) return h;
  return { past: [...h.past, h.present].slice(-LIMIT), present: d, future: [] };
}

export function historyUndo(h: History): History {
  if (!h.past.length) return h;
  return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1],
           future: [h.present, ...h.future] };
}

export function historyRedo(h: History): History {
  if (!h.future.length) return h;
  return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1) };
}
