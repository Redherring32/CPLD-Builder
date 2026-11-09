"""GAL16V8 / GAL20V8 / GAL22V10 target: fit the design into a GAL and write the .jed.

A GAL is an AND/OR array: every output macrocell (OLMC) is one sum of up to
7-16 product terms of the input pins and the fed-back outputs. So the flow is:

1. Yosys flattens the design to simple gates (the simulator's netlist).
2. Every output, register input and output enable becomes a BDD over the
   input pins and the register/latch outputs, and then a minimal sum of
   products (ISOP), in whichever polarity needs fewer terms (each OLMC can
   invert its output for free). An output's value doesn't matter while its
   output enable is off, which often saves terms.
3. The fitter picks the GAL16V8/20V8 mode (simple/complex/registered), places the
   outputs on OLMCs with enough product terms and the inputs on the pins left,
   honouring locked pins.
4. cpldglue writes the JEDEC fuse map itself (the fuse layout follows galette,
   https://github.com/simon-frankau/galette, and is checked against its test
   files), plus a galette/GALasm-compatible .pld with the equations.
5. The fuse map is read back and simulated against the design.

GAL rules that shape what fits: one clock for all registers (pin 1, rising
edge); the 16V8 has no asynchronous reset and its registered outputs share
the /OE pin (11 on the 16V8, 13 on the 20V8); the 22V10 has one asynchronous-reset product term that
resets every register at once. A register that isn't an output still takes a
whole OLMC (and its pin). Latches are built from combinational feedback.

Pin numbers inside this module are DIP pin numbers; the package maps them.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .bdd import Bdd, Cube

Lit = Tuple[int, bool]                # (DIP pin, negated)


# ---- chip descriptions -----------------------------------------------------------
@dataclass(frozen=True)
class Chip:
    name: str
    pins: int
    cols: int
    rows: int
    total: int
    olmc_pins: Tuple[int, ...]        # OLMC i is olmc_pins[i]
    row_start: Tuple[int, ...]
    row_count: Tuple[int, ...]        # rows per OLMC, including the OE row
    columns: Dict[str, Dict[int, int]]   # mode -> pin -> fuse column

    @property
    def gnd(self) -> int:
        return self.pins // 2

    @property
    def vcc(self) -> int:
        return self.pins

    def olmc(self, pin: int) -> Optional[int]:
        return self.olmc_pins.index(pin) if pin in self.olmc_pins else None

    @property
    def is_v8(self) -> bool:                 # GAL16V8 / GAL20V8 (simple/complex/registered)
        return self.name in ("GAL16V8", "GAL20V8")

    @property
    def is_ra(self) -> bool:                 # GAL20RA10: per-register clock / reset / preset
        return self.name == "GAL20RA10"

    @property
    def oe_pin(self) -> int:                 # /OE of the registered outputs (V8 parts)
        return 13 if self.name == "GAL20V8" else 11


_C16_SIMPLE = {1: 2, 2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 11: 30,
               12: 26, 13: 22, 14: 18, 17: 14, 18: 10, 19: 6}
_C16_COMPLEX = {1: 2, 2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 11: 30,
                13: 26, 14: 22, 15: 18, 16: 14, 17: 10, 18: 6}
_C16_REG = {2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28,
            12: 30, 13: 26, 14: 22, 15: 18, 16: 14, 17: 10, 18: 6, 19: 2}
# GAL20V8: same idea as the 16V8, 40 columns (galette's PIN_TO_COL_20_*)
_C20_SIMPLE = {1: 2, 2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 10: 32, 11: 36,
               13: 38, 14: 34, 15: 30, 16: 26, 17: 22, 20: 18, 21: 14, 22: 10, 23: 6}
_C20_COMPLEX = {1: 2, 2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 10: 32, 11: 36,
                13: 38, 14: 34, 16: 30, 17: 26, 18: 22, 19: 18, 20: 14, 21: 10, 23: 6}
_C20_REG = {2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 10: 32, 11: 36,
            14: 38, 15: 34, 16: 30, 17: 26, 18: 22, 19: 18, 20: 14, 21: 10, 22: 6, 23: 2}
# GAL20RA10: pin 1 is /PL (preload), pin 13 /OE; galette's PIN_TO_COL_20RA10
_C20RA = {2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 10: 32, 11: 36,
          14: 38, 15: 34, 16: 30, 17: 26, 18: 22, 19: 18, 20: 14, 21: 10, 22: 6, 23: 2}
_C22 = {1: 0, 2: 4, 3: 8, 4: 12, 5: 16, 6: 20, 7: 24, 8: 28, 9: 32, 10: 36, 11: 40,
        13: 42, 14: 38, 15: 34, 16: 30, 17: 26, 18: 22, 19: 18, 20: 14, 21: 10, 22: 6, 23: 2}

CHIPS: Dict[str, Chip] = {
    "GAL16V8": Chip("GAL16V8", 20, 32, 64, 2194, tuple(range(12, 20)),
                    (56, 48, 40, 32, 24, 16, 8, 0), (8,) * 8,
                    {"simple": _C16_SIMPLE, "complex": _C16_COMPLEX, "registered": _C16_REG}),
    "GAL20V8": Chip("GAL20V8", 24, 40, 64, 2706, tuple(range(15, 23)),
                    (56, 48, 40, 32, 24, 16, 8, 0), (8,) * 8,
                    {"simple": _C20_SIMPLE, "complex": _C20_COMPLEX, "registered": _C20_REG}),
    # Rows per OLMC: OE, CLK, ARST, APRST, then 4 product terms.
    "GAL20RA10": Chip("GAL20RA10", 24, 40, 80, 3274, tuple(range(14, 24)),
                      (72, 64, 56, 48, 40, 32, 24, 16, 8, 0), (8,) * 10, {"": _C20RA}),
    "GAL22V10": Chip("GAL22V10", 24, 44, 132, 5892, tuple(range(14, 24)),
                     (122, 111, 98, 83, 66, 49, 34, 21, 10, 1),
                     (9, 11, 13, 15, 17, 17, 15, 13, 11, 9), {"": _C22}),
}

MODE_TITLES = {"simple": "simple mode (combinational outputs, no output enables)",
               "complex": "complex mode (combinational outputs with output enables)",
               "registered": "registered mode (pin 1 = clock, /OE pin = output enable)",
               "": ""}


def chip_for(device: str) -> Chip:
    for name, c in CHIPS.items():
        if device.upper().startswith(name) or device.upper().replace("ATF", "GAL").startswith(name):
            return c
    raise ValueError(f"{device} is not a GAL")


def dedicated_inputs(chip: Chip, mode: str) -> List[int]:
    if chip.is_ra:
        return list(range(2, 12))
    plain = [p for p in range(1, chip.pins) if p != chip.gnd and p not in chip.olmc_pins]
    if chip.is_v8 and mode == "registered":
        return [p for p in plain if p not in (1, chip.oe_pin)]
    return plain


def olmc_input_pins(chip: Chip, mode: str) -> List[int]:
    """OLMC pins that can be inputs (or read back their own output)."""
    if not chip.is_v8:
        return list(chip.olmc_pins)
    return sorted(p for p in chip.columns[mode] if p in chip.olmc_pins)


def capacity(chip: Chip, mode: str, pin: int, registered: bool) -> int:
    """Product terms for the sum (the OE term is separate)."""
    i = chip.olmc(pin)
    if chip.is_ra:
        return 4
    if not chip.is_v8:
        return chip.row_count[i] - 1
    if mode == "simple" or registered:
        return 8
    return 7


# ---- the program: what goes in each OLMC ------------------------------------------
@dataclass
class Olmc:
    pin: int
    kind: str = "unused"              # reg | comb | input | unused
    active_high: bool = True
    terms: List[List[Lit]] = field(default_factory=list)   # the sum (pin-level semantics)
    oe: Optional[List[Lit]] = None    # one product term; None = always on
    oe_off: bool = False              # output never enabled (buried register / input)
    clk: Optional[List[Lit]] = None   # GAL20RA10: clock term (registers)
    arst: Optional[List[Lit]] = None  # GAL20RA10: async reset term (None = never)
    aprst: Optional[List[Lit]] = None # GAL20RA10: async preset term (None = never)
    name: str = ""
    note: str = ""


@dataclass
class Program:
    chip: Chip
    mode: str = ""                    # GAL16V8 only
    olmcs: Dict[int, Olmc] = field(default_factory=dict)
    ar: Optional[List[Lit]] = None    # GAL22V10 only; None = never
    sp: Optional[List[Lit]] = None
    signature: str = ""
    pin_names: Dict[int, str] = field(default_factory=dict)

    def cell(self, pin: int) -> Olmc:
        return self.olmcs.setdefault(pin, Olmc(pin))


# ---- JEDEC fuse map ------------------------------------------------------------------
@dataclass
class Fuses:
    chip: Chip
    array: List[int]                  # 1 = fuse blown (input not connected)
    xor: List[int]                    # indexed like galette: [num_olmcs-1-i]
    ac1: List[int]
    sig: List[int]
    pt: List[int] = field(default_factory=list)
    syn: int = 0
    ac0: int = 0

    def bits(self) -> List[int]:
        out = list(self.array)
        if self.chip.is_ra:
            out += self.xor + self.sig
        elif self.chip.is_v8:
            out += self.xor + self.sig + self.ac1 + self.pt + [self.syn, self.ac0]
        else:
            for x, a in zip(self.xor, self.ac1):
                out += [x, a]
            out += self.sig
        assert len(out) == self.chip.total, (len(out), self.chip.total)
        return out


def build_fuses(prog: Program, galette_unused: bool = False) -> Fuses:
    """Fuse map for a program. `galette_unused` reproduces galette's setting
    for unused OLMCs (registered, in a GAL16V8 that drives the pin when /OE
    is low); otherwise unused OLMCs are left as inputs (pins floating)."""
    chip, mode = prog.chip, prog.mode
    n = len(chip.olmc_pins)
    f = Fuses(chip, [1] * (chip.rows * chip.cols), [0] * n, [0] * n, [0] * 64,
              [1] * 64 if chip.is_v8 else [], 0, 0)
    if chip.is_v8:
        f.syn, f.ac0 = {"simple": (1, 0), "complex": (1, 1), "registered": (0, 1)}[mode]
    cols = chip.columns[mode if chip.is_v8 else ""]

    # Mode bits first: the 22V10 literal polarity depends on them.
    for i, pin in enumerate(chip.olmc_pins):
        c = prog.olmcs.get(pin, Olmc(pin))
        k = n - 1 - i
        if c.kind in ("reg", "comb") and c.active_high:
            f.xor[k] = 1
        if c.kind == "input":
            f.ac1[k] = 1
        elif c.kind == "comb":
            f.ac1[k] = 0 if (chip.is_v8 and mode == "simple") else 1
        elif c.kind == "unused":
            f.ac1[k] = 0 if galette_unused else 1
            if not chip.is_v8 and not galette_unused:
                f.ac1[k] = 0           # 22V10: OE row cleared either way

    def flip(pin: int) -> bool:        # 22V10 registered feedback is /Q
        if chip.is_v8 or chip.is_ra or pin not in chip.olmc_pins:
            return False
        k = n - 1 - chip.olmc(pin)
        return f.ac1[k] == 0 and f.xor[k] == 1 and prog.olmcs.get(pin, Olmc(pin)).kind == "reg"

    def put_row(row: int, term: Sequence[Lit]) -> None:
        for pin, neg in term:
            if pin not in cols:
                raise ValueError(f"pin {pin} can't be read by the array in {chip.name} "
                                 f"{mode or ''} mode")
            f.array[row * chip.cols + cols[pin] + (1 if neg ^ flip(pin) else 0)] = 0

    def clear(row: int) -> None:
        for c in range(chip.cols):
            f.array[row * chip.cols + c] = 0

    def put_sum(start: int, offset: int, count: int, terms: List[List[Lit]], what: str) -> None:
        if len(terms) > count - offset:
            raise ValueError(f"{what} needs {len(terms)} product terms; the OLMC has "
                             f"{count - offset}")
        for j, t in enumerate(terms):
            put_row(start + offset + j, t)
        for r in range(start + offset + len(terms), start + count):
            clear(r)

    for i, pin in enumerate(chip.olmc_pins):
        c = prog.olmcs.get(pin, Olmc(pin))
        start, count = chip.row_start[i], chip.row_count[i]
        if c.kind not in ("reg", "comb"):
            put_sum(start, 0, count, [], f"pin {pin}")
            continue
        if chip.is_ra:
            # rows: OE, CLK, ARST, APRST, 4 terms. Combinational = ARST and
            # APRST both true (left unprogrammed); its clock row is cleared.
            put_sum(start, 4, count, c.terms, f"pin {pin} ({c.name})")
            if c.oe_off:
                clear(start)
            elif c.oe is not None:
                put_row(start, c.oe)
            if c.kind == "reg":
                if c.clk is None:
                    raise ValueError(f"pin {pin} ({c.name}): register without a clock term")
                put_row(start + 1, c.clk)
                (put_row(start + 2, c.arst) if c.arst is not None else clear(start + 2))
                (put_row(start + 3, c.aprst) if c.aprst is not None else clear(start + 3))
            else:
                clear(start + 1)
            continue
        if chip.is_v8:
            offset = 0 if (mode == "simple" or c.kind == "reg") else 1
        else:
            offset = 1
        put_sum(start, offset, count, c.terms, f"pin {pin} ({c.name})")
        if offset:
            if c.oe_off:
                clear(start)
            elif c.oe is not None:
                put_row(start, c.oe)
    if not chip.is_v8 and not chip.is_ra:
        (put_row(0, prog.ar) if prog.ar is not None else clear(0))
        (put_row(chip.rows - 1, prog.sp) if prog.sp is not None else clear(chip.rows - 1))
    for i, ch in enumerate(prog.signature.encode("ascii", "replace")[:8]):
        for j in range(8):
            f.sig[i * 8 + j] = (ch << j) >> 7 & 1
    return f


def jedec_text(f: Fuses, header: str = "") -> str:
    chip, bits = f.chip, f.bits()
    out = ["\x02", f"{header or 'cpldglue GAL fuse map'}", f"Device:         {chip.name}", "",
           "*F0", "*G0", f"*QF{chip.total}"]
    total = 0
    acc, nbit = 0, 0

    def add(b: int) -> None:
        nonlocal total, acc, nbit
        if b:
            acc |= 1 << nbit
        nbit += 1
        if nbit == 8:
            total = (total + acc) & 0xFFFF
            acc, nbit = 0, 0

    idx = 0
    array = chip.rows * chip.cols
    for r in range(chip.rows):
        row = bits[idx:idx + chip.cols]
        if any(row):
            out.append(f"*L{idx:04d} " + "".join(map(str, row)))
        for b in row:
            add(b)
        idx += chip.cols
    groups = ([len(f.xor), 64] if chip.is_ra else
              [len(f.xor), 64, len(f.ac1), 64, 1, 1] if chip.is_v8 else [2 * len(f.xor), 64])
    for g in groups:
        chunk = bits[idx:idx + g]
        out.append(f"*L{idx:04d} " + "".join(map(str, chunk)))
        for b in chunk:
            add(b)
        idx += g
    assert idx == chip.total and array <= idx
    out.append(f"*C{(total + acc) & 0xFFFF:04x}")
    out.append("*")
    text = "\n".join(out) + "\n\x03"
    return text + f"{sum(text.encode('ascii')) & 0xFFFF:04x}\n"


def read_jedec(text: str) -> Tuple[int, List[int]]:
    """(fuse count, fuse bits) from a JEDEC file."""
    body = text.split("\x02", 1)[-1].split("\x03", 1)[0]
    fields = [x.strip() for x in body.split("*")]
    qf = next(int(x[2:]) for x in fields if x.startswith("QF"))
    default = next((int(x[1:]) for x in fields if x.startswith("F") and x[1:].isdigit()), 0)
    bits = [default] * qf
    for x in fields:
        if x.startswith("L"):
            addr, _, data = x[1:].partition(" ")
            data = re.sub(r"\s", "", data)
            for k, ch in enumerate(data):
                bits[int(addr) + k] = int(ch)
    return qf, bits


# ---- reading the fuse map back: a GAL simulator ------------------------------------
class GalModel:
    """Simulates a GAL from its fuse bits, at pin level."""

    def __init__(self, chip: Chip, bits: List[int]):
        self.chip = chip
        n = len(chip.olmc_pins)
        array = chip.rows * chip.cols
        self.array = bits[:array]
        self.clk_prev: Dict[int, Optional[int]] = {}
        if chip.is_ra:
            self.xor = bits[array:array + n]
            self.ac1 = [0] * n
            self.mode = ""
        elif chip.is_v8:
            self.xor = bits[array:array + n]
            self.ac1 = bits[array + n + 64:array + 2 * n + 64]
            syn, ac0 = bits[chip.total - 2], bits[chip.total - 1]
            self.mode = {(1, 0): "simple", (1, 1): "complex", (0, 1): "registered"}[(syn, ac0)]
        else:
            pairs = bits[array:array + 2 * n]
            self.xor, self.ac1 = pairs[0::2], pairs[1::2]
            self.mode = ""
        cols = chip.columns[self.mode]
        self.col_pin = {c: p for p, c in cols.items()}
        self.state: Dict[int, int] = {}            # registered OLMC pin -> stored value
        self.pins: Dict[int, Optional[int]] = {}   # settled pin values (None = floating)
        self.drive: Dict[int, bool] = {}
        self.ext: Dict[int, Optional[int]] = {}
        self.prev_clk = None
        rng = random.Random(7)
        for i, p in enumerate(chip.olmc_pins):
            if self._kind(i) == "reg":
                self.state[p] = rng.getrandbits(1)

    def _k(self, i: int) -> int:
        return len(self.chip.olmc_pins) - 1 - i

    def _row_all(self, r: int, value: int) -> bool:
        base = r * self.chip.cols
        return all(b == value for b in self.array[base:base + self.chip.cols])

    def _kind(self, i: int) -> str:
        k = self._k(i)
        if self.chip.is_ra:
            start = self.chip.row_start[i]
            if self._row_all(start + 2, 1) and self._row_all(start + 3, 1):
                return "comb"                     # ARST and APRST always true
            return "reg"
        if self.chip.is_v8:
            if self.mode == "simple":
                return "input" if self.ac1[k] else "comb"
            if self.mode == "complex":
                return "comb"
            return "comb" if self.ac1[k] else "reg"
        return "comb" if self.ac1[k] else "reg"

    def _row(self, r: int, colval: Dict[int, int]) -> int:
        base = r * self.chip.cols
        for c in range(self.chip.cols):
            if self.array[base + c] == 0 and not colval.get(c, 0):
                return 0
        return 1

    def _colvals(self) -> Dict[int, int]:
        cv: Dict[int, int] = {}
        chip = self.chip
        for c, p in self.col_pin.items():
            i = chip.olmc(p)
            if i is not None and self._kind(i) == "reg" and not chip.is_ra:
                v = self.state[p]
                if not chip.is_v8:           # 22V10 feeds back /Q
                    v = 1 - v
            else:
                v = self.pins.get(p)
                v = 0 if v is None else v
            cv[c], cv[c + 1] = v, 1 - v
        return cv

    def _sum(self, i: int, cv: Dict[int, int], offset: int) -> int:
        start, count = self.chip.row_start[i], self.chip.row_count[i]
        return int(any(self._row(r, cv) for r in range(start + offset, start + count)))

    def _outputs(self, cv: Dict[int, int]) -> Dict[int, Tuple[bool, int]]:
        chip, out = self.chip, {}
        if chip.is_ra:                       # feedback is the pin; async terms act now
            for i, p in enumerate(chip.olmc_pins):
                start, k = chip.row_start[i], self._k(i)
                oe = self._row(start, cv) and self.pins.get(13) == 0
                ar, ap = self._row(start + 2, cv), self._row(start + 3, cv)
                if ar and ap:
                    s = self._sum(i, cv, 4)
                    v = s
                else:
                    if ar:
                        self.state[p] = 0
                    elif ap:
                        self.state[p] = 1
                    v = self.state.setdefault(p, 0)
                out[p] = (bool(oe), v if self.xor[k] else 1 - v)
            return out
        for i, p in enumerate(chip.olmc_pins):
            kind, k = self._kind(i), self._k(i)
            start = chip.row_start[i]
            if kind == "input":
                out[p] = (False, 0)
            elif kind == "comb":
                simple = chip.is_v8 and self.mode == "simple"
                oe = 1 if simple else self._row(start, cv)
                s = self._sum(i, cv, 0 if simple else 1)
                out[p] = (bool(oe), s if self.xor[k] else 1 - s)
            else:
                if chip.is_v8:
                    oe = self.pins.get(chip.oe_pin) == 0
                    out[p] = (oe, self.state[p])
                else:
                    q = self.state[p]
                    out[p] = (bool(self._row(start, cv)), q if self.xor[k] else 1 - q)
        return out

    def _settle(self) -> None:
        for p, v in self.ext.items():
            self.pins[p] = v
        for _ in range(64):
            if not self.chip.is_v8 and not self.chip.is_ra and self._row(0, self._colvals()):  # 22V10 AR
                for p in self.state:
                    self.state[p] = 0
            cv = self._colvals()
            outs = self._outputs(cv)
            changed = False
            for p, (oe, v) in outs.items():
                new = v if oe else self.ext.get(p)
                self.drive[p] = oe
                if self.pins.get(p) != new:
                    self.pins[p] = new
                    changed = True
            if not changed:
                return
        raise RuntimeError("GAL feedback did not settle")

    def set(self, values: Dict[int, Optional[int]]) -> None:
        self.ext.update(values)

    def step(self) -> None:
        self._settle()
        if self.chip.is_ra:                  # every register has its own clock term
            for _ in range(50):
                cv = self._colvals()
                fire = {}
                for i, p in enumerate(self.chip.olmc_pins):
                    start = self.chip.row_start[i]
                    ck = self._row(start + 1, cv)
                    ar, ap = self._row(start + 2, cv), self._row(start + 3, cv)
                    if self.clk_prev.get(p) == 0 and ck == 1 and not (ar or ap):
                        fire[p] = self._sum(i, cv, 4)
                    self.clk_prev[p] = ck
                if not fire:
                    return
                self.state.update(fire)
                self._settle()
            raise RuntimeError("GAL clock terms did not settle")
        clk = self.pins.get(1)
        has_reg = any(self._kind(i) == "reg" for i in range(len(self.chip.olmc_pins)))
        if has_reg and self.prev_clk == 0 and clk == 1:
            cv = self._colvals()
            sp = (not self.chip.is_v8) and self._row(self.chip.rows - 1, cv)
            new = {}
            for i, p in enumerate(self.chip.olmc_pins):
                if self._kind(i) != "reg":
                    continue
                s = self._sum(i, cv, 0 if self.chip.is_v8 else 1)
                if self.chip.is_v8:
                    new[p] = s if self.xor[self._k(i)] else 1 - s
                else:
                    new[p] = 1 if sp else s
            self.state.update(new)
            self._settle()
        self.prev_clk = clk

    def get(self, pin: int) -> Optional[int]:
        return self.pins.get(pin) if self.drive.get(pin) else None


# ---- from the gate netlist to functions ------------------------------------------------
@dataclass
class Flop:
    q: object                          # netlist bit
    name: str
    var: int = -1                      # BDD variable index (value = Q)
    d: int = 0
    clk: int = 0
    r: int = 0                         # async reset (to 0), BDD
    s: int = 0                         # async set (to 1), BDD


@dataclass
class Latch:
    q: object
    name: str
    var: int = -1
    d: int = 0
    e: int = 0


@dataclass
class OutPort:
    name: str
    bidir: bool
    data: int
    oe: int
    var: int = -1                      # inout: the value read back from the pin


@dataclass
class Logic:
    bdd: Bdd
    inputs: List[str]                  # input and inout port names, in order
    var_of: Dict[str, int]             # port name -> BDD variable
    flops: List[Flop]
    latches: List[Latch]
    outputs: List[OutPort]
    all_inputs: List[str]


_GATE = {
    "$_BUF_": lambda b, c: c["A"],
    "$_NOT_": lambda b, c: b.not_(c["A"]),
    "$_AND_": lambda b, c: b.and_(c["A"], c["B"]),
    "$_NAND_": lambda b, c: b.not_(b.and_(c["A"], c["B"])),
    "$_OR_": lambda b, c: b.or_(c["A"], c["B"]),
    "$_NOR_": lambda b, c: b.not_(b.or_(c["A"], c["B"])),
    "$_XOR_": lambda b, c: b.xor(c["A"], c["B"]),
    "$_XNOR_": lambda b, c: b.not_(b.xor(c["A"], c["B"])),
    "$_ANDNOT_": lambda b, c: b.and_(c["A"], b.not_(c["B"])),
    "$_ORNOT_": lambda b, c: b.or_(c["A"], b.not_(c["B"])),
    "$_MUX_": lambda b, c: b.mux(c["A"], c["B"], c["S"]),
    "$_NMUX_": lambda b, c: b.not_(b.mux(c["A"], c["B"], c["S"])),
}


def extract(netlist: dict, top: str) -> Logic:
    """Functions of the design, from the simulator's gate netlist
    (yosys.sim_netlist: $_DFFSR_PPP_ flip-flops, $_DLATCH_P_ latches)."""
    mod = netlist["modules"][top]
    b = Bdd()
    names: Dict[object, str] = {}
    for nname, n in sorted(mod.get("netnames", {}).items(),
                           key=lambda kv: (kv[1].get("hide_name", 0), len(kv[0]))):
        for i, bit in enumerate(n["bits"]):
            names.setdefault(bit, nname if len(n["bits"]) == 1 else f"{nname}[{i}]")
    ports = mod["ports"]
    var_bit: Dict[object, int] = {}
    var_of: Dict[str, int] = {}
    inputs = []
    for pname, p in ports.items():
        if p["direction"] in ("input", "inout"):
            if len(p["bits"]) != 1:
                raise ValueError(f"port {pname} has {len(p['bits'])} bits; expected 1")
            var_bit[p["bits"][0]] = b.var(pname)
            var_of[pname] = len(b.names) - 1          # variable index
            inputs.append(pname)
    driver: Dict[object, Tuple[str, dict]] = {}
    flops: List[Flop] = []
    latches: List[Latch] = []
    tbufs: Dict[object, Tuple[object, object]] = {}
    for cname, cell in mod["cells"].items():
        t, con = cell["type"], {k: v[0] for k, v in cell["connections"].items()}
        if t == "$scopeinfo":
            continue
        if t in _GATE:
            driver[con["Y"]] = (t, con)
        elif t == "$_DFFSR_PPP_":
            flops.append(Flop(con["Q"], names.get(con["Q"], cname)))
            flops[-1].__dict__["_con"] = con
        elif t == "$_DLATCH_P_":
            latches.append(Latch(con["Q"], names.get(con["Q"], cname)))
            latches[-1].__dict__["_con"] = con
        elif t == "$_TBUF_":
            tbufs[con["Y"]] = (con["A"], con["E"])
        else:
            raise ValueError(f"unsupported cell {t} for a GAL")
    for f in flops:
        var_bit[f.q] = b.var(f.name)
        f.var = len(b.names) - 1
    for l in latches:
        var_bit[l.q] = b.var(l.name)
        l.var = len(b.names) - 1

    memo: Dict[object, int] = {}
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 20000))

    def fn(bit, stack=()) -> int:
        if bit in ("0", "x", "z"):
            return 0
        if bit == "1":
            return 1
        if bit in var_bit:
            return var_bit[bit]
        if bit in memo:
            return memo[bit]
        if bit in stack:
            raise ValueError(f"combinational loop through {names.get(bit, bit)}")
        if bit in tbufs:
            raise ValueError(f"internal 3-state signal {names.get(bit, bit)}: GALs have "
                             f"no internal 3-state buses")
        if bit not in driver:
            raise ValueError(f"undriven signal {names.get(bit, bit)}")
        t, con = driver[bit]
        args = {k: fn(v, stack + (bit,)) for k, v in con.items() if k != "Y"}
        memo[bit] = r = _GATE[t](b, args)
        return r

    try:
        for f in flops:
            con = f.__dict__.pop("_con")
            f.d, f.clk, f.r, f.s = fn(con["D"]), fn(con["C"]), fn(con["R"]), fn(con["S"])
        for l in latches:
            con = l.__dict__.pop("_con")
            l.d, l.e = fn(con["D"]), fn(con["E"])
        outs: List[OutPort] = []
        for pname, p in ports.items():
            if p["direction"] == "input":
                continue
            bit = p["bits"][0]
            if bit in tbufs:
                a, e = tbufs[bit]
                op = OutPort(pname, p["direction"] == "inout", fn(a), fn(e))
            elif p["direction"] == "inout":
                op = OutPort(pname, True, 0, 0)            # only ever read
            else:
                op = OutPort(pname, False, fn(bit), 1)
            if op.bidir:
                op.var = var_of[pname]
            outs.append(op)
    finally:
        sys.setrecursionlimit(old)
    all_inputs = [n for n, p in ports.items() if p["direction"] == "input"]
    return Logic(b, inputs, var_of, flops, latches, outs, all_inputs)


# ---- fitting -----------------------------------------------------------------------------
@dataclass
class Need:
    """Something that takes an OLMC."""
    name: str                          # pin name in the .pld / report
    kind: str                          # reg | comb
    cover: Dict[bool, List[Cube]]      # active_high -> cubes (var space)
    oe: Optional[List[Cube]] = None    # None = always enabled
    oe_off: bool = False
    feedback: bool = False             # its pin value is read back by the array
    port: Optional[str] = None         # the design port at this pin (None = buried)
    var: int = -1                      # the variable whose value is this pin
    var_inverted: bool = False         # pin = NOT var
    forced: Optional[bool] = None      # polarity forced (active_high) by async reset
    global_oe: bool = False            # V8 registered: enabled by the /OE pin
    clk: Optional[Cube] = None         # GAL20RA10: clock term
    rst: Optional[Cube] = None         # GAL20RA10: async reset of the design's flop (q -> 0)
    set_: Optional[Cube] = None        # GAL20RA10: async set (q -> 1)
    what: str = ""

    def terms(self, active_high: bool) -> List[Cube]:
        return self.cover[active_high]

    @property
    def best(self) -> bool:
        if self.forced is not None:
            return self.forced
        return len(self.cover[True]) <= len(self.cover[False])

    @property
    def pts(self) -> int:
        return len(self.cover[self.best])


@dataclass
class FitResult:
    ok: bool
    chip: Chip
    mode: str = ""
    errors: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    pins: Dict[str, int] = field(default_factory=dict)       # signal -> DIP pin
    program: Optional[Program] = None
    cells: List[dict] = field(default_factory=list)          # per OLMC, for the report
    inputs_used: int = 0
    inputs_total: int = 0


def _cover(b: Bdd, f: int, care: int = 1) -> Dict[bool, List[Cube]]:
    """Covers of f (active high) and NOT f (active low), with don't-cares
    where `care` is 0."""
    nf = b.not_(f)
    dc = b.not_(care)
    return {True: b.isop(b.and_(f, care), b.or_(f, dc)),
            False: b.isop(b.and_(nf, care), b.or_(nf, dc))}


def _single_cube(b: Bdd, f: int) -> Optional[Cube]:
    cubes = b.isop(f)
    if len(cubes) == 1:
        return cubes[0]
    return None


def _needs_ra(logic: Logic, chip: Chip, errors: List[str], notes: List[str]):
    """GAL20RA10: every register has its own clock, reset and preset term,
    so any clock (either edge, several clocks) and async set/reset fit, as
    long as each is one product term. Feedback comes from the pins, so a
    register that isn't an output still drives its pin."""
    b = logic.bdd
    needs: List[Need] = []
    flop_by_var = {f.var: f for f in logic.flops}
    latch_by_var = {l.var: l for l in logic.latches}
    shared: Dict[int, OutPort] = {}
    inverted: Dict[int, bool] = {}
    for op in logic.outputs:
        lit = b.as_literal(op.data)
        if op.bidir or op.oe != 1 or not lit or lit[0] in shared:
            continue
        if lit[0] in flop_by_var:
            shared[lit[0]] = op
            inverted[lit[0]] = lit[1] == 0
        elif lit[0] in latch_by_var and lit[1] == 1:
            shared[lit[0]] = op
    for f in logic.flops:
        clk = _single_cube(b, f.clk)
        if clk is None:
            errors.append(f"flip-flop {f.name}: its clock needs more than one product term")
            continue
        rst = _single_cube(b, f.r) if f.r else None
        st = _single_cube(b, f.s) if f.s else None
        if (f.r and rst is None) or (f.s and st is None):
            errors.append(f"flip-flop {f.name}: its asynchronous set/reset needs more than one "
                          f"product term")
            continue
        if f.r and f.s and b.and_(f.r, f.s) != 0:
            errors.append(f"flip-flop {f.name}: set and reset can be active together; the "
                          f"GAL20RA10 then makes the output combinational")
            continue
        op = shared.get(f.var)
        inv = inverted.get(f.var, False)
        nxt = b.not_(f.d) if inv else f.d
        n = Need(op.name if op else f.name, "reg", _cover(b, nxt), port=op.name if op else None,
                 var=f.var, var_inverted=inv, what=f"register {f.name}")
        n.clk, n.rst, n.set_ = clk, rst, st
        if not op:
            notes.append(f"register {f.name} has no output of its own but drives its pin "
                         f"(the GAL20RA10 feeds registers back from the pins): leave that pin "
                         f"unconnected")
        needs.append(n)
    for l in logic.latches:
        op = shared.get(l.var)
        q = {l.var: 1}

        def with_q(cubes):
            return [{**c, **q} for c in cubes if c.get(l.var, 1) == 1]
        cubes = b.isop(b.and_(l.e, l.d)) + with_q(b.isop(b.not_(l.e))) + with_q(b.isop(l.d))
        uniq = []
        for c in cubes:
            if c not in uniq:
                uniq.append(c)
        needs.append(Need(op.name if op else l.name, "comb", {True: uniq, False: uniq},
                          feedback=True, port=op.name if op else None, var=l.var, forced=True,
                          what=f"latch {l.name}"))
    taken = {op.name for op in shared.values()}
    for op in logic.outputs:
        if op.name in taken:
            continue
        if op.oe == 0:
            needs.append(Need(op.name, "input" if op.bidir else "comb", {True: [], False: []},
                              port=op.name, var=op.var if op.bidir else -1,
                              oe_off=not op.bidir, what="never driven"))
            continue
        n = Need(op.name, "comb", _cover(b, op.data, op.oe), port=op.name,
                 feedback=op.bidir, var=op.var if op.bidir else -1,
                 what="bidirectional pin" if op.bidir else "output")
        if op.oe != 1:
            c = _single_cube(b, op.oe)
            if c is None:
                errors.append(f"{op.name}: its output enable needs more than one product term")
                continue
            n.oe = [c]
        needs.append(n)
    notes.append("tie pin 13 (/OE) to GND and pin 1 (/PL, preload) to VCC")
    return needs, None, None, None


