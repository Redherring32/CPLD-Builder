"""Check every chip model against an independent Python description of the
datasheet behaviour, using Yosys + cpldglue.sim.

    python -m unittest discover -s tests
"""
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpldglue import chips, yosys                       # noqa: E402
from cpldglue.sim import Sim                            # noqa: E402

_NETLIST = None


def netlist():
    global _NETLIST
    if _NETLIST is None:
        tmp = Path(tempfile.mkdtemp(prefix="cpldglue_"))
        _NETLIST = json.loads(yosys.library_netlist(tmp / "lib.json")
                              .read_text(encoding="utf-8"))
    return _NETLIST


def sim(key):
    return Sim(netlist(), chips.LIBRARY[key].module)


def nand(a, b): return 1 - (a & b)


# ---------------------------------------------------------------------------
# Combinational references: inputs dict -> expected outputs dict
# ---------------------------------------------------------------------------
def gate4(fn):
    return lambda i: {f"y{k}": fn(i[f"a{k}"], i[f"b{k}"]) for k in range(1, 5)}


def hexf(fn):
    return lambda i: {f"y{k}": fn(i[f"a{k}"]) for k in range(1, 7)}


def dec139(i):
    o = {}
    for h in (1, 2):
        sel = i[f"a{h}"] | (i[f"b{h}"] << 1)
        for k in range(4):
            o[f"y{h}_{k}"] = 1 if i[f"g{h}_n"] else int(k != sel)
    return o


def dec138(i):
    en = i["g1"] and not i["g2a_n"] and not i["g2b_n"]
    sel = i["a"] | i["b"] << 1 | i["c"] << 2
    return {f"y{k}": int(not en or k != sel) for k in range(8)}


def mux153(i):
    s = i["a"] | i["b"] << 1
    return {f"y{h}": int(not i[f"g{h}_n"] and i[f"c{h}_{s}"]) for h in (1, 2)}


def mux157(i):
    return {f"y{k}": int(not i["g_n"] and (i[f"b{k}"] if i["s"] else i[f"a{k}"]))
            for k in range(1, 5)}


def hex_tri(inv):
    def f(i):
        o = {}
        for k in range(1, 7):
            o[f"y{k}"] = i[f"a{k}"] ^ inv
            o[f"y{k}_oe"] = 1 - (i["g1_n"] if k <= 4 else i["g2_n"])
        return o
    return f


def quad_tri(active_low):
    def f(i):
        o = {}
        for k in range(1, 5):
            o[f"y{k}"] = i[f"a{k}"]
            o[f"y{k}_oe"] = (1 - i[f"oe{k}_n"]) if active_low else i[f"oe{k}"]
        return o
    return f


def oct244(inv):
    def f(i):
        o = {}
        for g in (1, 2):
            for k in range(1, 5):
                o[f"y{g}_{k}"] = i[f"a{g}_{k}"] ^ inv
                o[f"y{g}_{k}_oe"] = 1 - i[f"oe{g}_n"]
        return o
    return f


def oct541(inv):
    def f(i):
        en = int(not i["oe1_n"] and not i["oe2_n"])
        o = {}
        for k in range(1, 9):
            o[f"y{k}"] = i[f"a{k}"] ^ inv
            o[f"y{k}_oe"] = en
        return o
    return f


def t245(i):
    o = {}
    for k in range(1, 9):
        o[f"a{k}_o"] = i[f"b{k}_i"]
        o[f"b{k}_o"] = i[f"a{k}_i"]
        o[f"a{k}_oe"] = int(not i["oe_n"] and not i["dir"])
        o[f"b{k}_oe"] = int(not i["oe_n"] and i["dir"])
    return o


