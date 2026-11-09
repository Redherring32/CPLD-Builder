"""GAL target: BDD/ISOP, the JEDEC writer (against galette's own test
files), the fuse-map simulator, and fitting real designs."""
import itertools
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cpldglue import gal                      # noqa: E402
from cpldglue.bdd import Bdd                  # noqa: E402

GALETTE = ROOT / "tests" / "reference" / "galette"


# ---- a small reader for galette's .pld files (just what the test files use) ---------
def parse_pld(text: str) -> gal.Program:
    lines = [l.split(";")[0].rstrip() for l in text.splitlines()]
    lines = [l for l in lines if l.strip()]
    chip = gal.CHIPS[lines[0].strip()]
    sig = lines[1].strip()
    toks, k = [], 2
    while len(toks) < chip.pins:
        toks += lines[k].split()
        k += 1
    decl = {}
    for p, t in enumerate(toks, 1):
        neg = t.startswith("/")
        decl[t.lstrip("/")] = (p, neg)
    body = []
    for l in lines[k:]:
        if l.strip() == "DESCRIPTION":
            break
        body.append(l)
    tokens = re.findall(r"/?[A-Za-z0-9_]+(?:\.[A-Za-z]+)?|=|\+|\*", " ".join(body))
    eqns, i = [], 0
    while i < len(tokens):
        lhs = tokens[i]
        assert tokens[i + 1] == "=", tokens[i:i + 3]
        j = i + 2
        rhs = [tokens[j]]
        j += 1
        while j < len(tokens) and tokens[j] in "+*":
            rhs += [tokens[j], tokens[j + 1]]
            j += 2
        eqns.append((lhs, rhs))
        i = j

    def lit(t):
        neg = t.startswith("/")
        p, dneg = decl[t.lstrip("/")]
        return p, neg != dneg

    def sop(rhs):
        if rhs == ["VCC"]:
            return [[]]
        if rhs == ["GND"]:
            return []
        terms, cur = [], []
        for t in rhs:
            if t == "+":
                terms.append(cur)
                cur = []
            elif t != "*":
                cur.append(lit(t))
        return terms + [cur]

    prog = gal.Program(chip, signature=sig)
    kinds, feedback = {}, set()
    for lhs, rhs in eqns:
        for t in rhs:
            if t not in "+*" and t not in ("VCC", "GND"):
                p, _ = lit(t)
                if p in chip.olmc_pins:
                    feedback.add(p)
        name, _, suffix = lhs.lstrip("/").partition(".")
        if name in ("AR", "SP"):
            setattr(prog, name.lower(), sop(rhs)[0] if sop(rhs) else None)
            continue
        p, dneg = decl[name]
        c = prog.cell(p)
        if suffix == "E":
            c.oe = sop(rhs)[0] if sop(rhs) else None
            if not sop(rhs):
                c.oe_off = True
            continue
        c.kind = "reg" if suffix == "R" else "comb"
        kinds[p] = suffix or "C"
        c.active_high = not (lhs.startswith("/") != dneg)
        c.terms = sop(rhs)
    for p in feedback:
        if p not in kinds:
            prog.cell(p).kind = "input"
    if chip.is_v8:                      # galette's mode choice
        if "R" in kinds.values():
            prog.mode = "registered"
        elif "T" in kinds.values():
            prog.mode = "complex"
        elif any(p in kinds for p in feedback) or \
                any(p not in kinds and chip.olmc(p) in (3, 4) for p in feedback):
            prog.mode = "complex"
        else:
            prog.mode = "simple"
    return prog


class TestBdd(unittest.TestCase):
    def test_isop_covers_exactly(self):
        rng = random.Random(3)
        for _ in range(40):
            b = Bdd()
            vs = [b.var(f"x{i}") for i in range(5)]
            truth = [rng.getrandbits(1) for _ in range(32)]
            f = 0
            for m, t in enumerate(truth):
                if t:
                    f = b.or_(f, b.cube({i: (m >> i) & 1 for i in range(5)}))
            cubes = b.isop(f)
            for m in range(32):
                val = {i: (m >> i) & 1 for i in range(5)}
                got = int(any(all(val[v] == x for v, x in c.items()) for c in cubes))
                self.assertEqual(got, truth[m])
            # irredundant: dropping any cube loses a minterm
            for k in range(len(cubes)):
                rest = cubes[:k] + cubes[k + 1:]
                g = 0
                for c in rest:
                    g = b.or_(g, b.cube(c))
                self.assertNotEqual(g, f)

    def test_dont_cares_shrink_the_cover(self):
        b = Bdd()
        a, c, e = b.var("a"), b.var("c"), b.var("e")
        f = b.or_(b.and_(a, c), b.and_(b.not_(a), b.not_(c)))   # xnor
        self.assertEqual(len(b.isop(f)), 2)
        # if we only care when a = 1, it's just c
        self.assertEqual(b.isop(b.and_(f, a), b.or_(f, b.not_(a))), [{1: 1}])