def _needs(logic: Logic, chip: Chip, errors: List[str], notes: List[str]):
    """What needs OLMCs, plus the clock and global-OE signals."""
    if chip.is_ra:
        return _needs_ra(logic, chip, errors, notes)
    b = logic.bdd
    needs: List[Need] = []
    clock = None
    oe_input = None                    # 16V8 registered: the /OE pin's signal
    ar_cube: Optional[Cube] = None

    # -- registers: one clock, rising edge, from a pin
    for f in logic.flops:
        lit = b.as_literal(f.clk)
        if lit is None or lit[0] not in [logic.var_of[i] for i in logic.inputs]:
            errors.append(f"flip-flop {f.name} is clocked by logic, not straight from a pin; "
                          f"a GAL's registers are all clocked from pin 1")
            continue
        if lit[1] == 0:
            errors.append(f"flip-flop {f.name} is clocked on the falling edge; GAL registers "
                          f"clock on the rising edge of pin 1 (invert the clock outside)")
            continue
        name = b.names[lit[0]]
        if clock is None:
            clock = name
        elif clock != name:
            errors.append(f"two clocks ({clock} and {name}); a GAL has one clock, on pin 1")
    # -- asynchronous set/reset
    asyncs = [f for f in logic.flops if f.r or f.s]
    if asyncs:
        if chip.is_v8:
            errors.append("asynchronous set/reset used (e.g. " + asyncs[0].name +
                          f"); the {chip.name} has none - use a GAL22V10")
        else:
            a = b.or_(asyncs[0].r, asyncs[0].s)
            for f in logic.flops:
                fa = b.or_(f.r, f.s)
                if fa != a:
                    errors.append(f"the GAL22V10 has one asynchronous reset for all registers; "
                                  f"{f.name} {'has a different one' if fa else 'has none'} "
                                  f"(compared with {asyncs[0].name})")
                    break
                if f.r and f.s:
                    errors.append(f"{f.name} has both an asynchronous set and reset")
                    break
            else:
                ar_cube = _single_cube(b, a)
                if ar_cube is None:
                    errors.append("the asynchronous reset condition needs more than one "
                                  "product term (the GAL22V10's AR is one term)")
    if errors:
        return needs, clock, oe_input, ar_cube

    flop_by_var = {f.var: f for f in logic.flops}
    latch_by_var = {l.var: l for l in logic.latches}
    shared: Dict[int, OutPort] = {}         # flop/latch var -> port sharing its OLMC
    inverted: Dict[int, bool] = {}
    # Ports that are just a register output (or its complement).
    reg_ports = []
    for op in logic.outputs:
        if op.bidir:
            continue
        lit = b.as_literal(op.data)
        if lit and lit[0] in flop_by_var and lit[0] not in shared:
            reg_ports.append((op, lit))
        elif lit and lit[0] in latch_by_var and lit[1] == 1 and op.oe == 1 \
                and lit[0] not in shared:
            shared[lit[0]] = op
    if chip.is_v8 and reg_ports:
        # Registered outputs share the /OE pin: pick the commonest enable.
        def oe_key(op):
            if op.oe == 1:
                return "1"
            lit = b.as_literal(op.oe)
            if lit and lit[1] == 0 and lit[0] in [logic.var_of[i] for i in logic.all_inputs]:
                return b.names[lit[0]]
            return None
        keys = [oe_key(op) for op, _ in reg_ports]
        cands = [k for k in keys if k]
        pick = max(set(cands), key=cands.count) if cands else None
        if pick and pick != "1":
            oe_input = pick
        kept = []
        for (op, lit), k in zip(reg_ports, keys):
            if k == pick:
                kept.append((op, lit))
        reg_ports = kept
    for op, (v, pol) in reg_ports:
        if v in shared:
            continue
        if not chip.is_v8 and op.oe != 1 and _single_cube(b, op.oe) is None:
            continue                       # a separate comb OLMC can't do it either
        shared[v] = op
        inverted[v] = pol == 0

    # -- register OLMCs
    for f in logic.flops:
        op = shared.get(f.var)
        inv = inverted.get(f.var, False)
        nxt = b.not_(f.d) if inv else f.d
        n = Need(op.name if op else f.name, "reg", _cover(b, nxt), port=op.name if op else None,
                 var=f.var, var_inverted=inv, what=f"register {f.name}")
        if ar_cube is not None:
            # After AR the register holds 0: the pin shows 0 if active high.
            q_after = 0 if f.r else 1
            pin_after = 1 - q_after if inv else q_after
            n.forced = pin_after == 0
        if op:
            if chip.is_v8:
                n.global_oe = True
            elif op.oe != 1:
                n.oe = [_single_cube(b, op.oe)]
        else:
            if chip.is_v8:
                n.global_oe = True
                notes.append(f"register {f.name} has no output of its own but still drives "
                             f"its pin when /OE (pin {chip.oe_pin}) is low: leave that pin unconnected")
            else:
                n.oe_off = True
        needs.append(n)
    # -- latches: Q = E&D | ~E&Q | D&Q (the last term keeps Q glitch-free)
    for l in logic.latches:
        op = shared.get(l.var)
        q = {l.var: 1}

        def with_q(cubes):
            return [{**c, **q} for c in cubes if c.get(l.var, 1) == 1]
        cubes = b.isop(b.and_(l.e, l.d)) + with_q(b.isop(b.not_(l.e))) + with_q(b.isop(l.d))
        uniq = []
        for c in cubes:
            if c not in uniq:
                uniq.append(c)
        n = Need(op.name if op else l.name, "comb", {True: uniq, False: uniq},
                 feedback=True, port=op.name if op else None, var=l.var, forced=True,
                 what=f"latch {l.name}")
        if not op:
            notes.append(f"latch {l.name} has no output of its own but needs its pin "
                         f"(it is built from feedback): leave that pin unconnected")
        needs.append(n)
    # -- other outputs
    taken = {op.name for op in shared.values()}
    for op in logic.outputs:
        if op.name in taken:
            continue
        if op.oe == 0:
            if op.bidir:
                needs.append(Need(op.name, "input", {True: [], False: []}, port=op.name,
                                  var=op.var, what="input (never driven)"))
            else:
                notes.append(f"{op.name} is never driven (its output enable is always off)")
                needs.append(Need(op.name, "comb", {True: [], False: []}, oe_off=True,
                                  port=op.name, what="output (never enabled)"))
            continue
        n = Need(op.name, "comb", _cover(b, op.data, op.oe), port=op.name,
                 feedback=op.bidir, var=op.var if op.bidir else -1,
                 what="bidirectional pin" if op.bidir else "output")
        if op.oe != 1:
            c = _single_cube(b, op.oe)
            if c is None:
                errors.append(f"{op.name}: its output enable needs more than one product "
                              f"term (a GAL OLMC's enable is one term)")
                continue
            n.oe = [c]
        needs.append(n)
    return needs, clock, oe_input, ar_cube


