"""GreenPAK SLG46826 / SLG46824 bitstream: place the mapped logic and write the
configuration NVM ourselves, then check it by simulation.

The configuration is 2048 bits (256 bytes); register bit n is bit n % 8 of byte
n // 8. Every input of every cell, every pin output and output enable is a
6-bit select on the connection matrix (Table 22): it picks one of the 64
matrix inputs (Table 21: pins' digital inputs, cell outputs, 0 = GND,
63 = VDD). Cells hold their truth tables and DFF settings in the register map
(Table 59). The tables are read from the datasheet (rev 3.25) into
data/slg46826.json; the cell list below cites the register map directly.

Cells used:
  - 2-bit LUT0-2 / DFF0-2 (DFF: clock + data, no reset)
  - 2-bit LUT3 (the pattern-generator cell, used as a LUT)
  - 3-bit LUT0-5 / DFF3-8 (DFF: clock, data, and nRST or nSET)
  - 3-bit LUT6 (the pipe-delay cell, used as a LUT)
  - 3-bit LUT7-13 and 4-bit LUT0, the multi-function cells, as LUTs only
    (their "single LUT" mode is the all-zero mode code; their flip-flop mode
    codes aren't used yet)

Programming (In-System Programming Guide, ISPG-SLG46824/6 rev 1.5): pages
0-13 (bytes 00h-DFh) are erased and written over I2C. Page 14 (protection)
and page 15 (factory service data) are never written. Fields this module
doesn't generate (the I2C control code at byte CAh, oscillators, ...) are
kept from the chip: the programmer reads the chip first and only replaces
the bits in `owned`.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

DATA = Path(__file__).parent / "data" / "slg46826.json"
SUPPORTED = ("SLG46826", "SLG46824")
GND, VDD = 0, 63


# What each cell input is in DFF mode, by kind of DFF:
#   "2"   2-bit LUT/DFF: CLK, D
#   "3"   3-bit LUT/DFF: CLK, D, nRST or nSET
#   "3m"  multi-function 3-bit LUT/DFF: CLK, nRST or nSET, D
#   "4"   multi-function 4-bit LUT/DFF: CLK, nRST, nSET, D
DFF_ROLES = {"2": ("clk", "d"), "3": ("clk", "d", "rs"), "3m": ("clk", "rs", "d"),
             "4": ("clk", "rst", "set", "d")}


@dataclass(frozen=True)
class Cell:
    name: str
    inputs: Tuple[int, ...]          # matrix outputs feeding IN0, IN1, ... (DFF: see DFF_ROLES)
    out: int                         # its matrix input number
    truth: Tuple[int, int]           # register bits [lo, hi] of the truth table / settings byte
    select: Optional[int] = None     # register bit: 1 = DFF (the LUT/DFF select)
    dff: str = ""                    # "" (LUT only) or a DFF_ROLES kind
    zero: Tuple[int, ...] = ()       # other mode bits, 0 for both LUT and DFF use

    @property
    def width(self) -> int:
        return len(self.inputs)

    def role(self, name: str) -> Optional[int]:
        """Index of the cell input that is `name` in DFF mode, or None."""
        roles = DFF_ROLES.get(self.dff, ())
        return roles.index(name) if name in roles else None


def _r(a: int, b: int) -> Tuple[int, ...]:
    return tuple(range(a, b + 1))


# Register map (Table 59) and Matrix Output table (Table 22) of the SLG46826.
# The multi-function cells' LUT/DFF select bits are from their block
# diagrams and the mode tables, and match Go Configure projects that use
# them as DFFs (tests/reference/greenpak).
CELLS: List[Cell] = [
    Cell("2-bit LUT0/DFF0", (0, 1), 14, (1152, 1155), 1232, "2"),
    Cell("2-bit LUT1/DFF1", (4, 5), 15, (1156, 1159), 1233, "2"),
    Cell("2-bit LUT2/DFF2", (6, 7), 16, (1160, 1163), 1234, "2"),
    Cell("2-bit LUT3", (2, 3), 17, (1164, 1167), 1235),
    Cell("3-bit LUT0/DFF3", (8, 9, 10), 18, (1184, 1191), 1236, "3", (1237,)),
    Cell("3-bit LUT1/DFF4", (11, 12, 13), 19, (1192, 1199), 1238, "3"),
    Cell("3-bit LUT2/DFF5", (14, 15, 16), 20, (1200, 1207), 1239, "3"),
    Cell("3-bit LUT3/DFF6", (17, 18, 19), 21, (1208, 1215), 1240, "3"),
    Cell("3-bit LUT4/DFF7", (20, 21, 22), 22, (1216, 1223), 1241, "3"),
    Cell("3-bit LUT5/DFF8", (23, 24, 25), 23, (1224, 1231), 1242, "3"),
    Cell("3-bit LUT6", (26, 27, 28), 24, (1248, 1255), 1257, zero=(1258,)),
    Cell("4-bit LUT0/DFF9", (30, 31, 32, 33), 39, (1288, 1303), 1282, "4",
         (1280, 1281, 1283, 1284, 1285, 1286)),
    Cell("3-bit LUT7/DFF10", (34, 35, 36), 40, (1344, 1351), 1339, "3m", (1337, 1338, 1340, 1341)),
    Cell("3-bit LUT8/DFF11", (37, 38, 39), 41, (1376, 1383), 1394, "3m", _r(1372, 1375)),
    Cell("3-bit LUT9/DFF12", (40, 41, 42), 42, (1416, 1423), 1411, "3m", (1409, 1410, 1412, 1413)),
    Cell("3-bit LUT10/DFF13", (43, 44, 45), 43, (1448, 1455), 1466, "3m", _r(1444, 1447)),
    Cell("3-bit LUT11/DFF14", (46, 47, 48), 44, (1488, 1495), 1483, "3m", (1481, 1482, 1484, 1485)),
    Cell("3-bit LUT12/DFF15", (49, 50, 51), 45, (1520, 1527), 1538, "3m", _r(1516, 1519)),
    Cell("3-bit LUT13/DFF16", (52, 53, 54), 46, (1560, 1567), 1556, "3m", _r(1552, 1555)),
]
RESERVED_OUTPUTS = {29, 66, 92, 93, 94, 95}
# I2C output-expander select bits (0 = pin output from the matrix), per pin.
EXPANDER_SELECT = {"IO0": 1593, "IO5": 1595, "IO6": 1597, "IO9": 1599}
# Bits that change while the chip runs or are factory-only (ISPG Table 4):
# ignore them when verifying a read-back.
VOLATILE = set([832, 840, 848, 849, 856, 857, 1048, 1134, 1263, 1543]
               + list(range(927, 976)) + list(range(984, 1024)) + list(range(1608, 1616))
               + list(range(1632, 1661)) + list(range(1816, 1824)) + list(range(1832, 1840))
               + list(range(1920, 2048)))
PAGES = 14                            # pages 0..13 (bytes 00h-DFh) are written
CONTROL_CODE_BITS = (1616, 1619)      # byte CAh b3..b0, default 0001


def load_data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


# ---- placement ------------------------------------------------------------------------------
@dataclass
class Placed:
    cell: Cell
    kind: str                         # "lut", "dff" or "latch"
    inputs: List[str]                 # net per cell input, in the cell's order; "0"/"1" constants
    truth: List[int] = field(default_factory=list)
    out_net: str = ""
    qb: bool = False
    nset: bool = False


@dataclass
class Config:
    placed: List[Placed]
    pins: Dict[str, dict]             # IOx -> {"signal", "dir": in/out/inout, "data", "oe"}
    errors: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _extend(truth: Sequence[int], width: int, cell_width: int) -> List[int]:
    """A LUT's truth table in a wider cell (the extra inputs are tied low)."""
    mask = (1 << width) - 1
    return [truth[k & mask] for k in range(1 << cell_width)]


