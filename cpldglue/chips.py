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

# Pinouts checked against the TI / Harris datasheets (see hdl/chips.v).
SR594 = ("1 qb:o,2 qc:o,3 qd:o,4 qe:o,5 qf:o,6 qg:o,7 qh:o,8 GND,9 qh_s:o,"
         "10 srclr_n,11 srclk,12 rclk,13 rclr_n,14 ser,15 qa:o,16 VCC")
SR166 = ("1 ser,2 a,3 b,4 c,5 d,6 clk_inh,7 clk,8 GND,9 clr_n,10 e,11 f,12 g,"
         "13 qh:o,14 h,15 sh_ld_n,16 VCC")
SR597 = ("1 b,2 c,3 d,4 e,5 f,6 g,7 h,8 GND,9 qh:o,10 srclr_n,11 srclk,12 rclk,"
         "13 srload_n,14 ser,15 a,16 VCC")
SR194 = ("1 clr_n,2 sr_ser,3 a,4 b,5 c,6 d,7 sl_ser,8 GND,9 s0,10 s1,11 clk,"
         "12 qd:o,13 qc:o,14 qb:o,15 qa:o,16 VCC")
CD4094 = ("1 strobe,2 data,3 clk,4 q1:t,5 q2:t,6 q3:t,7 q4:t,8 GND,9 qs:o,"
          "10 qs_d:o,11 q8:t,12 q7:t,13 q6:t,14 q5:t,15 oe,16 VCC")
CD4015 = ("1 clk_b,2 q4_b:o,3 q3_a:o,4 q2_a:o,5 q1_a:o,6 rst_a,7 data_a,8 GND,"
          "9 clk_a,10 q4_a:o,11 q3_b:o,12 q2_b:o,13 q1_b:o,14 rst_b,15 data_b,16 VCC")

# Single gates (SOT-23-5 / SOT-23-6 "DBV" pinouts, TI SN74LVC1G datasheets).
G1_2IN = "1 a,2 b,3 GND,4 y:o,5 VCC"
G1_3IN = "1 a,2 GND,3 b,4 y:o,5 VCC,6 c"


def G1_1IN(k: str = "o") -> str:
    return f"1 NC,2 a,3 GND,4 y:{k},5 VCC"


def G1_TRI(en: str) -> str:
    return f"1 {en},2 a,3 GND,4 y:t,5 VCC"


# More glue parts (pinouts checked against the TI datasheets).
NAND8 = "1 a,2 b,3 c,4 d,5 e,6 f,7 GND,8 y:o,9 NC,10 NC,11 g,12 h,13 NC,14 VCC"
MUX151 = ("1 d3,2 d2,3 d1,4 d0,5 y:o,6 w:o,7 g_n,8 GND,9 c,10 b,11 a,12 d7,13 d6,"
          "14 d5,15 d4,16 VCC")
DEC154 = (",".join(f"{i + 1} y{i}:o" for i in range(11)) + ",12 GND,"
          + ",".join(f"{i + 2} y{i}:o" for i in range(11, 16))
          + ",18 g1_n,19 g2_n,20 d,21 c,22 b,23 a,24 VCC")
MUX257 = ("1 s,2 a1,3 b1,4 y1:t,5 a2,6 b2,7 y2:t,8 GND,9 y3:t,10 b3,11 a3,"
          "12 y4:t,13 b4,14 a4,15 oe_n,16 VCC")
LATCH259 = ("1 s0,2 s1,3 s2,4 q0:o,5 q1:o,6 q2:o,7 q3:o,8 GND,9 q4:o,10 q5:o,"
            "11 q6:o,12 q7:o,13 d,14 g_n,15 clr_n,16 VCC")
REG173 = ("1 m,2 n,3 q1:t,4 q2:t,5 q3:t,6 q4:t,7 clk,8 GND,9 g1_n,10 g2_n,"
          "11 d4,12 d3,13 d2,14 d1,15 clr,16 VCC")