def fit(logic: Logic, device: str, locks: Dict[str, int], name: str = "") -> FitResult:
    """Place the design in the GAL. `locks` and the returned pins are DIP pin numbers."""
    chip = chip_for(device)
    res = FitResult(False, chip)
    needs, clock, oe_input, ar_cube = _needs(logic, chip, res.errors, res.notes)
    if res.errors:
        res.errors = list(dict.fromkeys(res.errors))
        return res
    b = logic.bdd
    registered = any(n.kind == "reg" for n in needs)
    if chip.is_v8:
        if registered:
            modes = ["registered"]
        else:
            modes = ["simple", "complex", "registered"]
    else:
        modes = [""]
    used_vars = set()
    for n in needs:
        for cubes in n.cover.values():
            for c in cubes:
                used_vars |= set(c)
        for c in (n.oe or []):
            used_vars |= set(c)
    if ar_cube:
        used_vars |= set(ar_cube)
    for n in needs:
        for c in (n.clk, n.rst, n.set_):
            if c:
                used_vars |= set(c)
    errs_by_mode = []
    for mode in modes:
        r = _place(logic, chip, mode, needs, clock, oe_input, ar_cube, locks, used_vars)
        if r.ok:
            r.notes = res.notes + r.notes
            r.program.signature = re.sub(r"[^A-Za-z0-9_]", "", name)[:8]
            return r
        errs_by_mode.append((mode, r.errors))
    res.errors = errs_by_mode[0][1] if len(errs_by_mode) == 1 else \
        [f"{MODE_TITLES[m].split(' (')[0]}: {e}" for m, es in errs_by_mode for e in es]
    res.errors = list(dict.fromkeys(res.errors))
    return res


