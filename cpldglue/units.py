"""The gates (units) inside each library part.

A unit is one gate, buffer, flip-flop bit or function block, named by its
pins. The generator uses them to leave out gates whose outputs go nowhere
(so their inputs need no CPLD pins); the editor uses them to draw the gates
on each chip.

symbol:   and or nand nor xor not buf tri tri_not mux bidir block
inputs:   data inputs (drawn on the gate's input side)
outputs:  outputs
controls: enables / selects / clocks (drawn on the side of the gate)
storage:  flip-flop or latch bits (for the macrocell estimate)
group:    units with the same group are drawn as one block (blocks only)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class Unit:
    symbol: str
    inputs: Tuple[str, ...]
    outputs: Tuple[str, ...]
    controls: Tuple[str, ...] = ()
    storage: int = 0
    group: str = ""
    name: str = ""

    @property
    def pins(self) -> Tuple[str, ...]:
        return self.inputs + self.controls + self.outputs

    def to_json(self) -> dict:
        return {"symbol": self.symbol, "inputs": list(self.inputs),
                "outputs": list(self.outputs), "controls": list(self.controls),
                "storage": self.storage, "group": self.group, "name": self.name}


def _u(symbol: str, ins: Sequence[str], outs: Sequence[str], ctrl: Sequence[str] = (),
       storage: int = 0, group: str = "", name: str = "") -> Unit:
    return Unit(symbol, tuple(ins), tuple(outs), tuple(ctrl), storage, group, name)


def _gates(symbol: str, n: int, ins: str, out: str = "y") -> List[Unit]:
    return [_u(symbol, [f"{c}{i}" for c in ins], [f"{out}{i}"], name=f"gate {i}")
            for i in range(1, n + 1)]


def _bits(group: str, n: int, ctrl: Sequence[str], qn: bool = False,
          d: str = "d", q: str = "q") -> List[Unit]:
    return [_u("block", [f"{d}{i}"], [f"{q}{i}"] + ([f"{q}{i}_n"] if qn else []), ctrl,
               storage=1, group=group, name=f"bit {i}") for i in range(1, n + 1)]


def _build() -> Dict[str, List[Unit]]:
    u: Dict[str, List[Unit]] = {}
    for key, sym in (("74x00", "nand"), ("74x02", "nor"), ("74x08", "and"),
                     ("74x32", "or"), ("74x86", "xor")):
        u[key] = _gates(sym, 4, "ab")
    for key in ("74x04", "74x05", "74x06", "74x14"):
        u[key] = _gates("not", 6, "a")
    u["74x07"] = _gates("buf", 6, "a")
    u["74x10"] = _gates("nand", 3, "abc")
    u["74x11"] = _gates("and", 3, "abc")
    u["74x20"] = _gates("nand", 2, "abcd")
    u["74x125"] = [_u("tri", [f"a{i}"], [f"y{i}"], [f"oe{i}_n"], name=f"buffer {i}")
                   for i in range(1, 5)]
    u["74x126"] = [_u("tri", [f"a{i}"], [f"y{i}"], [f"oe{i}"], name=f"buffer {i}")
                   for i in range(1, 5)]
    for key, sym in (("74x367", "tri"), ("74x368", "tri_not")):
        u[key] = [_u(sym, [f"a{i}"], [f"y{i}"], ["g1_n" if i <= 4 else "g2_n"],
                     name=f"buffer {i}") for i in range(1, 7)]
    for key, sym in (("74x244", "tri"), ("74x240", "tri_not")):
        u[key] = [_u(sym, [f"a{g}_{k}"], [f"y{g}_{k}"], [f"oe{g}_n"],
                     name=f"buffer {g}.{k}") for g in (1, 2) for k in range(1, 5)]
    for key, sym in (("74x541", "tri"), ("74x540", "tri_not")):
        u[key] = [_u(sym, [f"a{i}"], [f"y{i}"], ["oe1_n", "oe2_n"], name=f"buffer {i}")
                  for i in range(1, 9)]
    u["74x245"] = [_u("bidir", [f"a{i}"], [f"b{i}"], ["dir", "oe_n"], name=f"bit {i}")
                   for i in range(1, 9)]
    u["74x74"] = [_u("block", [f"d{i}"], [f"q{i}", f"q{i}_n"],
                     [f"clk{i}", f"pre{i}_n", f"clr{i}_n"], storage=1,
                     group=f"D FF {i}", name=f"flip-flop {i}") for i in (1, 2)]
    u["74x138"] = [_u("block", ["a", "b", "c"], [f"y{i}" for i in range(8)],
                      ["g1", "g2a_n", "g2b_n"], group="3→8 DEC", name="decoder")]
    u["74x139"] = [_u("block", [f"a{i}", f"b{i}"], [f"y{i}_{k}" for k in range(4)],
                      [f"g{i}_n"], group=f"2→4 DEC {i}", name=f"decoder {i}")
                   for i in (1, 2)]
    u["74x153"] = [_u("block", [f"c{i}_{k}" for k in range(4)], [f"y{i}"],
                      ["a", "b", f"g{i}_n"], group=f"4:1 MUX {i}", name=f"mux {i}")
                   for i in (1, 2)]
    u["74x157"] = [_u("mux", [f"a{i}", f"b{i}"], [f"y{i}"], ["s", "g_n"],
                      name=f"mux {i}") for i in range(1, 5)]
    for key in ("74x161", "74x163"):
        u[key] = [_u("block", ["a", "b", "c", "d", "enp", "ent"],
                     ["qa", "qb", "qc", "qd", "rco"], ["clk", "clr_n", "load_n"],
                     storage=4, group="CTR4", name="counter")]
    u["74x164"] = [_u("block", ["a", "b"], [f"q{c}" for c in "abcdefgh"],
                      ["clk", "clr_n"], storage=8, group="SRG8", name="shift register")]
    u["74x165"] = [_u("block", ["ser"] + list("abcdefgh"), ["qh", "qh_n"],
                      ["clk", "clk_inh", "sh_ld_n"], storage=8, group="SRG8",
                      name="shift register")]
    u["74x174"] = _bits("D FF ×6", 6, ["clk", "clr_n"])
    u["74x175"] = _bits("D FF ×4", 4, ["clk", "clr_n"], qn=True)
    u["74x273"] = _bits("D FF ×8", 8, ["clk", "clr_n"])
    u["74x377"] = _bits("D FF ×8", 8, ["clk", "e_n"])
    u["74x374"] = _bits("D FF ×8", 8, ["clk", "oe_n"])
    u["74x574"] = _bits("D FF ×8", 8, ["clk", "oe_n"])
    u["74x373"] = _bits("LATCH ×8", 8, ["le", "oe_n"])
    u["74x573"] = _bits("LATCH ×8", 8, ["le", "oe_n"])
    u["74x595"] = [_u("block", ["ser"], [f"q{c}" for c in "abcdefgh"] + ["qh_s"],
                      ["srclk", "rclk", "srclr_n", "oe_n"], storage=16,
                      group="SRG8 + LATCH", name="shift register")]
    u["4021"] = [_u("block", ["ser"] + [f"p{i}" for i in range(1, 9)], ["q6", "q7", "q8"],
                    ["clk", "ps"], storage=8, group="SRG8", name="shift register")]
    u["74x594"] = [_u("block", ["ser"], [f"q{c}" for c in "abcdefgh"] + ["qh_s"],
                      ["srclk", "rclk", "srclr_n", "rclr_n"], storage=16,
                      group="SRG8 + REG", name="shift register")]
    u["74x166"] = [_u("block", ["ser"] + list("abcdefgh"), ["qh"],
                      ["clk", "clk_inh", "sh_ld_n", "clr_n"], storage=8, group="SRG8",
                      name="shift register")]
    u["74x597"] = [_u("block", ["ser"] + list("abcdefgh"), ["qh"],
                      ["rclk", "srclk", "srload_n", "srclr_n"], storage=16,
                      group="REG + SRG8", name="shift register")]
    u["74x194"] = [_u("block", ["sr_ser", "sl_ser", "a", "b", "c", "d"],
                      ["qa", "qb", "qc", "qd"], ["clk", "clr_n", "s0", "s1"], storage=4,
                      group="SRG4 L/R", name="shift register")]
    u["4094"] = [_u("block", ["data"], [f"q{i}" for i in range(1, 9)] + ["qs", "qs_d"],
                    ["clk", "strobe", "oe"], storage=17, group="SRG8 + LATCH",
                    name="shift register")]
    u["4015"] = [_u("block", [f"data_{h}"], [f"q{i}_{h}" for i in range(1, 5)],
                    [f"clk_{h}", f"rst_{h}"], storage=4, group=f"SRG4 {h.upper()}",
                    name=f"shift register {h.upper()}") for h in "ab"]
    u["4014"] = [_u("block", ["ser"] + [f"p{i}" for i in range(1, 9)], ["q6", "q7", "q8"],
                    ["clk", "ps"], storage=8, group="SRG8", name="shift register")]
    for key, sym in (("74x1G00", "nand"), ("74x1G02", "nor"), ("74x1G08", "and"),
                     ("74x1G32", "or"), ("74x1G86", "xor")):
        u[key] = [_u(sym, ["a", "b"], ["y"], name="gate")]
    for key, sym in (("74x1G10", "nand"), ("74x1G11", "and"), ("74x1G27", "nor")):
        u[key] = [_u(sym, ["a", "b", "c"], ["y"], name="gate")]
    for key, sym in (("74x1G04", "not"), ("74x1G14", "not"), ("74x1G06", "not"),
                     ("74x1G34", "buf"), ("74x1G17", "buf"), ("74x1G07", "buf")):
        u[key] = [_u(sym, ["a"], ["y"], name="gate")]
    u["74x1G125"] = [_u("tri", ["a"], ["y"], ["oe_n"], name="buffer")]
    u["74x1G126"] = [_u("tri", ["a"], ["y"], ["oe"], name="buffer")]
    u["74x1G240"] = [_u("tri_not", ["a"], ["y"], ["oe_n"], name="buffer")]
    u["74x1G79"] = [_u("block", ["d"], ["q"], ["clk"], storage=1, group="D FF",
                       name="flip-flop")]
    u["74x1G80"] = [_u("block", ["d"], ["q_n"], ["clk"], storage=1, group="D FF",
                       name="flip-flop")]
    # ---- more glue
    u["74x03"] = _gates("nand", 4, "ab")
    u["74x09"] = _gates("and", 4, "ab")
    u["74x21"] = _gates("and", 2, "abcd")
    u["74x27"] = _gates("nor", 3, "abc")
    u["74x30"] = [_u("nand", list("abcdefgh"), ["y"], name="gate")]
    for key, active_low_k in (("74x109", True), ("74x112", False)):
        k = "k{i}_n" if active_low_k else "k{i}"
        u[key] = [_u("block", [f"j{i}", k.format(i=i)], [f"q{i}", f"q{i}_n"],
                     [f"clk{i}", f"pre{i}_n", f"clr{i}_n"], storage=1,
                     group=f"JK FF {i}", name=f"flip-flop {i}") for i in (1, 2)]
    u["74x151"] = [_u("block", [f"d{i}" for i in range(8)], ["y", "w"],
                      ["a", "b", "c", "g_n"], group="8:1 MUX", name="multiplexer")]
    u["74x154"] = [_u("block", ["a", "b", "c", "d"], [f"y{i}" for i in range(16)],
                      ["g1_n", "g2_n"], group="4→16 DEC", name="decoder")]
    u["74x173"] = [_u("block", [f"d{i}" for i in range(1, 5)], [f"q{i}" for i in range(1, 5)],
                      ["clk", "clr", "g1_n", "g2_n", "m", "n"], storage=4, group="REG4",
                      name="register")]
    u["74x191"] = [_u("block", ["a", "b", "c", "d"], ["qa", "qb", "qc", "qd", "maxmin", "rco_n"],
                      ["clk", "load_n", "cten_n", "du"], storage=4, group="CTR4 U/D",
                      name="counter")]
    u["74x193"] = [_u("block", ["a", "b", "c", "d"], ["qa", "qb", "qc", "qd", "co_n", "bo_n"],
                      ["up", "down", "load_n", "clr"], storage=5, group="CTR4 U/D",
                      name="counter")]
    for key, sym in (("74x257", "mux"), ("74x258", "mux")):
        u[key] = [_u(sym, [f"a{i}", f"b{i}"], [f"y{i}"], ["s", "oe_n"], name=f"mux {i}")
                  for i in range(1, 5)]
    u["74x259"] = [_u("block", ["d"], [f"q{i}" for i in range(8)],
                      ["s0", "s1", "s2", "g_n", "clr_n"], storage=8, group="LATCH ×8 ADDR",
                      name="addressable latch")]
    u["74x393"] = [_u("block", [], [f"q{c}{i}" for c in "abcd"], [f"clk{i}", f"clr{i}"],
                      storage=4, group=f"CTR4 {i}", name=f"counter {i}") for i in (1, 2)]
    for key in ("74x521", "74x688"):
        u[key] = [_u("block", [f"p{i}" for i in range(8)] + [f"q{i}" for i in range(8)],
                     ["eq_n"], ["g_n"], group="8-BIT P=Q", name="comparator")]
    for key, sym in (("4001", "nor"), ("4011", "nand"), ("4070", "xor"), ("4071", "or"),
                     ("4081", "and")):
        u[key] = _gates(sym, 4, "ab")
    u["4013"] = [_u("block", [f"d{i}"], [f"q{i}", f"q{i}_n"], [f"clk{i}", f"set{i}", f"rst{i}"],
                    storage=1, group=f"D FF {i}", name=f"flip-flop {i}") for i in (1, 2)]
    u["4017"] = [_u("block", [], [f"q{i}" for i in range(10)] + ["co"], ["clk", "inh", "rst"],
                    storage=5, group="÷10 JOHNSON", name="decade counter")]
    u["4040"] = [_u("block", [], [f"q{i}" for i in range(1, 13)], ["clk", "rst"],
                    storage=12, group="CTR12", name="counter")]
    u["4049"] = _gates("not", 6, "a")
    u["4050"] = _gates("buf", 6, "a")
    u["4069"] = _gates("not", 6, "a")
    for key, sym in (("74x2G00", "nand"), ("74x2G02", "nor"), ("74x2G08", "and"),
                     ("74x2G32", "or"), ("74x2G86", "xor")):
        u[key] = _gates(sym, 2, "ab")
    for key, sym in (("74x2G04", "not"), ("74x2G14", "not"), ("74x2G06", "not"),
                     ("74x2G34", "buf"), ("74x2G17", "buf"), ("74x2G07", "buf")):
        u[key] = _gates(sym, 2, "a")
    u["74x2G125"] = [_u("tri", [f"a{i}"], [f"y{i}"], [f"oe{i}_n"], name=f"buffer {i}")
                     for i in (1, 2)]
    u["74x2G126"] = [_u("tri", [f"a{i}"], [f"y{i}"], [f"oe{i}"], name=f"buffer {i}")
                     for i in (1, 2)]
    return u


UNITS: Dict[str, List[Unit]] = _build()