CMP688 = ("1 g_n,2 p0,3 q0,4 p1,5 q1,6 p2,7 q2,8 p3,9 q3,10 GND,11 p4,12 q4,"
          "13 p5,14 q5,15 p6,16 q6,17 p7,18 q7,19 eq_n:o,20 VCC")
JK109 = ("1 clr1_n,2 j1,3 k1_n,4 clk1,5 pre1_n,6 q1:o,7 q1_n:o,8 GND,9 q2_n:o,"
         "10 q2:o,11 pre2_n,12 clk2,13 k2_n,14 j2,15 clr2_n,16 VCC")
JK112 = ("1 clk1,2 k1,3 j1,4 pre1_n,5 q1:o,6 q1_n:o,7 q2_n:o,8 GND,9 q2:o,"
         "10 pre2_n,11 j2,12 k2,13 clk2,14 clr2_n,15 clr1_n,16 VCC")
CNT191 = ("1 b,2 qb:o,3 qa:o,4 cten_n,5 du,6 qc:o,7 qd:o,8 GND,9 d,10 c,"
          "11 load_n,12 maxmin:o,13 rco_n:o,14 clk,15 a,16 VCC")
CNT193 = ("1 b,2 qb:o,3 qa:o,4 down,5 up,6 qc:o,7 qd:o,8 GND,9 d,10 c,"
          "11 load_n,12 co_n:o,13 bo_n:o,14 clr,15 a,16 VCC")
CNT393 = ("1 clk1,2 clr1,3 qa1:o,4 qb1:o,5 qc1:o,6 qd1:o,7 GND,8 qd2:o,9 qc2:o,"
          "10 qb2:o,11 qa2:o,12 clr2,13 clk2,14 VCC")
CD4040 = ("1 q12:o,2 q6:o,3 q5:o,4 q7:o,5 q4:o,6 q3:o,7 q2:o,8 GND,9 q1:o,10 clk,"
          "11 rst,12 q9:o,13 q8:o,14 q10:o,15 q11:o,16 VCC")
CD4017 = ("1 q5:o,2 q1:o,3 q0:o,4 q2:o,5 q6:o,6 q7:o,7 q3:o,8 GND,9 q8:o,10 q4:o,"
          "11 q9:o,12 co:o,13 inh,14 clk,15 rst,16 VCC")
CD4013 = ("1 q1:o,2 q1_n:o,3 clk1,4 rst1,5 d1,6 set1,7 GND,8 set2,9 d2,10 rst2,"
          "11 clk2,12 q2_n:o,13 q2:o,14 VCC")
CD_QUAD2 = ("1 a1,2 b1,3 y1:o,4 y2:o,5 a2,6 b2,7 GND,8 a3,9 b3,10 y3:o,11 y4:o,"
            "12 a4,13 b4,14 VCC")
CD_HEX16 = ("1 VCC,2 y1:o,3 a1,4 y2:o,5 a2,6 y3:o,7 a3,8 GND,9 a4,10 y4:o,11 a5,"
            "12 y5:o,13 NC,14 a6,15 y6:o,16 NC")
# Dual gates (TI SN74LVC2G: 8-pin for 2-input and 3-state, 6-pin for 1-input)
G2_2IN = "1 a1,2 b1,3 y2:o,4 GND,5 a2,6 b2,7 y1:o,8 VCC"


def G2_1IN(k: str = "o") -> str:
    return f"1 a1,2 GND,3 a2,4 y2:{k},5 VCC,6 y1:{k}"