def _place(logic: Logic, chip: Chip, mode: str, needs: List[Need], clock, oe_input,
           ar_cube, locks: Dict[str, int], used_vars) -> FitResult:
    b = logic.bdd
    res = FitResult(False, chip, mode)
    cols = chip.columns[mode if chip.is_v8 else ""]
    pins: Dict[str, int] = {}
    reserved: Dict[int, str] = {}
    if clock:
        reserved[1] = clock
    if chip.is_v8 and mode == "registered":
        if oe_input:
            reserved[chip.oe_pin] = oe_input
        if clock and logic.var_of[clock] in used_vars:
            res.errors.append(f"{clock} is the clock (pin 1) and is also used as logic; in a "
                              f"{chip.name}'s registered mode pin 1 is the clock only")
        if oe_input and logic.var_of[oe_input] in used_vars:
            res.errors.append(f"{oe_input} is the registered outputs' /OE (pin {chip.oe_pin}) and "
                              f"is also used as logic; in registered mode that pin is /OE only")
    if mode == "simple":
        bad = [n.name for n in needs if n.oe is not None or n.feedback or n.oe_off]
        if bad:
            res.errors.append(f"needs output enables or feedback ({', '.join(bad)})")
    for pin, sig in reserved.items():
        if sig in locks and locks[sig] != pin:
            res.errors.append(f"{sig} is locked to pin {locks[sig]} but must be on pin {pin} "
                              f"({'clock' if pin == 1 else '/OE'})")
        pins[sig] = pin
    if res.errors:
        return res

    olmc_in = olmc_input_pins(chip, mode)
    feedback_ok = set(olmc_in)
    # Inputs locked to OLMC pins take those pins away from outputs.
    in_names = [i for i in logic.inputs if i not in pins and
                not any(n.port == i for n in needs)]
    locked_in = {s: p for s, p in locks.items() if s in in_names}
    for s, p in locked_in.items():
        if p not in dedicated_inputs(chip, mode) and p not in olmc_in:
            res.errors.append(f"{s} is locked to pin {p}, which can't be an input here")
        elif p in pins.values():
            res.errors.append(f"pin {p} locked twice")
        else:
            pins[s] = p
    if res.errors:
        return res
    olmc_free = [p for p in chip.olmc_pins if p not in pins.values()]

    def fits(n: Need, pin: int) -> bool:
        if n.port and n.port in locks and locks[n.port] != pin:
            return False
        if n.kind == "input":
            return pin in olmc_in
        if n.feedback and pin not in feedback_ok:
            return False
        if n.kind == "reg" and chip.is_v8 and mode != "registered":
            return False
        return n.pts <= capacity(chip, mode, pin, n.kind == "reg")

    for n in needs:
        if n.port and n.port in locks and locks[n.port] not in chip.olmc_pins:
            res.errors.append(f"{n.port} is locked to pin {locks[n.port]}, which has no "
                              f"output macrocell")
    if res.errors:
        return res
    order = sorted(range(len(needs)), key=lambda k: (not (needs[k].port in locks),
                                                     -needs[k].pts))
    # Prefer pins that can't be inputs, then the smallest OLMC that's big enough.
    pin_order = sorted(olmc_free, key=lambda p: (p in olmc_in,
                                                 capacity(chip, mode, p, False), p))
    match: Dict[int, int] = {}          # pin -> need index

    def augment(k: int, seen: set) -> bool:
        for p in pin_order:
            if p in seen or not fits(needs[k], p):
                continue
            seen.add(p)
            if p not in match or augment(match[p], seen):
                match[p] = k
                return True
        return False

    for k in order:
        if not augment(k, set()):
            n = needs[k]
            big = max((capacity(chip, mode, p, n.kind == "reg") for p in olmc_free), default=0)
            if n.pts > big:
                res.errors.append(f"{n.name} ({n.what}) needs {n.pts} product terms; the "
                                  f"largest OLMC has {big}")
            else:
                res.errors.append(f"no OLMC left for {n.name} ({n.what})")
    if res.errors:
        used = len(needs)
        res.errors.append(f"{used} OLMCs needed, {len(olmc_free)} available")
        return res
    for p, k in match.items():
        pins[needs[k].name] = p

    # Inputs: dedicated pins first, then spare OLMC pins.
    free_in = [p for p in dedicated_inputs(chip, mode) if p not in pins.values()] + \
              [p for p in olmc_in if p not in pins.values() and p not in match]
    used_inputs = [i for i in in_names if i not in pins and logic.var_of[i] in used_vars]
    idle_inputs = [i for i in in_names if i not in pins and logic.var_of[i] not in used_vars]
    for i in used_inputs:
        if not free_in:
            res.errors.append(f"out of input pins: {len(used_inputs)} inputs, "
                              f"{len(dedicated_inputs(chip, mode))} input pins plus the "
                              f"spare OLMC pins")
            return res
        pins[i] = free_in.pop(0)
    for i in idle_inputs:
        if free_in:
            pins[i] = free_in.pop(0)
        else:
            res.notes.append(f"{i} isn't used by any output and got no pin")

    # Literal for a variable.
    lit_of: Dict[int, Tuple[int, bool]] = {}      # var -> (pin, pin = NOT var)
    for i in logic.inputs:
        if i in pins:
            lit_of[logic.var_of[i]] = (pins[i], False)
    for n in needs:
        if n.var >= 0 and n.name in pins:
            lit_of[n.var] = (pins[n.name], n.var_inverted)

    def lits(c: Cube) -> List[Lit]:
        out = []
        for v, val in sorted(c.items()):
            if v not in lit_of:
                raise ValueError(f"{b.names[v]} has no pin the array can read")
            p, inv = lit_of[v]
            if p not in cols:
                raise ValueError(f"{b.names[v]} is on pin {p}, which the array can't read "
                                 f"in this mode")
            out.append((p, (not val) ^ inv))
        return out

    prog = Program(chip, mode)
    try:
        for p, k in match.items():
            n = needs[k]
            c = prog.cell(p)
            c.name = n.name
            c.note = n.what
            if n.kind == "input":
                c.kind = "input"
                continue
            c.kind = n.kind
            c.active_high = n.best
            c.terms = [lits(x) for x in n.terms(n.best)]
            c.oe_off = n.oe_off
            c.oe = [y for x in n.oe for y in lits(x)] if n.oe else None
            if chip.is_ra and n.kind == "reg":
                c.clk = lits(n.clk)
                # The register holds Q; the pin shows Q (active high) or /Q, and
                # the design's flop is the pin or its complement.
                flip = (not n.best) ^ n.var_inverted
                to0, to1 = (n.set_, n.rst) if flip else (n.rst, n.set_)
                c.arst = lits(to0) if to0 is not None else None
                c.aprst = lits(to1) if to1 is not None else None
        for i in in_names:
            p = pins.get(i)
            if p in chip.olmc_pins:
                prog.cell(p).kind = "input"
                prog.cell(p).name = i
        if ar_cube is not None:
            prog.ar = lits(ar_cube)
    except ValueError as e:
        res.errors.append(str(e))
        return res
    for sig, p in pins.items():
        prog.pin_names[p] = sig
    res.ok, res.pins, res.program = True, pins, prog
    if chip.is_v8 and mode == "registered" and not oe_input:
        res.notes.append(f"tie pin {chip.oe_pin} (/OE) to GND: it enables the registered outputs")
    ded =dedicated_inputs(chip, mode)
    res.inputs_total = len(ded)
    res.inputs_used = sum(1 for p in pins.values() if p in ded)
    for p in chip.olmc_pins:
        c = prog.olmcs.get(p)
        cap = capacity(chip, mode, p, bool(c and c.kind == "reg"))
        res.cells.append({"pin": p, "name": c.name if c else "", "kind": c.kind if c else "unused",
                          "terms": len(c.terms) if c and c.kind in ("reg", "comb") else 0,
                          "capacity": cap, "oe": bool(c and (c.oe or c.oe_off)),
                          "active_high": bool(c and c.active_high), "what": c.note if c else ""})
    return res


