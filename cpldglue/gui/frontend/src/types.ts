export type PinKind = "i" | "o" | "t" | "b" | "oc" | "gnd" | "vcc" | "nc";

export interface PartPin {
  number: string;
  name: string;
  kind: PinKind;
}

export interface PartUnit {
  symbol: string;          // and or nand nor xor not buf tri tri_not mux bidir block
  inputs: string[];
  outputs: string[];
  controls: string[];
  storage: number;
  group: string;
  name: string;
}

export interface Part {
  key: string;
  title: string;
  package: string;
  warning: string;
  pins: PartPin[];
  units: PartUnit[];
}

export interface NetNode {
  ref: string;
  pin: string;
}

export interface Net {
  name: string;
  nodes: NetNode[];
  external: boolean;
  const: number | null;
  named: boolean;
}

export interface LayoutEntry {
  x: number;
  y: number;
  rot?: number;
}

export interface Design {
  name: string;
  parts: Record<string, string>;
  nets: Record<string, Net>;
  device: string;
  package: string;
  pin_locks: Record<string, number>;
  keep_jtag: boolean;
  layout: Record<string, LayoutEntry>;
  // Variants ("fit one of" chips): variant name -> optional chips fitted in it
  variants?: Record<string, string[]>;
  variant_mode?: "build" | "pins";   // one .jed per variant, or VAR_SEL pins
  variant?: string;                  // variant shown / simulated in build mode
  variant_of?: string;
}

export interface ProjectInfo {
  path: string;
  recent?: string[];       // other recently opened projects
  mtime: number;
  error: string;
  design: Design;
}

export interface DeviceInfo {
  device: string;
  package: string;
  macrocells: number;
  io: number[];
  inputs: Record<string, number>;
  jtag: Record<string, number>;
  power: Record<string, string>;
  pin_count: number;
  nc?: number[];
  vcc?: number;
  kind?: "cpld" | "greenpak" | "gal" | "ice40" | "max7000";
  resources?: Record<string, number>;
  supply?: string;
  note?: string;
  out_only?: number[];
  no_oe?: number[];
  reserved?: Record<string, number>;
  pin_names?: Record<string, string>;
  style?: string;
  sides?: number[] | null;
}

export interface GenNet {
  external: boolean;
  const: number | null;
  port: string | null;
  direction: string | null;
  pin: number | null;
}

export interface GenPort {
  name: string;
  direction: "input" | "output" | "inout";
  net: string;
  drive?: string;          // outputs: "tri" (3-state), "oc", "" (push-pull)
  pin: number | null;
}

export interface GenResult {
  ok: boolean;
  ports: GenPort[];
  capacity: number | null;
  macrocells?: {
    outputs: number; storage: number; shared: number; estimate: number; total: number | null;
    // per chip: output pins it drives (shared buses split), flip-flops, and
    // flip-flops that sit at their own pin
    parts: Record<string, { outputs: number; storage: number; shared: number; estimate: number }>;
  } | null;
  nets: Record<string, GenNet>;
  unused?: Record<string, number[]>;     // ref -> indices of unused units
  errors: string[];
  warnings: string[];
  notes: string[];
  verilog: string;
  pin_file: string;
  report: string;
  error?: string;
}