def G2_TRI(active_low: bool) -> str:
    n = "_n" if active_low else ""
    return f"1 oe1{n},2 a1,3 y2:t,4 GND,5 a2,6 y1:t,7 oe2{n},8 VCC"


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
    ("74x1G00", "Single 2-input NAND", "cg_1g00", G1_2IN, "SOT-23-5", ""),
    ("74x1G02", "Single 2-input NOR", "cg_1g02", G1_2IN, "SOT-23-5", ""),
    ("74x1G08", "Single 2-input AND", "cg_1g08", G1_2IN, "SOT-23-5", ""),
    ("74x1G32", "Single 2-input OR", "cg_1g32", G1_2IN, "SOT-23-5", ""),
    ("74x1G86", "Single 2-input XOR", "cg_1g86", G1_2IN, "SOT-23-5", ""),
    ("74x1G04", "Single inverter", "cg_1g04", G1_1IN(), "SOT-23-5", ""),
    ("74x1G14", "Single Schmitt-trigger inverter", "cg_1g04", G1_1IN(), "SOT-23-5",
     "Schmitt-trigger hysteresis is lost; do not use on slow or RC signals"),
    ("74x1G34", "Single buffer", "cg_1g07", G1_1IN(), "SOT-23-5", ""),
    ("74x1G17", "Single Schmitt-trigger buffer", "cg_1g07", G1_1IN(), "SOT-23-5",
     "Schmitt-trigger hysteresis is lost; do not use on slow or RC signals"),
    ("74x1G06", "Single inverter, open drain", "cg_1g04", G1_1IN("oc"), "SOT-23-5",
     "open-drain output: keep the external pull-up; a CPLD pin cannot be pulled above VCC"),
    ("74x1G07", "Single buffer, open drain", "cg_1g07", G1_1IN("oc"), "SOT-23-5",
     "open-drain output: keep the external pull-up; a CPLD pin cannot be pulled above VCC"),
    ("74x1G10", "Single 3-input NAND", "cg_1g10", G1_3IN, "SOT-23-6", ""),
    ("74x1G11", "Single 3-input AND", "cg_1g11", G1_3IN, "SOT-23-6", ""),
    ("74x1G27", "Single 3-input NOR", "cg_1g27", G1_3IN, "SOT-23-6", ""),
    ("74x1G125", "Single 3-state buffer, active-low enable", "cg_1g125", G1_TRI("oe_n"),
     "SOT-23-5", ""),
    ("74x1G126", "Single 3-state buffer, active-high enable", "cg_1g126", G1_TRI("oe"),
     "SOT-23-5", ""),
    ("74x1G240", "Single 3-state inverting buffer, active-low enable", "cg_1g240",
     G1_TRI("oe_n"), "SOT-23-5", ""),
    ("74x1G79", "Single D flip-flop, rising edge", "cg_1g79",
     "1 d,2 clk,3 GND,4 q:o,5 VCC", "SOT-23-5", ""),
    ("74x1G80", "Single D flip-flop, rising edge, inverted output", "cg_1g80",
     "1 d,2 clk,3 GND,4 q_n:o,5 VCC", "SOT-23-5", ""),
    ("74x03", "Quad 2-input NAND, open collector", "cg_74x00", QUAD2.replace(":o", ":oc"),
     "DIP-14", "open-collector outputs: keep the external pull-up resistors"),
    ("74x09", "Quad 2-input AND, open collector", "cg_74x08", QUAD2.replace(":o", ":oc"),
     "DIP-14", "open-collector outputs: keep the external pull-up resistors"),
    ("74x21", "Dual 4-input AND", "cg_74x21", DUAL4, "DIP-14", ""),
    ("74x27", "Triple 3-input NOR", "cg_74x27", TRIPLE3, "DIP-14", ""),
    ("74x30", "8-input NAND", "cg_74x30", NAND8, "DIP-14", ""),
    ("74x109", "Dual J-/K flip-flop, preset and clear", "cg_74x109", JK109, "DIP-16", ""),
    ("74x112", "Dual J-K flip-flop, falling edge, preset and clear", "cg_74x112", JK112,
     "DIP-16", ""),
    ("74x151", "8-to-1 multiplexer", "cg_74x151", MUX151, "DIP-16", ""),
    ("74x154", "4-to-16 decoder", "cg_74x154", DEC154, "DIP-24", ""),
    ("74x173", "4-bit D register, 3-state", "cg_74x173", REG173, "DIP-16", ""),
    ("74x191", "4-bit up/down counter, async load", "cg_74x191", CNT191, "DIP-16", ""),
    ("74x193", "4-bit up/down counter, dual clock", "cg_74x193", CNT193, "DIP-16", ""),
    ("74x257", "Quad 2-to-1 multiplexer, 3-state", "cg_74x257", MUX257, "DIP-16", ""),
    ("74x258", "Quad 2-to-1 multiplexer, 3-state, inverting", "cg_74x258", MUX257,
     "DIP-16", ""),
    ("74x259", "8-bit addressable latch", "cg_74x259", LATCH259, "DIP-16", ""),
    ("74x393", "Dual 4-bit binary counter", "cg_74x393", CNT393, "DIP-14",
     "modelled as a synchronous counter: all outputs change together (the real chip ripples)"),
    ("74x521", "8-bit identity comparator", "cg_74x688", CMP688, "DIP-20", ""),
    ("74x688", "8-bit identity comparator", "cg_74x688", CMP688, "DIP-20", ""),
    ("4001", "CD4001 quad 2-input NOR", "cg_74x02", CD_QUAD2, "DIP-14", ""),
    ("4011", "CD4011 quad 2-input NAND", "cg_74x00", CD_QUAD2, "DIP-14", ""),
    ("4013", "CD4013 dual D flip-flop, set and reset", "cg_4013", CD4013, "DIP-14", ""),
    ("4017", "CD4017 decade counter / divider (Johnson)", "cg_4017", CD4017, "DIP-16", ""),
    ("4040", "CD4040 12-stage binary counter", "cg_4040", CD4040, "DIP-16", "modelled as a synchronous counter: all outputs change together (the real chip ripples)"),
    ("4049", "CD4049 hex inverting buffer", "cg_74x04", CD_HEX16, "DIP-16",
     "level-shifting buffer: a CPLD input can't take more than its own supply"),
    ("4050", "CD4050 hex buffer", "cg_74x07", CD_HEX16.replace(":oc", ":o"), "DIP-16",
     "level-shifting buffer: a CPLD input can't take more than its own supply"),
    ("4069", "CD4069 hex inverter", "cg_74x04", HEX("o"), "DIP-14", ""),
    ("4070", "CD4070 quad 2-input XOR", "cg_74x86", CD_QUAD2, "DIP-14", ""),
    ("4071", "CD4071 quad 2-input OR", "cg_74x32", CD_QUAD2, "DIP-14", ""),
    ("4081", "CD4081 quad 2-input AND", "cg_74x08", CD_QUAD2, "DIP-14", ""),
    ("74x2G00", "Dual 2-input NAND", "cg_2g00", G2_2IN, "SOT-23-8", ""),
    ("74x2G02", "Dual 2-input NOR", "cg_2g02", G2_2IN, "SOT-23-8", ""),
    ("74x2G08", "Dual 2-input AND", "cg_2g08", G2_2IN, "SOT-23-8", ""),
    ("74x2G32", "Dual 2-input OR", "cg_2g32", G2_2IN, "SOT-23-8", ""),
    ("74x2G86", "Dual 2-input XOR", "cg_2g86", G2_2IN, "SOT-23-8", ""),
    ("74x2G04", "Dual inverter", "cg_2g04", G2_1IN(), "SOT-23-6", ""),
    ("74x2G14", "Dual Schmitt-trigger inverter", "cg_2g04", G2_1IN(), "SOT-23-6",
     "Schmitt-trigger hysteresis is lost; do not use on slow or RC signals"),
    ("74x2G34", "Dual buffer", "cg_2g07", G2_1IN(), "SOT-23-6", ""),
    ("74x2G17", "Dual Schmitt-trigger buffer", "cg_2g07", G2_1IN(), "SOT-23-6",
     "Schmitt-trigger hysteresis is lost; do not use on slow or RC signals"),
    ("74x2G06", "Dual inverter, open drain", "cg_2g04", G2_1IN("oc"), "SOT-23-6",
     "open-drain outputs: keep the external pull-ups; a CPLD pin cannot be pulled above VCC"),
    ("74x2G07", "Dual buffer, open drain", "cg_2g07", G2_1IN("oc"), "SOT-23-6",
     "open-drain outputs: keep the external pull-ups; a CPLD pin cannot be pulled above VCC"),
    ("74x2G125", "Dual 3-state buffer, active-low enables", "cg_2g125", G2_TRI(True),
     "SOT-23-8", ""),
    ("74x2G126", "Dual 3-state buffer, active-high enables", "cg_2g126", G2_TRI(False),
     "SOT-23-8", ""),
    ("74x594", "8-bit shift register with output register and clears", "cg_74x594",
     SR594, "DIP-16", ""),
    ("74x166", "8-bit parallel-in serial-out shift register, sync load", "cg_74x166",
     SR166, "DIP-16", ""),
    ("74x597", "8-bit shift register with input storage register", "cg_74x597",
     SR597, "DIP-16", ""),
    ("74x194", "4-bit bidirectional universal shift register", "cg_74x194",
     SR194, "DIP-16", ""),
    ("4094", "CD4094 8-stage shift-and-store bus register (also 74x4094)", "cg_4094",
     CD4094, "DIP-16", ""),
    ("4015", "CD4015 dual 4-stage serial-in parallel-out shift register", "cg_4015",
     CD4015, "DIP-16", ""),
    ("4014", "CD4014 8-stage parallel-in serial-out shift register, sync load",
     "cg_4014", CD4021, "DIP-16", ""),
]