# ---- galette / GALasm source -------------------------------------------------------------
def _ident(name: str, used: set) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "S"
    if s[0].isdigit():
        s = "S" + s
    if s.upper() in ("VCC", "GND", "NC", "AR", "SP", "DESCRIPTION"):
        s += "_"
    base, k = s, 2
    while s in used:
        s, k = f"{base}_{k}", k + 1
    used.add(s)
    return s


def pld_text(prog: Program, title: str = "") -> str:
    """The equations as a galette/GALasm source file (pin-level semantics)."""
    chip = prog.chip
    used: set = set()
    names: Dict[int, str] = {}
    for p in range(1, chip.pins + 1):
        if p == chip.gnd:
            names[p] = "GND"
        elif p == chip.vcc:
            names[p] = "VCC"
        elif chip.is_ra and p in (1, 13):
            names[p] = "/PL" if p == 1 else "/OE"
            used.add(names[p][1:])
        elif p in prog.pin_names:
            names[p] = _ident(prog.pin_names[p], used)
        elif p in prog.olmcs and prog.olmcs[p].kind in ("reg", "comb"):
            names[p] = _ident(prog.olmcs[p].name or f"P{p}", used)
        else:
            names[p] = "NC"
    half = chip.pins // 2

    def term(t: List[Lit]) -> str:
        return " * ".join(("/" if neg else "") + names[p] for p, neg in t) if t else "VCC"

    def sop(ts: List[List[Lit]]) -> str:
        if not ts:
            return "GND"
        return "\n    + ".join(term(t) for t in ts)

    lines = [chip.name, (prog.signature or "CPLDGLUE")[:8], "",
             " ".join(names[p] for p in range(1, half + 1)),
             " ".join(names[p] for p in range(half + 1, chip.pins + 1)), ""]
    for p in sorted(prog.olmcs):
        c = prog.olmcs[p]
        if c.kind not in ("reg", "comb"):
            continue
        lhs = ("" if c.active_high else "/") + names[p]
        tri = c.oe is not None or c.oe_off
        if c.kind == "reg":
            lines.append(f"{lhs}.R = {sop(c.terms)}")
        elif tri:
            lines.append(f"{lhs}.T = {sop(c.terms)}")
        else:
            lines.append(f"{lhs} = {sop(c.terms)}")
        if chip.is_ra and c.kind == "reg":
            lines.append(f"{names[p]}.CLK = {term(c.clk or [])}")
            if c.arst is not None:
                lines.append(f"{names[p]}.ARST = {term(c.arst)}")
            if c.aprst is not None:
                lines.append(f"{names[p]}.APRST = {term(c.aprst)}")
        if c.oe_off and not (chip.is_v8 and c.kind == "reg"):
            lines.append(f"{names[p]}.E = GND")
        elif c.oe is not None:
            lines.append(f"{names[p]}.E = {term(c.oe)}")
        lines.append("")
    if prog.ar is not None:
        lines += [f"AR = {term(prog.ar)}", ""]
    lines += ["DESCRIPTION", "", title or "Generated by cpldglue.", ""]
    return "\n".join(lines)