COMB = {
    "74x00": gate4(nand),
    "74x02": gate4(lambda a, b: 1 - (a | b)),
    "74x08": gate4(lambda a, b: a & b),
    "74x32": gate4(lambda a, b: a | b),
    "74x86": gate4(lambda a, b: a ^ b),
    "74x04": hexf(lambda a: 1 - a),
    "74x05": hexf(lambda a: 1 - a),
    "74x14": hexf(lambda a: 1 - a),
    "74x07": hexf(lambda a: a),
    "74x10": lambda i: {f"y{k}": 1 - (i[f"a{k}"] & i[f"b{k}"] & i[f"c{k}"]) for k in (1, 2, 3)},
    "74x11": lambda i: {f"y{k}": i[f"a{k}"] & i[f"b{k}"] & i[f"c{k}"] for k in (1, 2, 3)},
    "74x20": lambda i: {f"y{k}": 1 - (i[f"a{k}"] & i[f"b{k}"] & i[f"c{k}"] & i[f"d{k}"]) for k in (1, 2)},
    "74x125": quad_tri(True),
    "74x126": quad_tri(False),
    "74x138": dec138,
    "74x139": dec139,
    "74x153": mux153,
    "74x157": mux157,
    "74x240": oct244(1),
    "74x244": oct244(0),
    "74x245": t245,
    "74x367": hex_tri(0),
    "74x368": hex_tri(1),
    "74x540": oct541(1),
    "74x541": oct541(0),
    # more glue (function tables from the TI datasheets)
    "74x03": gate4(nand),
    "74x09": gate4(lambda a, b: a & b),
    "74x21": lambda i: {f"y{k}": i[f"a{k}"] & i[f"b{k}"] & i[f"c{k}"] & i[f"d{k}"] for k in (1, 2)},
    "74x27": lambda i: {f"y{k}": 1 - (i[f"a{k}"] | i[f"b{k}"] | i[f"c{k}"]) for k in (1, 2, 3)},
    "74x30": lambda i: {"y": 1 - int(all(i[c] for c in "abcdefgh"))},
    "74x151": lambda i: (lambda y: {"y": y, "w": 1 - y})(
        0 if i["g_n"] else i[f"d{i['a'] | i['b'] << 1 | i['c'] << 2}"]),
    "74x154": lambda i: {f"y{k}": int(i["g1_n"] or i["g2_n"] or
                                      k != (i["a"] | i["b"] << 1 | i["c"] << 2 | i["d"] << 3))
                         for k in range(16)},
    "74x257": lambda i: {**{f"y{k}": i[f"b{k}"] if i["s"] else i[f"a{k}"] for k in range(1, 5)},
                         **{f"y{k}_oe": 1 - i["oe_n"] for k in range(1, 5)}},
    "74x258": lambda i: {**{f"y{k}": 1 - (i[f"b{k}"] if i["s"] else i[f"a{k}"]) for k in range(1, 5)},
                         **{f"y{k}_oe": 1 - i["oe_n"] for k in range(1, 5)}},
    "74x688": lambda i: {"eq_n": int(i["g_n"] or any(i[f"p{k}"] != i[f"q{k}"] for k in range(8)))},
    "74x521": lambda i: {"eq_n": int(i["g_n"] or any(i[f"p{k}"] != i[f"q{k}"] for k in range(8)))},
    "4001": gate4(lambda a, b: 1 - (a | b)),
    "4011": gate4(nand),
    "4070": gate4(lambda a, b: a ^ b),
    "4071": gate4(lambda a, b: a | b),
    "4081": gate4(lambda a, b: a & b),
    "4049": hexf(lambda a: 1 - a),
    "4050": hexf(lambda a: a),
    "4069": hexf(lambda a: 1 - a),
    "74x2G00": lambda i: {f"y{k}": nand(i[f"a{k}"], i[f"b{k}"]) for k in (1, 2)},
    "74x2G02": lambda i: {f"y{k}": 1 - (i[f"a{k}"] | i[f"b{k}"]) for k in (1, 2)},
    "74x2G08": lambda i: {f"y{k}": i[f"a{k}"] & i[f"b{k}"] for k in (1, 2)},
    "74x2G32": lambda i: {f"y{k}": i[f"a{k}"] | i[f"b{k}"] for k in (1, 2)},
    "74x2G86": lambda i: {f"y{k}": i[f"a{k}"] ^ i[f"b{k}"] for k in (1, 2)},
    "74x2G04": lambda i: {f"y{k}": 1 - i[f"a{k}"] for k in (1, 2)},
    "74x2G14": lambda i: {f"y{k}": 1 - i[f"a{k}"] for k in (1, 2)},
    "74x2G06": lambda i: {f"y{k}": 1 - i[f"a{k}"] for k in (1, 2)},
    "74x2G34": lambda i: {f"y{k}": i[f"a{k}"] for k in (1, 2)},
    "74x2G17": lambda i: {f"y{k}": i[f"a{k}"] for k in (1, 2)},
    "74x2G07": lambda i: {f"y{k}": i[f"a{k}"] for k in (1, 2)},
    "74x2G125": lambda i: {**{f"y{k}": i[f"a{k}"] for k in (1, 2)},
                           **{f"y{k}_oe": 1 - i[f"oe{k}_n"] for k in (1, 2)}},
    "74x2G126": lambda i: {**{f"y{k}": i[f"a{k}"] for k in (1, 2)},
                           **{f"y{k}_oe": i[f"oe{k}"] for k in (1, 2)}},
    # single gates
    "74x1G00": lambda i: {"y": nand(i["a"], i["b"])},
    "74x1G02": lambda i: {"y": 1 - (i["a"] | i["b"])},
    "74x1G08": lambda i: {"y": i["a"] & i["b"]},
    "74x1G32": lambda i: {"y": i["a"] | i["b"]},
    "74x1G86": lambda i: {"y": i["a"] ^ i["b"]},
    "74x1G04": lambda i: {"y": 1 - i["a"]},
    "74x1G14": lambda i: {"y": 1 - i["a"]},
    "74x1G06": lambda i: {"y": 1 - i["a"]},
    "74x1G34": lambda i: {"y": i["a"]},
    "74x1G17": lambda i: {"y": i["a"]},
    "74x1G07": lambda i: {"y": i["a"]},
    "74x1G10": lambda i: {"y": 1 - (i["a"] & i["b"] & i["c"])},
    "74x1G11": lambda i: {"y": i["a"] & i["b"] & i["c"]},
    "74x1G27": lambda i: {"y": 1 - (i["a"] | i["b"] | i["c"])},
    "74x1G125": lambda i: {"y": i["a"], "y_oe": 1 - i["oe_n"]},
    "74x1G126": lambda i: {"y": i["a"], "y_oe": i["oe"]},
    "74x1G240": lambda i: {"y": 1 - i["a"], "y_oe": 1 - i["oe_n"]},
}