# Flip-flops and latches per model; tests/test_chips.py checks these
# against the models' Yosys netlists.
STORAGE_BITS: Dict[str, int] = {
    "cg_74x74": 2, "cg_74x161": 4, "cg_74x163": 4, "cg_74x164": 8,
    "cg_74x165": 8, "cg_74x174": 6, "cg_74x175": 4, "cg_74x273": 8,
    "cg_74x373": 8, "cg_74x374": 8, "cg_74x377": 8, "cg_74x595": 16,
    "cg_4021": 8,
    "cg_74x594": 16, "cg_74x166": 8, "cg_74x597": 16, "cg_74x194": 4,
    "cg_4094": 17, "cg_4015": 8, "cg_4014": 8, "cg_1g79": 1, "cg_1g80": 1,
    "cg_74x259": 8, "cg_74x173": 4, "cg_74x109": 2, "cg_74x112": 2, "cg_74x191": 4,
    "cg_74x193": 5, "cg_74x393": 8, "cg_4040": 12, "cg_4017": 5, "cg_4013": 2,
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
    for key in LIBRARY:                 # e.g. "74x1G00" typed as is
        if key.upper() == v:
            return LIBRARY[key]
    m = re.search(r"74[A-Z]*?1GU?(\d{2,3})(?!\d)", v) or \
        re.search(r"NC7S[ZBVP]?U?(\d{2,3})(?!\d)", v)
    if m is not None:                   # single gates; 1GU04 = unbuffered 1G04
        return LIBRARY.get("74x1G" + m.group(1))
    m = re.search(r"74[A-Z]*?2GU?(\d{2,3})(?!\d)", v) or \
        re.search(r"NC7W[ZBVP]?U?(\d{2,3})(?!\d)", v)
    if m is not None:                   # dual gates (onsemi NC7WZ = 2G pinouts)
        return LIBRARY.get("74x2G" + m.group(1))
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