# ---- checking the fuse map against the design ---------------------------------------------
def verify(netlist_path: Path, top: str, fuses: Fuses, pins: Dict[str, int],
           registered: bool = True, vectors: int = 400, seed: int = 1) -> Tuple[bool, str]:
    """Simulate the fuse map and the design side by side on random inputs
    (with clock pulses) and compare every output the design defines."""
    from .sim import Sim
    sim = Sim.from_file(netlist_path, top)
    model = GalModel(fuses.chip, fuses.bits())
    rng = random.Random(seed)
    ins = [n for n, p in sim.ports.items() if p["direction"] == "input" and n in pins]
    outs = [n for n, p in sim.ports.items() if p["direction"] != "input" and n in pins]
    inouts = [n for n in outs if sim.ports[n]["direction"] == "inout"]
    has_reg = registered
    clock = next((n for n, p in pins.items() if p == 1 and n in ins), None) if has_reg else None
    tbuf_en = {y: e for _, e, y in sim.tbuf}

    def design_drives(port: str) -> bool:
        e = tbuf_en.get(sim.ports[port]["bits"][0])
        return e is not None and sim._v(e) == 1
    external: set = set()               # inouts driven from outside right now
    oe11 = next((n for n, p in pins.items() if p == fuses.chip.oe_pin and n in ins), None) \
        if fuses.chip.is_v8 and model.mode == "registered" else None
    bad: List[str] = []
    checked = 0

    def drive(values: Dict[str, Optional[int]]) -> None:
        sim.set(**values)
        for k, v in values.items():
            if k in inouts:
                (external.add if v is not None else external.discard)(k)
        ext = {pins[k]: v for k, v in values.items()}
        if fuses.chip.is_v8 and model.mode == "registered" and oe11 is None:
            ext[fuses.chip.oe_pin] = 0
        if fuses.chip.is_ra:
            ext[13], ext[1] = 0, 1
        model.set(ext)

    def compare(when: str) -> None:
        nonlocal checked
        sim.step()
        model.step()
        for o in outs:
            want = sim.get(o)
            if want is None or o in external:
                continue
            checked += 1
            have = model.get(pins[o])
            if have != want:
                bad.append(f"{o} = {have}, expected {want} ({when})")

    init = {i: 0 for i in ins}
    drive(init)
    compare("start")
    for k in range(vectors):
        v = {i: rng.getrandbits(1) for i in ins if i != clock}
        if clock and has_reg:
            v[clock] = 0
        v.update({i: None for i in inouts})
        drive(v)
        compare(f"vector {k}")
        idle = {i: rng.getrandbits(1) for i in inouts if not design_drives(i)}
        if idle:                         # drive the bidirectional pins the design isn't
            drive(idle)
            compare(f"vector {k}, inputs on {', '.join(idle)}")
        if clock and has_reg:
            drive({clock: 1})
            compare(f"clock edge {k}")
            drive({clock: 0})
            compare(f"after clock {k}")
        if len(bad) > 5:
            break
    if bad:
        return False, (f"WARNING: the GAL's fuse map differs from the design in {len(bad)} "
                       f"case(s), e.g. {bad[0]}")
    return True, (f"Fuse map matches the design ({len(outs)} outputs, {checked} values "
                  f"compared over {vectors} random input sets"
                  + (" with clock pulses" if clock and has_reg else "") + ").")


