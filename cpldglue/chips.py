"""Chip library: pinouts for every supported part.

This file is the single source of truth for pin numbers. Each part maps
pin number -> (port name, kind). The matching Verilog module lives in
hdl/chips.v and is named in `module`.

Pin kinds:
  i    input
  o    totem-pole output
  t    3-state output    (Verilog ports: X, X_oe)
  b    bidirectional     (Verilog ports: X_i, X_o, X_oe)
  oc   open-collector    (Verilog port X; 0 = pull low, 1 = released)
  gnd, vcc, nc           power / no connect (not in the Verilog module)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HDL_DIR = Path(__file__).parent / "hdl"
KINDS = {"i", "o", "t", "b", "oc", "gnd", "vcc", "nc"}


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    kind: str

    @property
    def is_power(self) -> bool:
        return self.kind in ("gnd", "vcc", "nc")


@dataclass
class Part:
    key: str               # library key, e.g. "74x139", "4021"
    title: str             # human description
    module: str            # Verilog module in hdl/chips.v
    pins: Dict[str, Pin]   # pin number (as string) -> Pin
    warning: str = ""      # shown whenever the part is used
    package: str = ""      # e.g. "DIP-16"

    @property
    def storage_bits(self) -> int:
        """Flip-flops + latches in the model (each needs a CPLD macrocell)."""
        return STORAGE_BITS.get(self.module, 0)

    def ports(self) -> List[Tuple[str, str]]:
        """(verilog_port, direction) for every signal port of the module."""
        out = []
        for p in self.pins.values():
            if p.kind in ("i",):
                out.append((p.name, "input"))
            elif p.kind in ("o", "oc"):
                out.append((p.name, "output"))
            elif p.kind == "t":
                out += [(p.name, "output"), (p.name + "_oe", "output")]
            elif p.kind == "b":
                out += [(p.name + "_i", "input"), (p.name + "_o", "output"),
                        (p.name + "_oe", "output")]
        return out


def _pins(spec: str) -> Dict[str, Pin]:
    """Parse "1 a1, 2 b1, 3 y1:o, 7 GND, 14 VCC" into a pin table."""
    pins: Dict[str, Pin] = {}
    for item in spec.split(","):
        num, name = item.split()
        if name == "GND":
            kind = "gnd"
        elif name == "VCC":
            kind = "vcc"
        elif name == "NC":
            kind = "nc"
        elif ":" in name:
            name, kind = name.split(":")
        else:
            kind = "i"
        assert kind in KINDS, (spec, item)
        assert num not in pins, (spec, num)
        pins[num] = Pin(num, name, kind)
    return pins


def _seq(fmt: str, kind: str, first_pin: int, names: List[str], step: int = 1) -> str:
    return ",".join(f"{first_pin + i * step} {n}{':' + kind if kind != 'i' else ''}"
                    for i, n in enumerate(names))


# --------------------------------------------------------------------------
# Pinout specs
# --------------------------------------------------------------------------
QUAD2 = ("1 a1,2 b1,3 y1:o,4 a2,5 b2,6 y2:o,7 GND,8 y3:o,9 a3,10 b3,"
         "11 y4:o,12 a4,13 b4,14 VCC")
QUAD2_NOR = ("1 y1:o,2 a1,3 b1,4 y2:o,5 a2,6 b2,7 GND,8 a3,9 b3,10 y3:o,"
             "11 a4,12 b4,13 y4:o,14 VCC")


def HEX(k: str) -> str:
    return (f"1 a1,2 y1:{k},3 a2,4 y2:{k},5 a3,6 y3:{k},7 GND,8 y4:{k},9 a4,"
            f"10 y5:{k},11 a5,12 y6:{k},13 a6,14 VCC")


TRIPLE3 = ("1 a1,2 b1,3 a2,4 b2,5 c2,6 y2:o,7 GND,8 y3:o,9 a3,10 b3,11 c3,"
           "12 y1:o,13 c1,14 VCC")
DUAL4 = ("1 a1,2 b1,3 NC,4 c1,5 d1,6 y1:o,7 GND,8 y2:o,9 a2,10 b2,11 NC,"
         "12 c2,13 d2,14 VCC")


def QUAD_TRI(en: str) -> str:
    return (f"1 {en}1,2 a1,3 y1:t,4 {en}2,5 a2,6 y2:t,7 GND,8 y3:t,9 a3,"
            f"10 {en}3,11 y4:t,12 a4,13 {en}4,14 VCC")


HEX_TRI = ("1 g1_n,2 a1,3 y1:t,4 a2,5 y2:t,6 a3,7 y3:t,8 GND,9 y4:t,10 a4,"
           "11 y5:t,12 a5,13 y6:t,14 a6,15 g2_n,16 VCC")
OCT244 = ("1 oe1_n,2 a1_1,3 y2_4:t,4 a1_2,5 y2_3:t,6 a1_3,7 y2_2:t,8 a1_4,"
          "9 y2_1:t,10 GND,11 a2_1,12 y1_4:t,13 a2_2,14 y1_3:t,15 a2_3,"
          "16 y1_2:t,17 a2_4,18 y1_1:t,19 oe2_n,20 VCC")
OCT541 = ("1 oe1_n," + _seq("", "i", 2, [f"a{i}" for i in range(1, 9)]) +
          ",10 GND," + _seq("", "t", 11, [f"y{i}" for i in range(8, 0, -1)]) +
          ",19 oe2_n,20 VCC")
OCT245 = ("1 dir," + _seq("", "b", 2, [f"a{i}" for i in range(1, 9)]) +
          ",10 GND," + _seq("", "b", 11, [f"b{i}" for i in range(8, 0, -1)]) +
          ",19 oe_n,20 VCC")
DEC138 = ("1 a,2 b,3 c,4 g2a_n,5 g2b_n,6 g1,7 y7:o,8 GND,9 y6:o,10 y5:o,"
          "11 y4:o,12 y3:o,13 y2:o,14 y1:o,15 y0:o,16 VCC")
DEC139 = ("1 g1_n,2 a1,3 b1,4 y1_0:o,5 y1_1:o,6 y1_2:o,7 y1_3:o,8 GND,"
          "9 y2_3:o,10 y2_2:o,11 y2_1:o,12 y2_0:o,13 b2,14 a2,15 g2_n,16 VCC")
MUX153 = ("1 g1_n,2 b,3 c1_3,4 c1_2,5 c1_1,6 c1_0,7 y1:o,8 GND,9 y2:o,"
          "10 c2_0,11 c2_1,12 c2_2,13 c2_3,14 a,15 g2_n,16 VCC")
MUX157 = ("1 s,2 a1,3 b1,4 y1:o,5 a2,6 b2,7 y2:o,8 GND,9 y3:o,10 b3,11 a3,"
          "12 y4:o,13 b4,14 a4,15 g_n,16 VCC")
FF74 = ("1 clr1_n,2 d1,3 clk1,4 pre1_n,5 q1:o,6 q1_n:o,7 GND,8 q2_n:o,"
        "9 q2:o,10 pre2_n,11 clk2,12 d2,13 clr2_n,14 VCC")
FF174 = ("1 clr_n,2 q1:o,3 d1,4 d2,5 q2:o,6 d3,7 q3:o,8 GND,9 clk,10 q4:o,"
         "11 d4,12 q5:o,13 d5,14 d6,15 q6:o,16 VCC")
FF175 = ("1 clr_n,2 q1:o,3 q1_n:o,4 d1,5 d2,6 q2_n:o,7 q2:o,8 GND,9 clk,"
         "10 q3:o,11 q3_n:o,12 d3,13 d4,14 q4_n:o,15 q4:o,16 VCC")


def OCT273(first: str, k: str = "o") -> str:
    return (f"1 {first},2 q1:{k},3 d1,4 d2,5 q2:{k},6 q3:{k},7 d3,8 d4,9 q4:{k},"
            f"10 GND,11 {{c}},12 q5:{k},13 d5,14 d6,15 q6:{k},16 q7:{k},17 d7,"
            f"18 d8,19 q8:{k},20 VCC")


def OCT573(c: str) -> str:
    return ("1 oe_n," + _seq("", "i", 2, [f"d{i}" for i in range(1, 9)]) +
            f",10 GND,11 {c}," + _seq("", "t", 12, [f"q{i}" for i in range(8, 0, -1)]) +
            ",20 VCC")


CNT161 = ("1 clr_n,2 clk,3 a,4 b,5 c,6 d,7 enp,8 GND,9 load_n,10 ent,"
          "11 qd:o,12 qc:o,13 qb:o,14 qa:o,15 rco:o,16 VCC")
SR164 = ("1 a,2 b,3 qa:o,4 qb:o,5 qc:o,6 qd:o,7 GND,8 clk,9 clr_n,10 qe:o,"
         "11 qf:o,12 qg:o,13 qh:o,14 VCC")
SR165 = ("1 sh_ld_n,2 clk,3 e,4 f,5 g,6 h,7 qh_n:o,8 GND,9 qh:o,10 ser,"
         "11 a,12 b,13 c,14 d,15 clk_inh,16 VCC")
SR595 = ("1 qb:t,2 qc:t,3 qd:t,4 qe:t,5 qf:t,6 qg:t,7 qh:t,8 GND,9 qh_s:o,"
         "10 srclr_n,11 srclk,12 rclk,13 oe_n,14 ser,15 qa:t,16 VCC")
CD4021 = ("1 p8,2 q6:o,3 q8:o,4 p4,5 p3,6 p2,7 p1,8 GND,9 ps,10 clk,11 ser,"
          "12 q7:o,13 p5,14 p6,15 p7,16 VCC")

_DEFS = [
    # key, title, module, pinspec, package, warning
    ("74x00", "Quad 2-input NAND", "cg_74x00", QUAD2, "DIP-14", ""),
    ("74x02", "Quad 2-input NOR", "cg_74x02", QUAD2_NOR, "DIP-14", ""),
    ("74x04", "Hex inverter", "cg_74x04", HEX("o"), "DIP-14", ""),
    ("74x05", "Hex inverter, open collector", "cg_74x04", HEX("oc"), "DIP-14",
     "open-collector outputs: keep the external pull-up resistors"),
    ("74x06", "Hex inverter, open collector (high voltage)", "cg_74x04", HEX("oc"),
     "DIP-14", "open-collector outputs: a CPLD pin cannot be pulled above VCC"),
    ("74x07", "Hex buffer, open collector (high voltage)", "cg_74x07", HEX("oc"),
     "DIP-14", "open-collector outputs: a CPLD pin cannot be pulled above VCC"),
    ("74x08", "Quad 2-input AND", "cg_74x08", QUAD2, "DIP-14", ""),
    ("74x10", "Triple 3-input NAND", "cg_74x10", TRIPLE3, "DIP-14", ""),
    ("74x11", "Triple 3-input AND", "cg_74x11", TRIPLE3, "DIP-14", ""),
    ("74x14", "Hex Schmitt-trigger inverter", "cg_74x04", HEX("o"), "DIP-14",
     "Schmitt-trigger hysteresis is lost; do not use on slow or RC signals"),
    ("74x20", "Dual 4-input NAND", "cg_74x20", DUAL4, "DIP-14", ""),
    ("74x32", "Quad 2-input OR", "cg_74x32", QUAD2, "DIP-14", ""),
    ("74x74", "Dual D flip-flop, preset and clear", "cg_74x74", FF74, "DIP-14", ""),
    ("74x86", "Quad 2-input XOR", "cg_74x86", QUAD2, "DIP-14", ""),
    ("74x125", "Quad 3-state buffer, active-low enable", "cg_74x125",
     QUAD_TRI("oe") .replace("oe1,", "oe1_n,").replace("oe2,", "oe2_n,")
     .replace("oe3,", "oe3_n,").replace("oe4,", "oe4_n,"), "DIP-14", ""),
    ("74x126", "Quad 3-state buffer, active-high enable", "cg_74x126",
     QUAD_TRI("oe"), "DIP-14", ""),
    ("74x138", "3-to-8 decoder", "cg_74x138", DEC138, "DIP-16", ""),
    ("74x139", "Dual 2-to-4 decoder", "cg_74x139", DEC139, "DIP-16", ""),
    ("74x153", "Dual 4-to-1 multiplexer", "cg_74x153", MUX153, "DIP-16", ""),
    ("74x157", "Quad 2-to-1 multiplexer", "cg_74x157", MUX157, "DIP-16", ""),
    ("74x161", "4-bit counter, async clear", "cg_74x161", CNT161, "DIP-16", ""),
    ("74x163", "4-bit counter, sync clear", "cg_74x163", CNT161, "DIP-16", ""),
    ("74x164", "8-bit serial-in parallel-out shift register", "cg_74x164", SR164,
     "DIP-14", ""),
    ("74x165", "8-bit parallel-in serial-out shift register", "cg_74x165", SR165,
     "DIP-16", ""),
    ("74x174", "Hex D flip-flop, clear", "cg_74x174", FF174, "DIP-16", ""),
    ("74x175", "Quad D flip-flop, clear", "cg_74x175", FF175, "DIP-16", ""),
    ("74x240", "Octal 3-state inverting buffer", "cg_74x240", OCT244, "DIP-20", ""),
    ("74x244", "Octal 3-state buffer", "cg_74x244", OCT244, "DIP-20", ""),
    ("74x245", "Octal bus transceiver", "cg_74x245", OCT245, "DIP-20",
     "both sides must be CPLD pins; a bidirectional net cannot stay inside the CPLD"),
    ("74x273", "Octal D flip-flop, clear", "cg_74x273",
     OCT273("clr_n").replace("{c}", "clk"), "DIP-20", ""),
    ("74x367", "Hex 3-state buffer", "cg_74x367", HEX_TRI, "DIP-16", ""),
    ("74x368", "Hex 3-state inverting buffer", "cg_74x368", HEX_TRI, "DIP-16", ""),
    ("74x373", "Octal transparent latch, 3-state", "cg_74x373",
     OCT273("oe_n", "t").replace("{c}", "le"), "DIP-20", ""),
    ("74x374", "Octal D flip-flop, 3-state", "cg_74x374",
     OCT273("oe_n", "t").replace("{c}", "clk"), "DIP-20", ""),
    ("74x377", "Octal D flip-flop, clock enable", "cg_74x377",
     OCT273("e_n").replace("{c}", "clk"), "DIP-20", ""),
    ("74x540", "Octal 3-state inverting buffer", "cg_74x540", OCT541, "DIP-20", ""),
    ("74x541", "Octal 3-state buffer", "cg_74x541", OCT541, "DIP-20", ""),
    ("74x573", "Octal transparent latch, 3-state", "cg_74x373", OCT573("le"),
     "DIP-20", ""),
    ("74x574", "Octal D flip-flop, 3-state", "cg_74x374", OCT573("clk"),
     "DIP-20", ""),
    ("74x595", "8-bit shift register with output latch", "cg_74x595", SR595,
     "DIP-16", ""),
    ("4021", "CD4021 8-stage parallel-in serial-out shift register", "cg_4021",
     CD4021, "DIP-16", ""),
]

# Flip-flops and latches per model; tests/test_chips.py checks these
# against the models' Yosys netlists.
STORAGE_BITS: Dict[str, int] = {
    "cg_74x74": 2, "cg_74x161": 4, "cg_74x163": 4, "cg_74x164": 8,
    "cg_74x165": 8, "cg_74x174": 6, "cg_74x175": 4, "cg_74x273": 8,
    "cg_74x373": 8, "cg_74x374": 8, "cg_74x377": 8, "cg_74x595": 16,
    "cg_4021": 8,
}

LIBRARY: Dict[str, Part] = {
    key: Part(key, title, module, _pins(spec), warn, pkg)
    for key, title, module, spec, pkg, warn in _DEFS
}


def lookup(value: str) -> Optional[Part]:
    """Find a library part from a schematic value like '74HC368/40H368 (CII)',
    'SN74LS00N', 'CD4021BE', '74x139' or '139'."""
    v = value.upper().replace(" ", "")
    if v.lower() in LIBRARY:
        return LIBRARY[v.lower()]
    m = re.search(r"74[A-Z]*?(\d{2,3})(?!\d)", v)
    if m is None:
        m = re.search(r"40H(\d{3})(?!\d)", v)          # Toshiba 40H = 74HC
    if m is not None:
        return LIBRARY.get("74x" + m.group(1))
    m = re.search(r"(?:CD|HEF|MC1|MC)?(40\d\d)(?:B|UB)?", v)
    if m is not None:
        return LIBRARY.get(m.group(1))
    m = re.fullmatch(r"(\d{2,3})", v)
    if m is not None:
        return LIBRARY.get("74x" + m.group(1))
    return None


def verilog_source() -> str:
    return (HDL_DIR / "chips.v").read_text(encoding="utf-8")


def verilog_modules(names) -> str:
    """Return the Verilog text of just the named modules."""
    src = verilog_source()
    blocks = {}
    for m in re.finditer(r"^module\s+(\w+).*?^endmodule\s*$", src, re.S | re.M):
        blocks[m.group(1)] = m.group(0)
    missing = [n for n in names if n not in blocks]
    if missing:
        raise KeyError(f"no Verilog model for {missing}")
    return "\n\n".join(blocks[n] for n in sorted(set(names)))
