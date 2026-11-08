"""Export the CPLD as a KiCad symbol, wired up with net labels.

`clipboard()` returns schematic items in the format KiCad's schematic
editor copies to the clipboard (a lib_symbols block, then the placed symbol,
wires, labels and no-connect flags). Paste it into a schematic with Ctrl+V.
`library()` returns the symbol alone as a .kicad_sym library.

Styling follows the TinyTendo schematic: 5.08 mm pins on a 2.54 mm grid,
a short horizontal wire from each pin, and a local label (1.27 mm text)
anchored at the wire's outer end with its text lying along the wire towards
the pin. Power pins are wired to VCC / GND labels the same way.

Pins:
  used signals          the net's label (input / output / 3-state / bidirectional)
  JTAG (when reserved)  labels TDI TMS TCK TDO, for the programming header
  unused input-only     tied to GND (CMOS inputs must not float)
  unused I/O            no-connect flag
  VCC / GND             VCC / GND labels (+3V3 for the 3.3 V ASV parts)
  NC (some packages)    no-connect pins
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import devices
from .design import Design
from .generate import Result, generate, sanitize

GRID = 2.54
PIN_LEN = 5.08
FONT = 1.27
ORIGIN = (101.6, 101.6)          # where the symbol lands, schematic mm

FOOTPRINTS = {
    "PLCC44": "Package_LCC:PLCC-44_16.6x16.6mm_P1.27mm",
    "PLCC68": "Package_LCC:PLCC-68_24.2x24.2mm_P1.27mm",
    "PLCC84": "Package_LCC:PLCC-84_29.3x29.3mm_P1.27mm",
    "TQFP44": "Package_QFP:TQFP-44_10x10mm_P0.8mm",
    "TQFP100": "Package_QFP:TQFP-100_14x14mm_P0.5mm",
    "PQFP100": "Package_QFP:PQFP-100_14x20mm_P0.65mm",
    "PQFP160": "Package_QFP:PQFP-160_28x28mm_P0.65mm",
}


@dataclass
class SymPin:
    number: int
    name: str
    etype: str                    # KiCad electrical type
    label: Optional[str] = None   # net label to wire it to
    no_connect: bool = False      # put a no-connect flag on it


@dataclass
class Export:
    name: str                     # symbol name (no library prefix)
    clipboard: str                # paste into a schematic
    library: str                  # .kicad_sym
    warnings: List[str] = field(default_factory=list)
    labels: int = 0


def label_text(net: str) -> str:
    """KiCad net name -> local label text: drop the sheet path ('/CPU-A13')."""
    return net.rsplit("/", 1)[-1] if net.startswith("/") else net


def _visible_len(text: str) -> int:
    return len(re.sub(r"[~_^]\{([^}]*)\}", r"\1", text))


def _pins(design: Design, r: Result) -> Tuple[List[SymPin], List[SymPin], List[str]]:
    """Left and right pin columns (None entries are gaps), plus warnings."""
    dev, pkg = devices.get_package(design.device, design.package)
    warnings: List[str] = []
    by_pin = {r.pins[p.name]: p for p in r.ports if p.name in r.pins}
    inputs, outputs = [], []
    for num in sorted(by_pin):
        p = by_pin[num]
        text = label_text(p.net)
        if re.match(r"(unconnected-|Net-\()", text):
            warnings.append(f"net {p.net} has no label in KiCad; label it in your schematic "
                            f"as {text!r}, or rename it here, so the pasted label connects")
        if p.direction == "input":
            inputs.append(SymPin(num, text, "input", text))
        else:
            etype = ("bidirectional" if p.direction == "inout"
                     else {"tri": "tri_state", "oc": "open_collector"}.get(p.drive, "output"))
            outputs.append(SymPin(num, text, etype, text))

    used = set(by_pin)
    jtag = []
    if design.keep_jtag and pkg.jtag:
        for fn in ("TDI", "TMS", "TCK", "TDO"):
            n = pkg.jtag[fn]
            jtag.append(SymPin(n, fn, "output" if fn == "TDO" else "input", fn))
    spare_in = [SymPin(n, fn, "input", "GND")
                for fn, n in sorted(pkg.inputs.items(), key=lambda kv: kv[1]) if n not in used]
    # dedicated pins such as a GreenPAK's I2C SCL/SDA: labelled for the
    # programming header, like JTAG
    jtag += [SymPin(n, fn, "bidirectional" if fn == "SDA" else "input", fn)
             for fn, n in sorted(pkg.reserved.items(), key=lambda kv: kv[1])]
    jtag_pins = set(pkg.jtag.values()) if design.keep_jtag else set()
    spare_io = [SymPin(n, pkg.pin_names.get(n, "I/O"),
                       "output" if n in pkg.out_only else "bidirectional", no_connect=True)
                for n in pkg.io if n not in used and n not in jtag_pins]
    vcc = "+3V3" if dev.vcc < 5 else "VCC"
    power = [SymPin(n, pkg.pin_names.get(n, vcc if kind == "VCC" else "GND"), "power_in",
                    vcc if kind == "VCC" else "GND")
             for kind in ("VCC", "GND") for n, k in sorted(pkg.power.items()) if k == kind]
    nc = [SymPin(n, "NC", "no_connect") for n in pkg.nc]

    def column(*groups):
        out: list = []
        for g in groups:
            if g:
                if out:
                    out.append(None)
                out += g
        return out

    return column(inputs, jtag, spare_in, power), column(outputs, spare_io, nc), warnings


def _n(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _font(justify: str = "", hide: bool = False) -> str:
    j = f" (justify {justify})" if justify else ""
    h = " (hide yes)" if hide else ""
    return f"(effects (font (size {FONT} {FONT})){j}{h})"


def build(design: Design, r: Optional[Result] = None) -> Export:
    r = r or generate(design)
    if not r.ok:
        raise ValueError("fix the report errors first: " + "; ".join(r.errors))
    left, right, warnings = _pins(design, r)
    name = f"{sanitize(design.name)}_{design.device}_{design.package}"
    lib_id = f"cpldglue:{name}"

    # body size: wide enough for the longest pin names on both sides
    def longest(col):
        return max((_visible_len(p.name) for p in col if p), default=0)
    width = max(20.32, math.ceil(((longest(left) + longest(right)) * 1.1 * FONT + 6) / (2 * GRID)) * 2 * GRID)
    rows = max(len(left), len(right))
    half = width / 2
    top = 0.0
    body_top, body_bottom = top + GRID, top - rows * GRID

    def pin_xy(side: str, i: int) -> Tuple[float, float]:
        x = -half - PIN_LEN if side == "L" else half + PIN_LEN
        return x, top - i * GRID

    # ---- library symbol ----
    pin_lines = []
    for side, col in (("L", left), ("R", right)):
        for i, p in enumerate(col):
            if p is None:
                continue
            x, y = pin_xy(side, i)
            pin_lines.append(
                f"(pin {p.etype} line (at {_n(x)} {_n(y)} {0 if side == 'L' else 180}) "
                f"(length {_n(PIN_LEN)}) (name {_q(p.name)} {_font()}) "
                f"(number {_q(str(p.number))} {_font()}))")
    dev = devices.DEVICES[design.device.upper()]
    _, pkg = devices.get_package(design.device, design.package)
    fp = pkg.footprint or FOOTPRINTS.get(design.package.upper(), "")
    what = ("GreenPAK" if dev.kind == "greenpak" else f"CPLD, {dev.macrocells} macrocells")
    props_lib = [
        ("Reference", "U", 0, body_top + 1.27, False),
        ("Value", f"{dev.name}-{design.package}", 0, body_bottom - 1.27, False),
        ("Footprint", fp, 0, body_bottom - 3.81, True),
        ("Datasheet", (f"https://www.renesas.com/en/document/dst/{dev.name.lower()}-datasheet"
                       if dev.kind == "greenpak" else
                       "https://www.microchip.com/en-us/search?searchQuery=" + dev.family),
         0, body_bottom - 6.35, True),
        ("Description", f"{dev.name} {what}, {design.package}: "
                        f"{design.name} (generated by cpldglue)", 0, 0, True),
    ]

    def lib_symbol(sym_name: str) -> str:
        props = "\n".join(
            f"      (property {_q(k)} {_q(v)} (at {_n(x)} {_n(y)} 0) {_font(hide=h)})"
            for k, v, x, y, h in props_lib)
        pins = "\n".join("        " + l for l in pin_lines)
        return (f"    (symbol {_q(sym_name)} (pin_names (offset 1.016)) (in_bom yes) (on_board yes)\n"
                f"{props}\n"
                f"      (symbol {_q(name + '_0_1')}\n"
                f"        (rectangle (start {_n(-half)} {_n(body_top)}) (end {_n(half)} {_n(body_bottom)})\n"
                f"          (stroke (width 0.254) (type default)) (fill (type background)))\n"
                f"      )\n"
                f"      (symbol {_q(name + '_1_1')}\n{pins}\n      )\n"
                f"    )")

    # ---- placed symbol, wires, labels ----
    ox, oy = ORIGIN
    items = []
    inst_props = "\n".join(
        f"    (property {_q(k)} {_q('U?' if k == 'Reference' else v)} "
        f"(at {_n(ox + x)} {_n(oy - y)} 0) {_font(hide=h)})"
        for k, v, x, y, h in props_lib)
    inst_pins = "\n".join(f"    (pin {_q(str(p.number))} (uuid {_q(str(uuid.uuid4()))}))"
                          for col in (left, right) for p in col if p)
    items.append(f"  (symbol (lib_id {_q(lib_id)}) (at {_n(ox)} {_n(oy)} 0) (unit 1)\n"
                 f"    (in_bom yes) (on_board yes) (dnp no)\n"
                 f"    (uuid {_q(str(uuid.uuid4()))})\n{inst_props}\n{inst_pins}\n  )")

    def wire_len(col) -> float:
        n = max((_visible_len(p.label) for p in col if p and p.label), default=0)
        return max(10.16, math.ceil((n * 1.05 * FONT + 1.27) / GRID) * GRID)

    labels = 0
    for side, col in (("L", left), ("R", right)):
        length = wire_len(col)
        for i, p in enumerate(col):
            if p is None:
                continue
            px, py = pin_xy(side, i)
            ex, ey = ox + px, oy - py                       # pin end, schematic coords
            if p.no_connect:
                items.append(f"  (no_connect (at {_n(ex)} {_n(ey)}) (uuid {_q(str(uuid.uuid4()))}))")
                continue
            if not p.label:
                continue
            fx = ex - length if side == "L" else ex + length
            items.append(f"  (wire (pts (xy {_n(fx)} {_n(ey)}) (xy {_n(ex)} {_n(ey)}))\n"
                         f"    (stroke (width 0) (type default)) (uuid {_q(str(uuid.uuid4()))}))")
            rot, just = (0, "left bottom") if side == "L" else (180, "right bottom")
            items.append(f"  (label {_q(p.label)} (at {_n(fx)} {_n(ey)} {rot})\n"
                         f"    {_font(just)}\n    (uuid {_q(str(uuid.uuid4()))}))")
            labels += 1

    clip = ("(lib_symbols\n" + lib_symbol(lib_id) + "\n)\n" + "\n".join(items) + "\n")
    lib = ("(kicad_symbol_lib (version 20231120) (generator \"cpldglue\")\n"
           + lib_symbol(name) + "\n)\n")
    return Export(name, clip, lib, warnings, labels)


def wrap_schematic(clip: str) -> str:
    """Wrap clipboard items into a whole .kicad_sch (used by the tests to check
    the output with kicad-cli; also handy to open on its own)."""
    return ("(kicad_sch (version 20231120) (generator \"cpldglue\")\n"
            f"  (uuid {_q(str(uuid.uuid4()))})\n  (paper \"A3\")\n"
            + clip + "  (sheet_instances (path \"/\" (page \"1\")))\n)\n")