def model_cells(fuses: Fuses) -> List[Olmc]:
    m = GalModel(fuses.chip, fuses.bits())
    return [Olmc(p, m._kind(i)) for i, p in enumerate(fuses.chip.olmc_pins)]


# ---- the whole flow ------------------------------------------------------------------------
@dataclass
class GalBuild:
    fit: FitResult
    package: str
    pins: Dict[str, int] = field(default_factory=dict)     # signal -> package pin
    jedec: str = ""
    pld: str = ""
    check: str = ""
    check_ok: bool = False

    @property
    def ok(self) -> bool:
        return self.fit.ok and self.check_ok

    def pin_text(self, design_name: str, device: str) -> str:
        lines = [f'CHIP "{design_name}" ASSIGNED TO AN {device} {self.package}']
        for sig, pin in sorted(self.pins.items(), key=lambda kv: kv[1]):
            lines.append(f"{sig:<16} : {pin}")
        return "\n".join(lines) + "\n"


def build(design, r, workdir: Path) -> GalBuild:
    """Fit a generated design (generate.Result) into its GAL and make the fuse map."""
    from . import devices, yosys
    from .generate import sanitize
    dev, pkg = devices.get_package(design.device, design.package)
    if dev.kind != "gal":
        raise ValueError(f"{dev.name} is not a GAL")
    if not r.ok:
        raise ValueError("fix the report errors first: " + "; ".join(r.errors))
    top = sanitize(design.name)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / f"{top}.v").write_text(r.verilog, encoding="utf-8")
    net = yosys.sim_netlist([workdir / f"{top}.v"], top, workdir / "gal.json")
    logic = extract(json.loads(net.read_text(encoding="utf-8")), top)
    here = {p.name for p in r.ports}
    locks = {s: devices.gal_dip_pin(pkg.name, int(p)) for s, p in design.pin_locks.items()
             if s in here}
    fr = fit(logic, dev.name, locks, design.name)
    out = GalBuild(fr, pkg.name)
    if not fr.ok:
        return out
    out.pins = {s: devices.gal_package_pin(pkg.name, p) for s, p in fr.pins.items()}
    for c in fr.cells:
        c["dip"], c["pin"] = c["pin"], devices.gal_package_pin(pkg.name, c["pin"])
    fuses = build_fuses(fr.program)
    out.jedec = jedec_text(fuses, f"cpldglue: {design.name} ({dev.name} {pkg.name})")
    out.pld = pld_text(fr.program, f"{design.name}, generated by cpldglue. Replaces "
                       + ", ".join(f"{ref} ({k})" for ref, k in design.parts.items()) + ".")
    out.check_ok, out.check = verify(net, top, fuses, fr.pins,
                                     any(c.kind == "reg" for c in fr.program.olmcs.values()))
    return out