def place(mapping, port_dirs: Dict[str, str], pin_names: Dict[str, str],
          open_drain: Sequence[str] = ()) -> Config:
    """mapping: greenpak.Mapping; port_dirs: port -> input/output/inout;
    pin_names: port -> IOx name of its pin; open_drain: open-collector
    outputs (their pins use the open-drain output mode)."""
    from .greenpak import Lut
    cfg = Config([], {})
    luts = list(mapping.luts)
    flops = list(mapping.flops)
    inverted: Dict[str, str] = {}

    def inverter(net: str) -> str:
        """One inverter (a 1-input LUT) per net that needs one."""
        if net not in inverted:
            inverted[net] = f"__inv_{net}"
            luts.append(Lut(inverted[net], [net], [1, 0]))
        return inverted[net]

    # pins (first: an open-drain pin may need an inverter)
    pin_data = load_data()["pins"]
    for port, d in port_dirs.items():
        io = pin_names.get(port)
        if io is None:
            cfg.errors.append(f"{port} has no pin")
            continue
        entry = {"signal": port, "dir": d, "od": port in open_drain}
        if d != "input":
            if port in mapping.tbufs:
                entry["data"], entry["oe"] = mapping.tbuf_data[port], mapping.tbufs[port]
                if entry["od"] and entry["data"] == "0" and pin_data[io].get("matrix_oe") is None:
                    # open collector on a pin without an OE input: the
                    # open-drain output pulls low while the enable is high
                    entry["data"], entry["oe"] = inverter(entry["oe"]), "1"
            else:
                entry["data"], entry["oe"] = mapping.port_nets.get(port, port), "1"
        cfg.pins[io] = entry

    jobs: List[Tuple[str, object, List[Cell]]] = []
    for f in flops:
        clk = f.clock
        # DFFs clock on the rising edge; latches are transparent while CLK is low.
        if (f.kind == "DFF" and f.clock_falling) or (f.kind == "latch" and not f.clock_falling):
            clk = inverter(f.clock)
        # cheapest cell first: plain DFFs, then ones with nRST/nSET, then the 4-bit one
        if f.reset and f.set:
            kinds = ("4",)
        elif f.reset or f.set:
            kinds = ("3", "3m", "4")
        else:
            kinds = ("2", "3", "3m", "4")
        cands = [c for k in kinds for c in CELLS if c.dff == k]
        jobs.append(("ff", (f, clk), cands))
    for l in luts:
        w = len(l.inputs)
        cands = [c for c in CELLS if c.width >= w]
        # cheapest first: LUT-only cells of the right size, then DFF-capable ones, then bigger
        cands.sort(key=lambda c: (c.width - w, c.dff != "", c.width))
        # LUT-only cells first, then the DFF-capable ones (kept for DFFs if possible)
        jobs.append(("lut", l, cands))

    # bipartite matching (most constrained first)
    order = sorted(range(len(jobs)), key=lambda k: len(jobs[k][2]))
    match: Dict[str, int] = {}

    def augment(k: int, seen: set) -> bool:
        for c in jobs[k][2]:
            if c.name in seen:
                continue
            seen.add(c.name)
            if c.name not in match or augment(match[c.name], seen):
                match[c.name] = k
                return True
        return False

    for k in order:
        if not augment(k, set()):
            kind, obj, _ = jobs[k]
            what = f"flip-flop {obj[0].q}" if kind == "ff" else \
                f"{len(obj.inputs)}-input LUT {obj.out}"
            cfg.errors.append(f"no free cell for {what}")
    by_name = {c.name: c for c in CELLS}
    for cname, k in match.items():
        cell = by_name[cname]
        kind, obj, _ = jobs[k]
        if kind == "lut":
            ins = list(obj.inputs) + ["0"] * (cell.width - len(obj.inputs))
            cfg.placed.append(Placed(cell, "lut", ins, _extend(obj.truth, len(obj.inputs), cell.width),
                                     obj.out))
        else:
            f, clk = obj
            nets = {"clk": clk, "d": f.d, "rst": f.reset or "1", "set": f.set or "1",
                    "rs": f.set or f.reset or "1"}          # "1": inactive nRST/nSET
            ins = [nets[r] for r in DFF_ROLES[cell.dff]]
            nset = bool(f.set) and cell.dff in ("3", "3m")
            cfg.placed.append(Placed(cell, "latch" if f.kind == "latch" else "dff", ins, [],
                                     f.q, nset=nset))
    return cfg