class TestJedec(unittest.TestCase):
    def test_matches_galette_bit_for_bit(self):
        files = sorted(GALETTE.glob("*.pld"))
        self.assertGreaterEqual(len(files), 11)
        for pld in files:
            with self.subTest(pld.name):
                prog = parse_pld(pld.read_text())
                fuses = gal.build_fuses(prog, galette_unused=True)
                want_text = pld.with_suffix(".jed").read_text()
                qf, want = gal.read_jedec(want_text)
                self.assertEqual(qf, prog.chip.total)
                got = fuses.bits()
                diff = [i for i, (x, y) in enumerate(zip(got, want)) if x != y]
                self.assertEqual(diff, [], f"{pld.name}: first differing fuse {diff[:5]}")
                mine = gal.jedec_text(fuses)
                self.assertEqual(re.search(r"\*C([0-9a-f]{4})", mine).group(1),
                                 re.search(r"\*C([0-9a-f]{4})", want_text).group(1))
                self.assertEqual(gal.read_jedec(mine)[1], want)

    def test_model_follows_galette_semantics(self):
        """The fuse-map simulator, run on galette's files, does what the
        equations say (pin-level: a registered pin shows its equation after
        the clock; AR clears the register)."""
        for name in ("GAL16V8_combinatorial", "GAL16V8_reg", "GAL22V10_reg",
                     "GAL22V10_invertedreg", "GAL22V10_tri"):
            with self.subTest(name):
                prog = parse_pld((GALETTE / f"{name}.pld").read_text())
                chip = prog.chip
                model = gal.GalModel(chip, gal.build_fuses(prog, galette_unused=True).bits())
                registered = any(c.kind == "reg" for c in prog.olmcs.values())
                fixed = {1} | ({11} if chip.is_v8 and registered else set())
                inputs = [p for p in range(1, chip.pins) if p != chip.gnd and p not in fixed
                          and (p not in prog.olmcs or prog.olmcs[p].kind == "input")]
                rng = random.Random(5)

                def value(term, pins):
                    return int(all(pins[p] != neg for p, neg in term))

                def sop(terms, pins):
                    return int(any(value(t, pins) for t in terms))

                for _ in range(60):
                    ext = {p: rng.getrandbits(1) for p in inputs}
                    ext[1] = 0
                    if 11 in fixed:
                        ext[11] = 0
                    model.set(ext)
                    model.step()
                    pins = {**ext, **{p: model.pins.get(p) for p in prog.olmcs}}
                    want = {}
                    for p, c in prog.olmcs.items():
                        if c.kind == "reg":
                            want[p] = sop(c.terms, pins) if c.active_high else 1 - sop(c.terms, pins)
                    model.set({1: 1})
                    model.step()
                    for p, w in want.items():
                        self.assertEqual(model.get(p), w, f"registered pin {p}")
                    for p, c in prog.olmcs.items():
                        if c.kind == "comb" and (c.oe is None or value(c.oe, model.pins)):
                            s = sop(c.terms, {**ext, **model.pins})
                            self.assertEqual(model.get(p), s if c.active_high else 1 - s,
                                             f"combinational pin {p}")


# ---- whole designs (need Yosys) -------------------------------------------------------
from cpldglue import design as dsg, devices, generate, yosys   # noqa: E402

try:
    yosys.find_yosys()
    HAVE_YOSYS = True
except RuntimeError:
    HAVE_YOSYS = False

CTR161 = """design ctr
device {dev} {pkg}
part U1 74x161
net CLR ext: U1.1
net CLK ext: U1.2
net A ext: U1.3
net B ext: U1.4
net C ext: U1.5
net D ext: U1.6
net ENP ext: U1.7
net LD ext: U1.9
net ENT ext: U1.10
net QD ext: U1.11
net QC ext: U1.12
net QB ext: U1.13
net QA ext: U1.14
net RCO ext: U1.15
"""
DEC139 = """design dec
device GAL16V8 DIP20
part U7 74x139
net A13 ext: U7.2
net A14 ext: U7.3
net M2 ext: U7.1
net WRAM ext: U7.4
net PPU ext: U7.5
net Y2 ext: U7.6
net ROMSEL ext: U7.7
"""