class TestPorts(unittest.TestCase):
    def test_every_part_matches_its_module(self):
        mods = netlist()["modules"]
        for key, part in chips.LIBRARY.items():
            with self.subTest(part=key):
                self.assertIn(part.module, mods)
                got = {n: p["direction"] for n, p in mods[part.module]["ports"].items()}
                self.assertEqual(got, dict(part.ports()))

    def test_storage_bits_match_models(self):
        # The macrocell estimate relies on these counts.
        mods = netlist()["modules"]
        for part in chips.LIBRARY.values():
            with self.subTest(part=part.key):
                cells = mods[part.module]["cells"].values()
                n = sum(1 for c in cells if "DFF" in c["type"] or "DLATCH" in c["type"])
                self.assertEqual(part.storage_bits, n)

    def test_units_cover_every_pin(self):
        from cpldglue.units import UNITS
        for key, part in chips.LIBRARY.items():
            with self.subTest(part=key):
                names = {p.name for p in part.pins.values() if not p.is_power}
                in_units = {n for u in UNITS[key] for n in u.pins}
                self.assertEqual(in_units, names)
                self.assertEqual(sum(u.storage for u in UNITS[key]), part.storage_bits)
                for u in UNITS[key]:
                    self.assertTrue(u.outputs and u.name)

    def test_lookup(self):
        for value, key in [("74HC368/40H368 (CII)", "74x368"), ("SN74LS00N", "74x00"),
                           ("74HCT245", "74x245"), ("CD4021BE", "4021"),
                           ("74HC139", "74x139"), ("HEF4021B", "4021"), ("139", "74x139"),
                           ("SN74LVC1G00DBVR", "74x1G00"), ("74AHC1GU04", "74x1G04"),
                           ("74HC1G125GW", "74x1G125"), ("NC7SZ32M5X", "74x1G32"),
                           ("NC7S04", "74x1G04"), ("74LVC1G79", "74x1G79"),
                           ("74x1G240", "74x1G240"), ("SN74LVC1G10DBVR", "74x1G10"),
                           ("74HC4040", "4040"), ("CD4017BE", "4017"), ("MC14013B", "4013"),
                           ("74LVC2G00", "74x2G00"), ("NC7WZ04", "74x2G04"),
                           ("SN74HC688N", "74x688"), ("74ALS521", "74x521"),
                           ("CD4049UBE", "4049"), ("74HC154", "74x154")]:
            self.assertEqual(chips.lookup(value).key, key, value)


class TestCombinational(unittest.TestCase):
    def test_all(self):
        rng = random.Random(1)
        for key, ref in COMB.items():
            part = chips.LIBRARY[key]
            ins = [n for n, d in part.ports() if d == "input"]
            outs = [n for n, d in part.ports() if d == "output"]
            s = sim(key)
            n = 2 ** len(ins) if len(ins) <= 10 else 400
            for v in range(n):
                bits = v if len(ins) <= 10 else rng.getrandbits(len(ins))
                inp = {name: (bits >> i) & 1 for i, name in enumerate(ins)}
                s.set(**inp)
                s.step()
                exp = ref(inp)
                got = {o: s.get(o) for o in outs}
                if got != exp:
                    self.fail(f"{key} inputs {inp}: got {got}, expected {exp}")


# ---------------------------------------------------------------------------
# Sequential parts: scripted checks
# ---------------------------------------------------------------------------
def bus(s, prefix, names):
    vals = [s.get(prefix + n) for n in names]
    if None in vals:
        return None
    return sum(v << i for i, v in enumerate(vals))


