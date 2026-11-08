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
    return u


UNITS: Dict[str, List[Unit]] = _build()