# ---- encoding -------------------------------------------------------------------------------
def encode(cfg: Config, data: dict, base: Optional[List[int]] = None) -> Tuple[List[int], List[int]]:
    """(bits, owned): the 2048 configuration bits, and which of them this
    design defines (the rest come from `base`: the chip's own image when
    programming, else zeros with the default I2C control code 0001)."""
    bits = list(base) if base else [0] * 2048
    if not base:
        bits[CONTROL_CODE_BITS[0]] = 1                     # control code 0001
    owned = [0] * 2048

    def put(lo: int, hi: int, value: int) -> None:
        for i, b in enumerate(range(lo, hi + 1)):
            bits[b] = (value >> i) & 1
            owned[b] = 1

    mo = {int(k): v for k, v in data["matrix_outputs"].items()}
    # sources: matrix input number of every net
    src: Dict[str, int] = {"0": GND, "1": VDD}
    pins = data["pins"]
    for io, p in cfg.pins.items():
        if p["dir"] != "output" and pins[io].get("matrix_in") is not None:
            src[p["signal"]] = pins[io]["matrix_in"]
    for pl in cfg.placed:
        src[pl.out_net] = pl.cell.out
    missing = set()

    def sel(output: int, net: str) -> None:
        if net not in src:
            missing.add(net)
            return
        lo, hi = mo[output]["bits"]
        put(lo, hi, src[net])

    # every matrix output we don't use reads GND
    for n, o in mo.items():
        if n not in RESERVED_OUTPUTS:
            put(o["bits"][0], o["bits"][1], GND)
    # cells: clear all, then program the used ones
    for c in CELLS:
        put(c.truth[0], c.truth[1], 0)
        if c.select is not None:
            put(c.select, c.select, 0)
        for z in c.zero:
            put(z, z, 0)
    for pl in cfg.placed:
        c = pl.cell
        for i, net in enumerate(pl.inputs):
            sel(c.inputs[i], net)
        if pl.kind == "lut":
            put(c.truth[0], c.truth[1], sum(v << i for i, v in enumerate(pl.truth)))
        else:
            put(c.select, c.select, 1)
            # settings, from the top of the truth-table field: latch, QB,
            # (3-bit: nSET instead of nRST), initial polarity
            top = c.truth[1]
            put(top, top, 1 if pl.kind == "latch" else 0)
            put(top - 1, top - 1, 1 if pl.qb else 0)
            if c.dff in ("3", "3m"):
                put(top - 2, top - 2, 1 if pl.nset else 0)
                put(top - 3, top - 3, 0)
            else:
                put(top - 2, top - 2, 0)
    # pins: as Go Configure sets them up. Unused pins are digital inputs
    # with a 1M pull-down and the output off; used ones have no pull.
    for io, p in pins.items():
        used = cfg.pins.get(io)
        if "input_mode" in p:
            put(*p["input_mode"], 0)                      # digital in, no Schmitt trigger
        od = bool(used and used.get("od"))
        put(*p["output_mode"], 2 if od else 0)            # 1x open-drain / push-pull
        put(*p["pull_res"], 0 if used else 3)             # floating / 1M
        put(*p["pull_up"], 0)                             # (pull-down)
        if io in EXPANDER_SELECT:
            put(EXPANDER_SELECT[io], EXPANDER_SELECT[io], 0)
        out = used is not None and used["dir"] != "input"
        if p.get("oe_bit"):
            put(*p["oe_bit"], 1 if out else 0)
            if out and used["oe"] != "1":
                cfg.errors.append(f"{used['signal']} is 3-state but {io} has no output enable")
        if p.get("matrix_out") is not None and out:
            sel(p["matrix_out"], used["data"])
        if p.get("matrix_oe") is not None and out:
            sel(p["matrix_oe"], used["oe"])
    if missing:
        cfg.errors.append("no source for net(s) " + ", ".join(sorted(missing)))
    return bits, owned