def reg374(dev="GAL16V8 DIP20"):
    return (f"design r374\ndevice {dev}\npart U1 74x374\nnet OE ext: U1.1\nnet CLK ext: U1.11\n"
            + "".join(f"net D{i} ext: U1.{d}\nnet Q{i} ext: U1.{q}\n" for i, (d, q) in
                      enumerate([(3, 2), (4, 5), (7, 6), (8, 9), (13, 12), (14, 15), (17, 16),
                                 (18, 19)])))


def bidir245():
    return ("design b245\ndevice GAL22V10 DIP24\npart U1 74x245\nnet DIR ext: U1.1\n"
            "net OE ext: U1.19\n" + "".join(f"net A{i} ext: U1.{a}\nnet B{i} ext: U1.{b}\n"
                                            for i, (a, b) in enumerate([(2, 18), (3, 17), (4, 16)])))


def latch573():
    return ("design l573\ndevice GAL22V10 DIP24\npart U1 74x573\nnet OE const=0: U1.1\n"
            "net LE ext: U1.11\n" + "".join(f"net D{i} ext: U1.{d}\nnet Q{i} ext: U1.{q}\n"
                                            for i, (d, q) in enumerate([(2, 19), (3, 18)])))


def build(text):
    d = dsg.parse_text(text)
    r = generate.generate(d)
    assert r.ok, r.errors
    return d, gal.build(d, r, Path(tempfile.mkdtemp(prefix="galtest_")))


class TestTables(unittest.TestCase):
    def test_packages(self):
        for name, dip in (("GAL16V8", 20), ("GAL22V10", 24)):
            dev = devices.DEVICES[name]
            self.assertEqual(dev.kind, "gal")
            for pkg in dev.packages.values():
                with self.subTest(device=name, package=pkg.name):
                    groups = [set(pkg.io), set(pkg.inputs.values()), set(pkg.power), set(pkg.nc)]
                    self.assertEqual(sum(map(len, groups)), pkg.pin_count)
                    self.assertEqual(set().union(*groups), set(range(1, pkg.pin_count + 1)))
                    self.assertEqual(len(pkg.io), dev.macrocells)
                    for p in range(1, dip + 1):
                        self.assertEqual(devices.gal_dip_pin(
                            pkg.name, devices.gal_package_pin(pkg.name, p)), p)
        plcc = devices.DEVICES["GAL22V10"].packages["PLCC28"]
        self.assertEqual((plcc.power, plcc.nc), ({14: "GND", 28: "VCC"}, [1, 8, 15, 22]))
        self.assertEqual(devices.gal_package_pin("PLCC28", 13), 16)


