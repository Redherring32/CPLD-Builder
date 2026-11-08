import { createContext } from "react";
import type { MouseEvent } from "react";

/** What one chip pin is connected to, as drawn next to the pin. */
export interface PinNet {
  name: string;          // net name in the project
  label: string;         // short display text
  external: boolean;
  const: number | null;
  port: string | null;   // CPLD port name, if the net is a pin
  pin: number | null;    // CPLD pin number
}

export type Issue = "error" | "warning";

export interface NetCtx {
  pinNet: Record<string, PinNet>;    // "U7.2" -> net
  issues: Record<string, Issue>;     // "U7.2" -> problem from the report
  selectedNet: string | null;
  netValues: Record<string, number | null> | null;   // live simulation values
  unused: Record<string, number[]>;  // ref -> unused gate indices (from the generator)
  macrocells: Record<string, { estimate: number; slot: number }>;  // per chip
  select: (net: string | null) => void;
  onPinMenu: (e: MouseEvent, ref: string, pin: string) => void;
  onChipMenu: (e: MouseEvent, ref: string) => void;
}

export const NetContext = createContext<NetCtx>({
  pinNet: {}, issues: {}, selectedNet: null, netValues: null, unused: {}, macrocells: {}, select: () => {},
  onPinMenu: () => {}, onChipMenu: () => {},
});

export function shortNetName(name: string): string {
  return name.replace(/^\//, "").replace(/~\{([^}]*)\}/g, "/$1");
}

/** Pull "U7.12"-style pin references out of report messages. */
export function issuesFromReport(errors: string[], warnings: string[]): Record<string, Issue> {
  const out: Record<string, Issue> = {};
  const scan = (msgs: string[], level: Issue) => {
    for (const m of msgs)
      for (const hit of m.matchAll(/\b([A-Za-z_]\w*)\.(\d+)\b/g)) {
        const key = `${hit[1]}.${hit[2]}`;
        if (out[key] !== "error") out[key] = level;
      }
  };
  scan(warnings, "warning");
  scan(errors, "error");
  return out;
}