class TestSequential(unittest.TestCase):
    def clock(self, s, pin="clk"):
        s.set(**{pin: 0}); s.step()
        s.set(**{pin: 1}); s.step()

    def test_74x74(self):
        s = sim("74x74")
        s.set(clr1_n=0, pre1_n=1, d1=1, clk1=0, clr2_n=1, pre2_n=1, d2=0, clk2=0)
        s.step()
        self.assertEqual((s.get("q1"), s.get("q1_n")), (0, 1))
        s.set(clr1_n=1, pre1_n=0); s.step()
        self.assertEqual((s.get("q1"), s.get("q1_n")), (1, 0))
        s.set(clr1_n=0); s.step()                      # both low: Q = /Q = 1
        self.assertEqual((s.get("q1"), s.get("q1_n")), (1, 1))
        s.set(clr1_n=1, pre1_n=1, d1=0); s.step()
        self.clock(s, "clk1")
        self.assertEqual(s.get("q1"), 0)
        s.set(d1=1); s.step()
        self.clock(s, "clk1")
        self.assertEqual(s.get("q1"), 1)
        s.set(d1=0); s.step()                          # no edge: holds
        self.assertEqual(s.get("q1"), 1)

    def _counter(self, key, sync_clear):
        s = sim(key)
        q = lambda: bus(s, "q", "abcd")
        s.set(clr_n=1, clk=0, a=0, b=1, c=1, d=1, enp=1, ent=1, load_n=0); s.step()
        self.clock(s)
        self.assertEqual(q(), 14)
        s.set(load_n=1); s.step()
        self.clock(s)
        self.assertEqual((q(), s.get("rco")), (15, 1))
        s.set(ent=0); s.step()
        self.assertEqual(s.get("rco"), 0)
        self.clock(s)
        self.assertEqual(q(), 15)                      # ENT low: hold
        s.set(ent=1); s.step()
        self.clock(s)
        self.assertEqual(q(), 0)                       # wraps
        self.clock(s); self.clock(s)
        self.assertEqual(q(), 2)
        s.set(clr_n=0); s.step()
        self.assertEqual(q(), 2 if sync_clear else 0)
        self.clock(s)
        self.assertEqual(q(), 0)

    def test_74x161(self):
        self._counter("74x161", sync_clear=False)

    def test_74x163(self):
        self._counter("74x163", sync_clear=True)

    def test_74x164(self):
        s = sim("74x164")
        q = lambda: bus(s, "q", "abcdefgh")
        s.set(clk=0, clr_n=0, a=1, b=1); s.step()
        self.assertEqual(q(), 0)
        s.set(clr_n=1); s.step()
        for bit in (1, 0, 1, 1):
            s.set(a=bit, b=1); s.step()
            self.clock(s)
        self.assertEqual(q(), 0b1011)                  # qa = latest bit, qd = first
        s.set(a=1, b=0); s.step()                       # serial = A & B
        self.clock(s)
        self.assertEqual(q(), 0b10110)

    def test_74x165(self):
        s = sim("74x165")
        data = 0b10110010                               # bit0 = A ... bit7 = H
        pins = dict(zip("abcdefgh", [(data >> i) & 1 for i in range(8)]))
        s.set(clk=0, clk_inh=0, ser=0, sh_ld_n=0, **pins); s.step()
        self.assertEqual(s.get("qh"), 1)               # H appears at once (async)
        s.set(sh_ld_n=1); s.step()
        seen = [s.get("qh")]
        for _ in range(7):
            self.clock(s)
            seen.append(s.get("qh"))
        self.assertEqual(seen, [(data >> (7 - i)) & 1 for i in range(8)])
        self.assertEqual(s.get("qh_n"), 1 - seen[-1])
        s.set(clk_inh=1); s.step()                      # inhibit: no shift
        self.clock(s)
        self.assertEqual(s.get("qh"), seen[-1])

    def test_4021(self):
        s = sim("4021")
        data = 0b01101011                               # bit0 = P1 ... bit7 = P8
        pins = {f"p{i + 1}": (data >> i) & 1 for i in range(8)}
        s.set(clk=0, ser=1, ps=1, **pins); s.step()
        self.assertEqual((s.get("q8"), s.get("q7"), s.get("q6")),
                         ((data >> 7) & 1, (data >> 6) & 1, (data >> 5) & 1))
        self.clock(s)                                   # P/S high: clock ignored
        self.assertEqual(s.get("q8"), (data >> 7) & 1)
        s.set(ps=0); s.step()
        out = [s.get("q8")]
        for _ in range(8):
            self.clock(s)
            out.append(s.get("q8"))
        self.assertEqual(out, [(data >> (7 - i)) & 1 for i in range(8)] + [1])  # SER=1 fills

    def test_74x174_175_273(self):
        for key, n in (("74x174", 6), ("74x175", 4), ("74x273", 8)):
            s = sim(key)
            names = [str(i) for i in range(1, n + 1)]
            s.set(clr_n=0, clk=0, **{f"d{i}": 1 for i in names}); s.step()
            self.assertEqual(bus(s, "q", names), 0, key)
            s.set(clr_n=1); s.step()
            val = 0b101101 & ((1 << n) - 1)
            s.set(**{f"d{i}": (val >> k) & 1 for k, i in enumerate(names)}); s.step()
            self.clock(s)
            self.assertEqual(bus(s, "q", names), val, key)
            if key == "74x175":
                self.assertEqual(bus(s, "q", [f"{i}_n" for i in names]), val ^ 0xf)

    def test_74x377(self):
        s = sim("74x377")
        names = [str(i) for i in range(1, 9)]
        s.set(e_n=0, clk=0, **{f"d{i}": 1 for i in names}); s.step()
        self.clock(s)
        self.assertEqual(bus(s, "q", names), 0xff)
        s.set(e_n=1, **{f"d{i}": 0 for i in names}); s.step()
        self.clock(s)
        self.assertEqual(bus(s, "q", names), 0xff)     # disabled: holds

    def test_74x373_latch(self):
        for key in ("74x373", "74x573"):
            s = sim(key)
            names = [str(i) for i in range(1, 9)]
            put = lambda v: s.set(**{f"d{i}": (v >> k) & 1 for k, i in enumerate(names)})
            s.set(oe_n=0, le=1); put(0x5a); s.step()
            self.assertEqual(bus(s, "q", names), 0x5a)
            put(0xc3); s.step()
            self.assertEqual(bus(s, "q", names), 0xc3)  # transparent
            s.set(le=0); s.step()
            put(0x00); s.step()
            self.assertEqual(bus(s, "q", names), 0xc3)  # held
            self.assertEqual(s.get("q1_oe"), 1)
            s.set(oe_n=1); s.step()
            self.assertEqual(s.get("q1_oe"), 0)

    def test_74x374_ff(self):
        for key in ("74x374", "74x574"):
            s = sim(key)
            names = [str(i) for i in range(1, 9)]
            s.set(oe_n=0, clk=0, **{f"d{i}": (0x96 >> k) & 1 for k, i in enumerate(names)})
            s.step()
            self.clock(s)
            self.assertEqual(bus(s, "q", names), 0x96)
            s.set(**{f"d{i}": 0 for i in names}); s.step()
            self.assertEqual(bus(s, "q", names), 0x96)  # edge-triggered

    def test_74x259(self):
        s = sim("74x259")
        q = lambda: bus(s, "q", "01234567")
        def addr(n):
            s.set(s0=n & 1, s1=n >> 1 & 1, s2=n >> 2 & 1)
        s.set(d=0, g_n=1, clr_n=0); addr(0); s.step()
        self.assertEqual(q(), 0)                        # clear
        s.set(clr_n=1); s.step()
        for n, bit in ((2, 1), (5, 1), (7, 1), (5, 0)):  # addressable latch
            addr(n); s.set(d=bit); s.step()
            s.set(g_n=0); s.step()
            s.set(g_n=1); s.step()
        self.assertEqual(q(), 0b10000100)
        addr(3); s.set(d=1); s.step()
        self.assertEqual(q(), 0b10000100)               # /G high: hold
        s.set(clr_n=0, g_n=0); s.step()                  # demultiplexer
        self.assertEqual(q(), 0b00001000)
        s.set(d=0); s.step()
        self.assertEqual(q(), 0)

    def test_74x173(self):
        s = sim("74x173")
        q = lambda: bus(s, "q", "1234")
        s.set(clk=0, clr=1, m=0, n=0, g1_n=0, g2_n=0, d1=1, d2=0, d3=1, d4=1); s.step()
        self.assertEqual(q(), 0)
        s.set(clr=0); s.step()
        self.clock(s)
        self.assertEqual(q(), 0b1101)
        s.set(g1_n=1, d1=0); s.step()
        self.clock(s)
        self.assertEqual(q(), 0b1101)                   # data enable off: hold
        self.assertEqual(s.get("q1_oe"), 1)
        s.set(n=1); s.step()
        self.assertEqual(s.get("q1_oe"), 0)             # M or N high: Z

    def test_jk_flip_flops(self):
        # '109: J and /K; '112: J and K, falling edge
        for key, kname, edge in (("74x109", "k1_n", "rise"), ("74x112", "k1", "fall")):
            with self.subTest(key):
                s = sim(key)
                kv = (lambda k: 1 - k) if kname.endswith("_n") else (lambda k: k)
                idle = 0 if edge == "rise" else 1
                s.set(clk1=idle, clr1_n=0, pre1_n=1, j1=0, **{kname: kv(0)}); s.step()
                self.assertEqual((s.get("q1"), s.get("q1_n")), (0, 1))
                s.set(clr1_n=1); s.step()

                def tick():
                    s.set(clk1=1 - idle); s.step()
                    s.set(clk1=idle); s.step()
                for j, k, want in ((1, 0, 1), (0, 0, 1), (0, 1, 0), (1, 1, 1), (1, 1, 0)):
                    s.set(j1=j, **{kname: kv(k)}); s.step()
                    tick()
                    self.assertEqual(s.get("q1"), want, (j, k))
                s.set(pre1_n=0, clr1_n=0); s.step()
                self.assertEqual((s.get("q1"), s.get("q1_n")), (1, 1))

    def test_74x191(self):
        s = sim("74x191")
        q = lambda: bus(s, "q", "abcd")
        s.set(clk=0, cten_n=0, du=0, load_n=0, a=1, b=0, c=1, d=1); s.step()
        self.assertEqual(q(), 13)                       # async load
        s.set(load_n=1); s.step()
        seen = []
        for _ in range(3):
            self.clock(s); seen.append(q())
        self.assertEqual(seen, [14, 15, 0])
        self.clock(s); self.clock(s); self.clock(s); self.clock(s)
        self.assertEqual(q(), 4)
        s.set(du=1); s.step()
        self.clock(s)
        self.assertEqual(q(), 3)
        for _ in range(3):
            self.clock(s)
        s.set(clk=0); s.step()
        self.assertEqual((q(), s.get("maxmin"), s.get("rco_n")), (0, 1, 0))  # CLK low
        s.set(clk=1); s.step()
        self.assertEqual(s.get("rco_n"), 1)
        self.assertEqual(q(), 15)                       # that rising edge counted down
        s.set(clk=0, cten_n=1); s.step()
        self.clock(s)
        self.assertEqual(q(), 15)                       # /CTEN high: hold

    def test_74x193(self):
        s = sim("74x193")
        q = lambda: bus(s, "q", "abcd")
        s.set(up=1, down=1, clr=1, load_n=1, a=0, b=1, c=1, d=1); s.step()
        self.assertEqual(q(), 0)
        s.set(clr=0); s.step()

        def pulse(pin):
            s.set(**{pin: 0}); s.step()
            s.set(**{pin: 1}); s.step()
        pulse("up"); pulse("up"); pulse("up")
        self.assertEqual(q(), 3)
        pulse("down")
        self.assertEqual(q(), 2)
        s.set(load_n=0); s.step(); s.set(load_n=1); s.step()
        self.assertEqual(q(), 14)                       # async load
        pulse("up")
        self.assertEqual(q(), 15)
        s.set(up=0); s.step()
        self.assertEqual(s.get("co_n"), 0)              # carry while UP is low at 15
        s.set(up=1); s.step()
        self.assertEqual((q(), s.get("co_n")), (0, 1))
        s.set(down=0); s.step()
        self.assertEqual(s.get("bo_n"), 0)              # borrow while DOWN is low at 0
        s.set(down=1); s.step()
        self.assertEqual(q(), 15)

    def test_ripple_counters(self):
        s = sim("74x393")
        s.set(clk1=1, clr1=1, clk2=1, clr2=1); s.step()
        s.set(clr1=0); s.step()
        for _ in range(11):
            s.set(clk1=0); s.step(); s.set(clk1=1); s.step()    # falling edges count
        self.assertEqual(bus(s, "q", ["a1", "b1", "c1", "d1"]), 11)
        self.assertEqual(bus(s, "q", ["a2", "b2", "c2", "d2"]), 0)
        s = sim("4040")
        s.set(clk=1, rst=1); s.step(); s.set(rst=0); s.step()
        for _ in range(1000):
            s.set(clk=0); s.step(); s.set(clk=1); s.step()
        self.assertEqual(bus(s, "q", [str(i) for i in range(1, 13)]), 1000)
        s.set(rst=1); s.step()
        self.assertEqual(bus(s, "q", [str(i) for i in range(1, 13)]), 0)

    def test_4017(self):
        s = sim("4017")
        s.set(clk=0, inh=0, rst=1); s.step(); s.set(rst=0); s.step()
        for n in range(23):
            outs = [s.get(f"q{i}") for i in range(10)]
            self.assertEqual(outs, [int(i == n % 10) for i in range(10)], n)
            self.assertEqual(s.get("co"), int(n % 10 < 5))
            self.clock(s)
        s.set(inh=1); s.step()
        self.clock(s)
        self.assertEqual(s.get("q3"), 1)                # inhibited: no count

    def test_4013(self):
        s = sim("4013")
        s.set(clk1=0, d1=1, set1=0, rst1=1); s.step()
        self.assertEqual((s.get("q1"), s.get("q1_n")), (0, 1))
        s.set(rst1=0); s.step()
        self.clock(s, "clk1")
        self.assertEqual(s.get("q1"), 1)
        s.set(d1=0); s.step(); self.clock(s, "clk1")
        self.assertEqual(s.get("q1"), 0)
        s.set(set1=1); s.step()
        self.assertEqual(s.get("q1"), 1)                # async set (active high)
        s.set(rst1=1); s.step()
        self.assertEqual((s.get("q1"), s.get("q1_n")), (1, 1))

    def test_single_flip_flops(self):
        for key, out, inv in (("74x1G79", "q", 0), ("74x1G80", "q_n", 1)):
            with self.subTest(key):
                s = sim(key)
                s.set(clk=0, d=1); s.step()
                self.clock(s)
                self.assertEqual(s.get(out), 1 ^ inv)
                s.set(d=0); s.step()
                self.assertEqual(s.get(out), 1 ^ inv)      # holds until the next edge
                self.clock(s)
                self.assertEqual(s.get(out), 0 ^ inv)

    def test_single_gate_pinouts(self):
        # SOT-23-5/6 'DBV' pinouts from the TI SN74LVC1G datasheets
        def pins(key):
            return {int(n): (p.name, p.kind) for n, p in chips.LIBRARY[key].pins.items()}
        self.assertEqual(pins("74x1G00"), {1: ("a", "i"), 2: ("b", "i"), 3: ("GND", "gnd"),
                                           4: ("y", "o"), 5: ("VCC", "vcc")})
        self.assertEqual(pins("74x1G04")[2], ("a", "i"))
        self.assertEqual(pins("74x1G04")[1][1], "nc")
        self.assertEqual(pins("74x1G07")[4], ("y", "oc"))
        self.assertEqual(pins("74x1G125")[1], ("oe_n", "i"))
        self.assertEqual(pins("74x1G125")[4], ("y", "t"))
        self.assertEqual(pins("74x1G10"), {1: ("a", "i"), 2: ("GND", "gnd"), 3: ("b", "i"),
                                           4: ("y", "o"), 5: ("VCC", "vcc"), 6: ("c", "i")})
        self.assertEqual((pins("74x1G79")[1], pins("74x1G79")[2]), (("d", "i"), ("clk", "i")))

    # ---- more shift registers (behaviour from each datasheet's function table)
    def test_74x594(self):
        s = sim("74x594")
        q = lambda: bus(s, "q", "abcdefgh")
        s.set(ser=0, srclk=0, srclr_n=0, rclk=0, rclr_n=0); s.step()
        self.assertEqual(q(), 0)                       # both registers cleared
        s.set(srclr_n=1, rclr_n=1); s.step()
        for bit in (1, 0, 1, 1):
            s.set(ser=bit); s.step()
            self.clock(s, "srclk")
        self.assertEqual(q(), 0)                       # output register not loaded yet
        self.clock(s, "rclk")
        self.assertEqual(q(), 0b1011)                  # QA = latest bit
        s.set(srclr_n=0); s.step(); s.set(srclr_n=1); s.step()
        self.assertEqual(q(), 0b1011)                  # SRCLR leaves the outputs alone
        self.assertEqual(s.get("qh_s"), 0)
        s.set(rclr_n=0); s.step()
        self.assertEqual(q(), 0)                       # RCLR clears the outputs at once

    def test_74x166(self):
        s = sim("74x166")
        data = 0b10010111                              # bit0 = A ... bit7 = H
        pins = dict(zip("abcdefgh", [(data >> i) & 1 for i in range(8)]))
        s.set(clk=0, clk_inh=0, ser=1, clr_n=0, sh_ld_n=0, **pins); s.step()
        self.assertEqual(s.get("qh"), 0)               # async clear
        s.set(clr_n=1); s.step()
        self.assertEqual(s.get("qh"), 0)               # load is synchronous: no change yet
        self.clock(s)
        self.assertEqual(s.get("qh"), 1)               # H loaded on the clock edge
        s.set(sh_ld_n=1); s.step()
        seen = [s.get("qh")]
        for _ in range(8):
            self.clock(s)
            seen.append(s.get("qh"))
        self.assertEqual(seen, [(data >> (7 - i)) & 1 for i in range(8)] + [1])  # SER fills
        s.set(ser=0, clk_inh=1); s.step()
        self.clock(s)
        self.assertEqual(s.get("qh"), 1)               # inhibited: no shift

    def test_74x597(self):
        s = sim("74x597")
        first, second = 0b11001010, 0b00110101
        bits = lambda v: dict(zip("abcdefgh", [(v >> i) & 1 for i in range(8)]))
        s.set(ser=0, srclk=0, rclk=0, srload_n=1, srclr_n=1, **bits(first)); s.step()
        self.clock(s, "rclk")                          # FIRST into the input register
        s.set(**bits(second)); s.step()                # inputs change, not clocked in
        s.set(srload_n=0); s.step()
        self.assertEqual(s.get("qh"), (first >> 7) & 1)   # async load from the register
        s.set(srload_n=1); s.step()
        seen = [s.get("qh")]
        for _ in range(7):
            self.clock(s, "srclk")
            seen.append(s.get("qh"))
        self.assertEqual(seen, [(first >> (7 - i)) & 1 for i in range(8)])
        s.set(srclr_n=0); s.step()
        self.assertEqual(s.get("qh"), 0)               # SRCLR clears the shift register

    def test_74x194(self):
        s = sim("74x194")
        q = lambda: bus(s, "q", "abcd")
        s.set(clk=0, clr_n=0, s0=1, s1=1, sr_ser=0, sl_ser=1, a=1, b=1, c=0, d=1); s.step()
        self.assertEqual(q(), 0)                       # async clear
        s.set(clr_n=1); s.step()
        self.clock(s)
        self.assertEqual(q(), 0b1011)                  # S1 S0 = 11: parallel load
        s.set(s1=0, s0=1, sr_ser=0); s.step()
        self.clock(s)
        self.assertEqual(q(), 0b0110)                  # 01: shift right, QA <- SR SER
        s.set(s1=1, s0=0, sl_ser=1); s.step()
        self.clock(s)
        self.assertEqual(q(), 0b1011)                  # 10: shift left, QD <- SL SER
        s.set(s1=0, s0=0); s.step()
        self.clock(s)
        self.assertEqual(q(), 0b1011)                  # 00: hold

    def test_4094(self):
        s = sim("4094")
        q = lambda: bus(s, "q", "12345678")
        s.set(clk=0, data=0, strobe=1, oe=1); s.step()
        for _ in range(8):
            self.clock(s)                              # flush zeros through
        self.assertEqual(q(), 0)
        s.set(strobe=0); s.step()
        for bit in (1, 1, 0, 1):
            s.set(data=bit); s.step()
            self.clock(s)
        self.assertEqual(q(), 0)                       # STROBE low: outputs hold
        s.set(strobe=1); s.step()
        self.assertEqual(q(), 0b1101)                  # latches follow (Q1 = latest bit)
        self.assertEqual(s.get("q1_oe"), 1)
        s.set(oe=0); s.step()
        self.assertEqual(s.get("q8_oe"), 0)            # outputs released
        for _ in range(4):                             # first bit (1) reaches stage 8
            s.set(data=0); s.step()
            self.clock(s)
        self.assertEqual(s.get("qs"), 1)
        self.assertEqual(s.get("qs_d"), 0)             # Q'S waits for the falling edge
        s.set(clk=0); s.step()
        self.assertEqual(s.get("qs_d"), 1)

    def test_4015(self):
        s = sim("4015")
        qa = lambda: bus(s, "q", ["1_a", "2_a", "3_a", "4_a"])
        qb = lambda: bus(s, "q", ["1_b", "2_b", "3_b", "4_b"])
        s.set(clk_a=0, clk_b=0, rst_a=1, rst_b=1, data_a=1, data_b=0); s.step()
        self.assertEqual((qa(), qb()), (0, 0))
        s.set(rst_a=0, rst_b=0); s.step()
        self.clock(s, "clk_a")
        self.clock(s, "clk_a")
        self.assertEqual(qa(), 0b0011)                 # Q1 <- DATA, Q2 <- Q1
        self.assertEqual(qb(), 0)                      # B has its own clock
        s.set(data_b=1); s.step()
        self.clock(s, "clk_b")
        self.assertEqual(qb(), 0b0001)
        s.set(rst_a=1); s.step()
        self.assertEqual((qa(), qb()), (0, 0b0001))    # reset is per half

    def test_4014(self):
        s = sim("4014")
        data = 0b01101011                              # bit0 = P1 ... bit7 = P8
        pins = {f"p{i + 1}": (data >> i) & 1 for i in range(8)}
        s.set(clk=0, ser=1, ps=0, **{k: 0 for k in pins}); s.step()
        for _ in range(8):
            self.clock(s)                              # fill with SER = 1
        s.set(ps=1, **pins); s.step()
        self.assertEqual(s.get("q8"), 1)               # unlike the 4021: no async load
        self.clock(s)
        self.assertEqual((s.get("q8"), s.get("q7"), s.get("q6")),
                         ((data >> 7) & 1, (data >> 6) & 1, (data >> 5) & 1))
        s.set(ps=0); s.step()
        out = [s.get("q8")]
        for _ in range(7):
            self.clock(s)
            out.append(s.get("q8"))
        self.assertEqual(out, [(data >> (7 - i)) & 1 for i in range(8)])

    def test_74x595(self):
        s = sim("74x595")
        q = lambda: bus(s, "q", "abcdefgh")
        s.set(ser=0, srclk=0, srclr_n=0, rclk=0, oe_n=0); s.step()
        s.set(srclr_n=1); s.step()
        for bit in (1, 1, 0, 1):
            s.set(ser=bit); s.step()
            self.clock(s, "srclk")
        self.assertIsNone(q())                         # output register not loaded yet
        self.clock(s, "rclk")
        self.assertEqual(q(), 0b1101)                  # qa = latest bit
        self.assertEqual(s.get("qa_oe"), 1)
        for _ in range(4):
            s.set(ser=0); s.step()
            self.clock(s, "srclk")
        self.assertEqual(s.get("qh_s"), 1)             # first bit reached QH'


if __name__ == "__main__":
    unittest.main()
