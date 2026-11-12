import type { DeviceInfo } from "./types";

/** How a device appears in the device pickers. */
export function deviceLabel(d: string, info: DeviceInfo | undefined): string {
  if (!info) return d;
  switch (info.kind) {
    case "greenpak": return `${d} · GreenPAK`;
    case "gal": return `${d} · GAL · ${info.macrocells} OLMC`;
    case "ice40": return `${d} · FPGA · ${info.resources?.lut ?? "?"} LUT · 3.3 V`;
    case "gowin": return `${d} · FPGA · ${info.resources?.lut ?? "?"} LUT · flash · 3.3 V`;
    case "max7000": return `${d} · ${info.macrocells} MC · MAX 7000S`;
    default:
      return `${d} · ${info.macrocells} MC${info.vcc !== undefined && info.vcc < 5 ? " · 3.3 V" : ""}`;
  }
}