@unittest.skipUnless(HAVE_YOSYS, "needs Yosys")
class TestFit(unittest.TestCase):
    def check(self, text, mode, cells):
        d, b = build(text)
        self.assertTrue(b.fit.ok, b.fit.errors)
        self.assertTrue(b.check_ok, b.check)
        self.assertEqual(b.fit.mode, mode)
        used = sum(1 for c in b.fit.cells if c["kind"] in ("reg", "comb"))
        self.assertEqual(used, cells)
        return d, b

    def test_decoder_simple_mode(self):
        self.check(DEC139, "simple", 4)

    def test_counter_22v10_uses_ar_for_async_clear(self):
        d, b = self.check(CTR161.format(dev="GAL22V10", pkg="DIP24"), "", 5)
        self.assertEqual(b.pins["CLK"], 1)
        self.assertIn("AR = /CLR", b.pld)
        self.assertIn("with clock pulses", b.check)

    def test_counter_plcc28_pins(self):
        d, b = self.check(CTR161.format(dev="GAL22V10", pkg="PLCC28"), "", 5)
        self.assertEqual(b.pins["CLK"], 2)
        self.assertTrue(set(b.pins.values()) <= set(range(2, 28)) - {8, 14, 15, 22})

    def test_counter_16v8_has_no_async_reset(self):
        d, b = build(CTR161.format(dev="GAL16V8", pkg="DIP20"))
        self.assertFalse(b.fit.ok)
        self.assertIn("GAL16V8 has none", " ".join(b.fit.errors))

    def test_374_is_a_16r8(self):
        d, b = self.check(reg374(), "registered", 8)
        self.assertEqual((b.pins["CLK"], b.pins["OE"]), (1, 11))

    def test_bidirectional(self):
        d, b = self.check(bidir245(), "", 6)
        self.assertNotIn(" 0 values", b.check)

    def test_latch_from_feedback(self):
        d, b = self.check(latch573(), "", 2)
        # hold term (Q while LE is low) and the consensus term keep it glitch-free
        self.assertTrue(all(c["terms"] == 3 for c in b.fit.cells if c["kind"] == "comb"))

    def test_locks_are_honoured_and_checked(self):
        text = DEC139.replace("design dec", "design dec\npin Y2 19\npin A13 9")
        d, b = build(text)
        self.assertTrue(b.fit.ok, b.fit.errors)
        self.assertEqual((b.pins["Y2"], b.pins["A13"]), (19, 9))
        d, b = build(CTR161.format(dev="GAL22V10", pkg="DIP24")
                     .replace("design ctr", "design ctr\npin CLK 5"))
        self.assertFalse(b.fit.ok)
        self.assertIn("must be on pin 1", " ".join(b.fit.errors))

    def test_two_clocks_rejected(self):
        text = ("design s595\ndevice GAL22V10 DIP24\npart U1 74x595\nnet OE ext: U1.13\n"
                "net SRCLK ext: U1.11\nnet RCLK ext: U1.12\nnet SRCLR const=1: U1.10\n"
                "net SER ext: U1.14\nnet QA ext: U1.15\n")
        d, b = build(text)
        self.assertFalse(b.fit.ok)
        self.assertIn("two clocks", " ".join(b.fit.errors))

    def test_check_catches_a_wrong_fuse(self):
        d, b = build(CTR161.format(dev="GAL22V10", pkg="DIP24"))
        prog = b.fit.program
        fuses = gal.build_fuses(prog)
        work = Path(tempfile.mkdtemp(prefix="galtest_"))
        r = generate.generate(d)
        (work / "ctr.v").write_text(r.verilog, encoding="utf-8")
        net = yosys.sim_netlist([work / "ctr.v"], "ctr", work / "n.json")
        self.assertTrue(gal.verify(net, "ctr", fuses, b.fit.pins)[0])
        # connect one more input to a product term of QA
        qa = b.fit.pins["QA"]
        i = gal.CHIPS["GAL22V10"].olmc(qa)
        row = gal.CHIPS["GAL22V10"].row_start[i] + 1
        k = row * 44 + gal._C22[b.fit.pins["A"]]
        bad = gal.Fuses(**{**fuses.__dict__, "array": list(fuses.array)})
        bad.array[k] = 0 if bad.array[k] else 1
        ok, msg = gal.verify(net, "ctr", bad, b.fit.pins)
        self.assertFalse(ok, msg)

    def test_pld_assembles_to_the_same_fuses(self):
        for text in (DEC139, reg374(), CTR161.format(dev="GAL22V10", pkg="DIP24"), latch573()):
            d, b = build(text)
            with self.subTest(d.name):
                prog = parse_pld(b.pld)
                for p, c in b.fit.program.olmcs.items():       # idle inputs on OLMC pins
                    if c.kind == "input":
                        prog.cell(p).kind = "input"
                self.assertEqual(gal.build_fuses(prog).bits(), gal.read_jedec(b.jedec)[1])

    def test_cli_and_build_button(self):
        from cpldglue import cli
        from cpldglue.gui import api
        out = Path(tempfile.mkdtemp(prefix="galtest_"))
        proj = out / "ctr.cg"
        proj.write_text(CTR161.format(dev="GAL22V10", pkg="DIP24"))
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["build", str(proj), "-o", str(out / "cli")]), 0)
        jed = (out / "cli" / "ctr.jed").read_bytes()
        self.assertTrue(jed.startswith(b"\x02") and b"*QF5892" in jed and b"\r" not in jed)
        # JEDEC file checksum: the sum of the bytes from STX to ETX
        body, tail = jed.split(b"\x03")
        self.assertEqual(int(tail.strip(), 16), (sum(body) + 3) & 0xFFFF)
        self.assertIn("CLK              : 1", (out / "cli" / "ctr.pin").read_text())
        res = api.Builder(None, None).build(dsg.parse_text(proj.read_text()), out / "gui")
        self.assertTrue(res["ok"], res["log"])
        self.assertTrue((out / "gui" / "ctr.jed").exists())


if __name__ == "__main__":
    unittest.main()