# ---- writing --------------------------------------------------------------------------------
def to_bytes(bits: Sequence[int]) -> bytes:
    return bytes(sum(bits[8 * i + k] << k for k in range(8)) for i in range(len(bits) // 8))


def from_bytes(data: bytes) -> List[int]:
    return [(b >> k) & 1 for b in data for k in range(8)]


def txt_file(bits: Sequence[int], owned: Sequence[int]) -> str:
    """One line per register bit, as GreenPAK Designer's bit list and
    openfpga's bitstream files: index, value, comment."""
    lines = ["index\t\tvalue\t\tcomment"]
    for i, b in enumerate(bits):
        lines.append(f"{i}\t\t{b}\t\t//{'' if owned[i] else ' kept'}")
    return "\n".join(lines) + "\n"


def arduino_sketch(bits: Sequence[int], owned: Sequence[int], name: str) -> str:
    """An Arduino sketch that programs the configuration over I2C (Wire):
    read the chip, keep the bits this design doesn't define, erase and write
    pages 0-13, then read back and compare."""
    data, mask = to_bytes(bits)[:PAGES * 16], to_bytes(owned)[:PAGES * 16]
    vol = to_bytes([1 if i in VOLATILE else 0 for i in range(2048)])[:PAGES * 16]

    def arr(b: bytes) -> str:
        return ",\n  ".join(", ".join(f"0x{x:02X}" for x in b[i:i + 16]) for i in range(0, len(b), 16))
    return f"""// GreenPAK SLG46824/6 programmer for "{name}", generated by cpldglue.
// Wiring: Arduino SDA/SCL to the GreenPAK's SDA (pin 9 STQFN / 12 TSSOP) and
// SCL (pin 8 / 13) with 4.7k pull-ups to the GreenPAK's VDD (2.5-5.5 V for
// programming), and GND to GND. Open the serial monitor at 115200 baud.
// Procedure: In-System Programming Guide ISPG-SLG46824/6 (Renesas).
#include <Wire.h>

const uint8_t CONTROL_CODE = 0x1;   // I2C control code (0001 unless changed)
const uint8_t PAGES = {PAGES};

const uint8_t DATA[PAGES * 16] PROGMEM = {{
  {arr(data)}
}};
// 1 = bit defined by this design; 0 = keep what the chip has (I2C address, ...)
const uint8_t MASK[PAGES * 16] PROGMEM = {{
  {arr(mask)}
}};
// 1 = bit changes at run time (ISPG Table 4): not compared
const uint8_t VOLATILE_BITS[PAGES * 16] PROGMEM = {{
  {arr(vol)}
}};

uint8_t image[PAGES * 16];

uint8_t addr(uint8_t block) {{ return (CONTROL_CODE << 3) | block; }}

bool readBlock(uint8_t block, uint8_t word, uint8_t *buf, uint8_t n) {{
  Wire.beginTransmission(addr(block));
  Wire.write(word);
  if (Wire.endTransmission(false) != 0) return false;
  uint8_t got = Wire.requestFrom(addr(block), n);
  for (uint8_t i = 0; i < got; i++) buf[i] = Wire.read();
  return got == n;
}}

void erasePage(uint8_t page) {{
  Wire.beginTransmission(addr(0));       // registers
  Wire.write(0xE3);                      // erase register (ERSR)
  Wire.write(0x80 | page);               // ERSE = 1, ERSEB4 = 0: configuration NVM
  Wire.endTransmission();                // the chip's ACK here may be non-compliant (errata)
  delay(25);
}}

bool writePage(uint8_t page) {{
  Wire.beginTransmission(addr(2));       // NVM configuration block
  Wire.write(page * 16);
  for (uint8_t i = 0; i < 16; i++) Wire.write(image[page * 16 + i]);
  uint8_t r = Wire.endTransmission();
  delay(25);
  return r == 0;
}}

void setup() {{
  Serial.begin(115200);
  while (!Serial) {{}}
  Wire.begin();
  Wire.setClock(100000);
  Serial.println(F("Reading the chip..."));
  uint8_t cur[16];
  for (uint8_t p = 0; p < PAGES; p++) {{
    if (!readBlock(2, p * 16, cur, 16)) {{
      Serial.println(F("No answer: check wiring, pull-ups, VDD and the control code."));
      return;
    }}
    for (uint8_t i = 0; i < 16; i++) {{
      uint8_t m = pgm_read_byte(&MASK[p * 16 + i]);
      image[p * 16 + i] = (cur[i] & ~m) | (pgm_read_byte(&DATA[p * 16 + i]) & m);
    }}
  }}
  Serial.println(F("Erasing and writing pages 0-13..."));
  for (uint8_t p = 0; p < PAGES; p++) {{
    erasePage(p);
    if (!writePage(p)) {{ Serial.print(F("Write failed on page ")); Serial.println(p); return; }}
  }}
  Serial.println(F("Verifying..."));
  for (uint8_t p = 0; p < PAGES; p++) {{
    readBlock(2, p * 16, cur, 16);
    for (uint8_t i = 0; i < 16; i++) {{
      uint8_t v = pgm_read_byte(&VOLATILE_BITS[p * 16 + i]);
      if ((cur[i] & ~v) != (image[p * 16 + i] & ~v)) {{
        Serial.print(F("Mismatch at byte 0x")); Serial.println(p * 16 + i, HEX);
        return;
      }}
    }}
  }}
  Serial.println(F("Done. Power-cycle the GreenPAK to load the new configuration."));
}}

void loop() {{}}
"""


# ---- reading it back: a simulator of the configured chip ------------------------------------
class GpModel:
    """Simulates the configured SLG46826 from its register bits: the matrix,
    the cells (LUT, DFF with nRST/nSET, latch) and the pins."""

    def __init__(self, bits: Sequence[int], data: dict):
        self.bits = list(bits)
        self.data = data
        self.mo = {int(k): v for k, v in data["matrix_outputs"].items()}
        self.state: Dict[str, int] = {}
        self.prev_clk: Dict[str, Optional[int]] = {}
        self.ext: Dict[str, Optional[int]] = {}   # IOx -> driven value
        self.vals: Dict[int, int] = {}            # matrix input -> value
        self.extra: Dict[int, int] = {}           # matrix inputs of blocks not modelled here
        rng = random.Random(3)
        for c in CELLS:
            self.state[c.name] = rng.getrandbits(1)

    def field(self, lo: int, hi: int) -> int:
        return sum(self.bits[b] << i for i, b in enumerate(range(lo, hi + 1)))

    def sel(self, output: int) -> int:
        lo, hi = self.mo[output]["bits"]
        n = self.field(lo, hi)
        return self.vals.get(n, 0)

    def is_dff(self, c: Cell) -> bool:
        return bool(c.dff) and self.bits[c.select] == 1

    def pin(self, c: Cell, role: str) -> Optional[int]:
        k = c.role(role)
        return None if k is None else self.sel(c.inputs[k])

    def held(self, c: Cell) -> Optional[int]:
        """The value an active nRST/nSET forces, else None."""
        top = c.truth[1]
        if c.dff in ("3", "3m") and self.pin(c, "rs") == 0:
            return 1 if self.bits[top - 2] else 0
        if c.dff == "4":
            if self.pin(c, "rst") == 0:
                return 0
            if self.pin(c, "set") == 0:
                return 1
        return None

    def _cell_out(self, c: Cell) -> int:
        if self.is_dff(c):
            top = c.truth[1]
            q = self.state[c.name]
            if self.bits[top] == 1:                      # latch: transparent while CLK is low
                if self.pin(c, "clk") == 0:
                    q = self.pin(c, "d")
                    self.state[c.name] = q
            h = self.held(c)
            if h is not None:
                q = h
                self.state[c.name] = q
            return q ^ self.bits[top - 1]
        idx = sum(self.sel(i) << k for k, i in enumerate(c.inputs))
        return self.bits[c.truth[0] + idx]

    def settle(self) -> None:
        pins = self.data["pins"]
        for _ in range(200):
            new = {GND: 0, VDD: 1}
            for io, p in pins.items():
                if p.get("matrix_in") is not None:
                    v = self.pin_value(io)
                    new[p["matrix_in"]] = 0 if v is None else v
            for c in CELLS:
                new[c.out] = self._cell_out(c)
            new.update(self.extra)
            if new == self.vals:
                return
            self.vals = new
        raise RuntimeError("GreenPAK model did not settle")

    def drives(self, io: str) -> bool:
        p = self.data["pins"][io]
        if p.get("oe_bit"):
            on = self.bits[p["oe_bit"][0]] == 1
        elif p.get("matrix_oe") is not None:
            on = self.sel(p["matrix_oe"]) == 1
        else:
            return False
        if on and self.field(*p["output_mode"]) >= 2:        # open-drain: only pulls low
            return self.sel(p["matrix_out"]) == 0
        return on

    def pin_value(self, io: str) -> Optional[int]:
        p = self.data["pins"][io]
        if self.drives(io) and p.get("matrix_out") is not None:
            return self.sel(p["matrix_out"])
        return self.ext.get(io)

    def step(self) -> None:
        self.settle()
        for _ in range(50):
            fire = []
            for c in CELLS:
                if not self.is_dff(c) or self.bits[c.truth[1]] == 1:
                    continue
                clk = self.pin(c, "clk")
                if self.prev_clk.get(c.name) == 0 and clk == 1:
                    if self.held(c) is None:
                        fire.append((c, self.pin(c, "d")))
                self.prev_clk[c.name] = clk
            if not fire:
                return
            for c, d in fire:
                self.state[c.name] = d
            self.settle()
        raise RuntimeError("GreenPAK clocks did not settle")

    def output(self, io: str) -> Optional[int]:
        return self.pin_value(io) if self.drives(io) else None


def verify(netlist_path: Path, top: str, bits: Sequence[int], data: dict,
           pins: Dict[str, str], vectors: int = 400, seed: int = 1) -> Tuple[bool, str]:
    """Simulate the bitstream and the design side by side. pins: port -> IOx."""
    from .sim import Sim
    sim = Sim.from_file(netlist_path, top)
    model = GpModel(bits, data)
    ins = [n for n, p in sim.ports.items() if p["direction"] == "input" and n in pins]
    outs = [n for n, p in sim.ports.items() if p["direction"] != "input" and n in pins]
    inouts = [n for n in outs if sim.ports[n]["direction"] == "inout"]
    tbuf_en = {y: e for _, e, y in sim.tbuf}
    rng = random.Random(seed)
    bad: List[str] = []
    checked = 0
    v = {i: 0 for i in ins}

    def drive(values: Dict[str, Optional[int]]) -> None:
        sim.set(**values)
        for k, val in values.items():
            model.ext[pins[k]] = val
        sim.step()
        model.step()

    def compare(when: str, external: set) -> None:
        nonlocal checked
        for o in outs:
            want = sim.get(o)
            if want is None or o in external:
                continue
            checked += 1
            have = model.output(pins[o])
            if have != want:
                bad.append(f"{o} = {have}, expected {want} ({when})")

    for k in range(vectors):
        # one input at a time: a latch enable and its data changing together
        # is a race in the chip too
        if ins:
            v[rng.choice(ins)] ^= 1
        drive({**v, **{i: None for i in inouts}})
        compare(f"step {k}", set())
        idle = {}
        for i in inouts:
            e = tbuf_en.get(sim.ports[i]["bits"][0])
            if e is None or sim._v(e) != 1:
                idle[i] = rng.getrandbits(1)
        if idle:
            drive(idle)
            compare(f"step {k}, inputs on {', '.join(idle)}", set(idle))
        if len(bad) > 5:
            break
    if bad:
        return False, f"WARNING: the bitstream differs from the design in {len(bad)} case(s), e.g. {bad[0]}"
    return True, (f"Bitstream matches the design ({len(outs)} outputs, {checked} values compared "
                  f"over {vectors} input changes).")


# ---- the whole flow ---------------------------------------------------------------------------
@dataclass
class GpBuild:
    ok: bool
    bits: List[int] = field(default_factory=list)
    owned: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    check: str = ""
    check_ok: bool = False
    placement: List[Tuple[str, str]] = field(default_factory=list)   # (cell, what)


def build(design, r, mapping, workdir: Path) -> GpBuild:
    """Bitstream for a GreenPAK design already mapped by greenpak.map_design.
    If its 4-input LUTs don't fit the one 4-input cell, the design is mapped
    again with 3-input LUTs (there are fourteen 3-input cells)."""
    from . import devices, greenpak, yosys
    from .generate import sanitize
    dev, pkg = devices.get_package(design.device, design.package)
    if dev.name not in SUPPORTED:
        return GpBuild(False, errors=[f"bitstreams are made for {', '.join(SUPPORTED)} only"])
    data = load_data()
    port_dirs = {p.name: p.direction for p in r.ports}
    pin_names = {s: pkg.pin_names[pin] for s, pin in r.pins.items()}
    open_drain = [p.name for p in r.ports if getattr(p, "drive", "") == "oc"]
    cfg = place(mapping, port_dirs, pin_names, open_drain)
    if cfg.errors and sum(1 for l in mapping.luts if len(l.inputs) == 4) > 1:
        remapped = greenpak.map_design(design, r, workdir / "lut3", lut=3)
        cfg3 = place(remapped, port_dirs, pin_names, open_drain)
        if not cfg3.errors or len(cfg3.errors) < len(cfg.errors):
            cfg, mapping = cfg3, remapped
            cfg.notes.append("mapped with 3-input LUTs to fit the cells")
    bits, owned = encode(cfg, data)
    out = GpBuild(not cfg.errors, bits, owned, list(cfg.errors), list(cfg.notes))
    out.placement = [(pl.cell.name, f"{pl.kind} {pl.out_net}") for pl in cfg.placed]
    if not out.ok:
        return out
    top = sanitize(design.name)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / f"{top}.v").write_text(r.verilog, encoding="utf-8")
    net = yosys.sim_netlist([workdir / f"{top}.v"], top, workdir / "gp_sim.json")
    out.check_ok, out.check = verify(net, top, bits, data, pin_names)
    out.ok = out.check_ok
    return out


def write_files(b: GpBuild, design, outdir: Path, top: str) -> List[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    files = {f"{top}.txt": txt_file(b.bits, b.owned),
             f"{top}_programmer.ino": arduino_sketch(b.bits, b.owned, design.name)}
    paths = []
    for name, text in files.items():
        (outdir / name).write_text(text, encoding="utf-8")
        paths.append(outdir / name)
    (outdir / f"{top}.bin").write_bytes(to_bytes(b.bits))
    (outdir / f"{top}_mask.bin").write_bytes(to_bytes(b.owned))
    return paths + [outdir / f"{top}.bin", outdir / f"{top}_mask.bin"]