def write_files(b: GalBuild, design, outdir: Path, top: str) -> List[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    files = {f"{top}.jed": b.jedec, f"{top}.pld": b.pld,
             f"{top}.pin": b.pin_text(design.name, design.device)}
    for name, text in files.items():
        # newline="\n": the JEDEC file checksum covers the exact bytes
        with open(outdir / name, "w", encoding="ascii", errors="replace", newline="\n") as fh:
            fh.write(text)
    return [outdir / n for n in files]


def report_lines(b: GalBuild, device: str) -> List[str]:
    fr = b.fit
    if not fr.ok:
        return ["Does NOT fit:"] + [f"  {e}" for e in fr.errors]
    used = sum(1 for c in fr.cells if c["kind"] in ("reg", "comb"))
    lines = [f"Fits {device}" + (f" in {MODE_TITLES[fr.mode]}" if fr.mode else "") + ":",
             f"  output macrocells: {used} / {len(fr.cells)}"]
    for c in fr.cells:
        pkgpin = c["pin"]
        if c["kind"] in ("reg", "comb"):
            lines.append(f"  pin {pkgpin:>2}: {c['name']:<14} {c['what']:<24} "
                         f"{c['terms']:>2} / {c['capacity']} product terms"
                         + ("" if c["active_high"] else ", active low"))
        elif c["kind"] == "input":
            lines.append(f"  pin {pkgpin:>2}: {c['name']:<14} input")
    cells = {c["name"] for c in fr.cells if c["kind"] != "unused"}
    ins = sorted(((p, s) for s, p in b.pins.items() if s not in cells), key=lambda t: t[0])
    roles = {1: ", clock" if fr.mode == "registered" or any(c["kind"] == "reg" for c in fr.cells)
             else ""}
    if fr.mode == "registered":
        roles[fr.chip.oe_pin] = ", /OE"
    if ins:
        lines.append("  inputs: " + ", ".join(
            f"{s} ({p}{roles.get(gal_dip(b, p), '')})" for p, s in ins))
    lines += [f"note: {n}" for n in fr.notes]
    lines.append(b.check)
    return lines


def gal_dip(b: GalBuild, pin: int) -> int:
    from .devices import gal_dip_pin
    return gal_dip_pin(b.package, pin)


class Session:
    """Cached GAL fit for the editor (keyed by the generated Verilog and locks)."""

    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.cache: Dict[str, dict] = {}

    def payload(self, design, r) -> dict:
        key = hashlib.sha1((design.device + design.package + r.verilog
                            + json.dumps(design.pin_locks, sort_keys=True)).encode()).hexdigest()
        if key not in self.cache:
            b = build(design, r, self.workdir / key[:12])
            fr = b.fit
            self.cache = {key: {
                "ok": True, "fits": fr.ok, "errors": fr.errors, "notes": fr.notes,
                "mode": fr.mode, "mode_title": MODE_TITLES.get(fr.mode, ""),
                "cells": fr.cells if fr.ok else [],
                "pins": b.pins, "check": b.check, "check_ok": b.check_ok,
                "pld": b.pld,
            }}
        return self.cache[key]
