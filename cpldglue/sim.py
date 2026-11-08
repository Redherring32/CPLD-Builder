"""Tiny gate-level simulator for Yosys JSON netlists.

Feed it the output of yosys.sim_netlist(). Values are 0, 1 or None
(unknown / high impedance). Supported cells: the simple $_..._ gates,
$_TBUF_, $_DFFSR_PPP_ (reset wins over set) and $_DLATCH_P_.

    s = Sim.from_file("design.json")
    s.set(a=1, b=0); s.step(); s.get("y")

Clock edges are detected between successive step() calls, so change a
clock on its own step, not together with the data it samples.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

V = Optional[int]


def _not(a: V) -> V:
    return None if a is None else 1 - a


def _and(a: V, b: V) -> V:
    if a == 0 or b == 0:
        return 0
    return None if a is None or b is None else 1


def _or(a: V, b: V) -> V:
    if a == 1 or b == 1:
        return 1
    return None if a is None or b is None else 0


def _xor(a: V, b: V) -> V:
    return None if a is None or b is None else a ^ b


def _mux(a: V, b: V, s: V) -> V:
    if s is None:
        return a if a == b else None
    return b if s else a


GATES = {
    "$_BUF_": lambda c: c["A"],
    "$_NOT_": lambda c: _not(c["A"]),
    "$_AND_": lambda c: _and(c["A"], c["B"]),
    "$_NAND_": lambda c: _not(_and(c["A"], c["B"])),
    "$_OR_": lambda c: _or(c["A"], c["B"]),
    "$_NOR_": lambda c: _not(_or(c["A"], c["B"])),
    "$_XOR_": lambda c: _xor(c["A"], c["B"]),
    "$_XNOR_": lambda c: _not(_xor(c["A"], c["B"])),
    "$_ANDNOT_": lambda c: _and(c["A"], _not(c["B"])),
    "$_ORNOT_": lambda c: _or(c["A"], _not(c["B"])),
    "$_MUX_": lambda c: _mux(c["A"], c["B"], c["S"]),
    "$_NMUX_": lambda c: _not(_mux(c["A"], c["B"], c["S"])),
}


class Sim:
    def __init__(self, netlist: dict, top: Optional[str] = None):
        mods = netlist["modules"]
        if top is None:
            top = next(n for n, m in mods.items()
                       if m.get("attributes", {}).get("top"))
        m = mods[top]
        self.ports: Dict[str, dict] = m["ports"]
        self.netnames: Dict[str, dict] = m.get("netnames", {})
        self.comb: List[tuple] = []
        self.tbuf: List[tuple] = []
        self.dff: List[list] = []     # [C, S, R, D, Q, state, prevC]
        self.latch: List[list] = []   # [E, D, Q, state]
        for name, c in m["cells"].items():
            t, con = c["type"], c["connections"]
            pins = {k: v[0] for k, v in con.items()}
            if t == "$scopeinfo":          # hierarchy marker left by flatten
                continue
            if t in GATES:
                ins = {k: v for k, v in pins.items() if k != "Y"}
                self.comb.append((GATES[t], ins, pins["Y"]))
            elif t == "$_TBUF_":
                self.tbuf.append((pins["A"], pins["E"], pins["Y"]))
            elif t == "$_DFFSR_PPP_":
                self.dff.append([pins["C"], pins["S"], pins["R"], pins["D"],
                                 pins["Q"], None, None])
            elif t == "$_DLATCH_P_":
                self.latch.append([pins["E"], pins["D"], pins["Q"], None])
            else:
                raise ValueError(f"simulator does not support cell {t} ({name})")
        self.val: Dict = {}
        self.ext: Dict = {}            # externally driven bits (inputs, inouts)
        self.contention: List[str] = []

    @classmethod
    def from_file(cls, path, top: Optional[str] = None) -> "Sim":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")), top)

    # ------------------------------------------------------------------
    def _v(self, bit) -> V:
        if bit == "0":
            return 0
        if bit == "1":
            return 1
        if isinstance(bit, str):
            return None
        return self.val.get(bit)

    def set(self, **values) -> None:
        """Drive input/inout ports. Integers spread across multi-bit ports;
        None releases an inout (high impedance)."""
        for name, value in values.items():
            p = self.ports[name]
            if p["direction"] == "output":
                raise ValueError(f"{name} is an output")
            for i, bit in enumerate(p["bits"]):
                self.ext[bit] = None if value is None else (value >> i) & 1

    def get(self, name: str) -> V:
        bits = self.ports[name]["bits"]
        out = 0
        for i, bit in enumerate(bits):
            v = self._v(bit)
            if v is None:
                return None
            out |= v << i
        return out

    def get_wire(self, name: str) -> V:
        """Value of any named wire that survived synthesis (None if unknown
        or not present)."""
        info = self.netnames.get(name)
        if info is None:
            return None
        out = 0
        for i, bit in enumerate(info["bits"]):
            v = self._v(bit)
            if v is None:
                return None
            out |= v << i
        return out

    def _settle(self) -> None:
        for _ in range(10000):
            changed = False

            def put(bit, v):
                nonlocal changed
                if not isinstance(bit, str) and self.val.get(bit, "unset") != v:
                    self.val[bit] = v
                    changed = True

            for bit, v in self.ext.items():
                if not any(bit == y for _, _, y in self.tbuf):
                    put(bit, v)
            for fn, ins, y in self.comb:
                put(y, fn({k: self._v(b) for k, b in ins.items()}))
            for a, e, y in self.tbuf:
                ev = self._v(e)
                if ev == 1:
                    put(y, self._v(a))
                    if self.ext.get(y) is not None:
                        self.contention.append(f"bit {y}")
                else:
                    put(y, self.ext.get(y))
            for l in self.latch:
                if self._v(l[0]) == 1:
                    l[3] = self._v(l[1])
                put(l[2], l[3])
            for f in self.dff:
                if self._v(f[2]) == 1:
                    f[5] = 0
                elif self._v(f[1]) == 1:
                    f[5] = 1
                put(f[4], f[5])
            if not changed:
                return
        raise RuntimeError("combinational loop did not settle")

    def step(self) -> None:
        self._settle()
        for _ in range(100):
            fire = []
            for f in self.dff:
                c = self._v(f[0])
                if f[6] == 0 and c == 1 and self._v(f[1]) != 1 and self._v(f[2]) != 1:
                    fire.append((f, self._v(f[3])))
            for f in self.dff:
                f[6] = self._v(f[0])
            if not fire:
                return
            for f, d in fire:
                f[5] = d
            self._settle()
        raise RuntimeError("clock edges did not settle")
