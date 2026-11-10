"""GreenPAK target: pin tables (from the Renesas datasheets), capability-
aware pin assignment, LUT/DFF fitting, the sheet's equations, and (with
Yosys) that the mapped LUT network behaves like the design."""
import itertools
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import design as dsg, devices, generate, greenpak, yosys   # noqa: E402
from cpldglue.sim import Sim                                              # noqa: E402

try:
    yosys.find_yosys()
    HAVE_YOSYS = True
except RuntimeError:
    HAVE_YOSYS = False

DECODER = """
design dec
device {dev} {pkg}
part U7 74x139
net A13 ext: U7.2
net A14 ext: U7.3
net M2 ext: U7.1
net WRAM_CE_n ext: U7.4
net PPU_CE_n ext: U7.5
net Y2 ext: U7.6
net ROMSEL_n ext: U7.7
"""


def buffers(dev="SLG46826", pkg="TSSOP20", n=4):
    """n 3-state buffers sharing one enable (a 74x368)."""
    lines = [f"device {dev} {pkg}", "part U8 74x368", "net G ext: U8.1"]
    for i, (a, y) in enumerate([(2, 3), (4, 5), (6, 7), (10, 9), (12, 11), (14, 13)][:n]):
        lines += [f"net A{i} ext: U8.{a}", f"net Y{i} ext: U8.{y}"]
    return dsg.parse_text("\n".join(lines))


class TestTables(unittest.TestCase):
    def test_every_pin_once(self):
        gp = [n for n, d in devices.DEVICES.items() if d.kind == "greenpak"]
        self.assertEqual(len(gp), 11)
        for name in gp:
            for pkg in devices.DEVICES[name].packages.values():
                with self.subTest(device=name, package=pkg.name):
                    groups = [set(pkg.io), set(pkg.inputs.values()), set(pkg.power),
                              set(pkg.reserved.values()), set(pkg.nc)]
                    self.assertEqual(sum(map(len, groups)), pkg.pin_count)
                    self.assertEqual(set().union(*groups), set(range(1, pkg.pin_count + 1)))
                    self.assertTrue(set(pkg.out_only) <= set(pkg.io))
                    self.assertTrue(set(pkg.no_oe) <= set(pkg.io))

    def test_new_parts_from_their_datasheets(self):
        D = devices.DEVICES
        # SLG46824 = SLG46826 pins; SLG46621 = SLG46620 with VDD2 on pin 14
        for p in ("STQFN20", "TSSOP20"):
            a, b = D["SLG46824"].packages[p], D["SLG46826"].packages[p]
            self.assertEqual((a.io, a.no_oe, a.out_only, a.reserved), (b.io, b.no_oe, b.out_only, b.reserved))
        p21 = D["SLG46621"].packages["STQFN20"]
        self.assertEqual(p21.power[14], "VCC")
        self.assertNotIn(14, p21.io)
        # small parts: which pins have an output enable
        self.assertEqual(sorted(set(D["SLG46108"].packages["STQFN8"].io) -
                                set(D["SLG46108"].packages["STQFN8"].no_oe)), [4, 8])
        self.assertEqual(sorted(set(D["SLG46110"].packages["STQFN12"].io) -
                                set(D["SLG46110"].packages["STQFN12"].no_oe)), [6, 10])
        self.assertEqual(D["SLG46110"].packages["STQFN12"].nc, [5, 11])
        self.assertEqual(sorted(set(D["SLG46140"].packages["STQFN14"].io) -
                                set(D["SLG46140"].packages["STQFN14"].no_oe)),
                         [3, 4, 5, 7, 9, 12, 13, 14])
        # SLG4653x: OE on 3, 5, 7, 10, 13, 14, 16, 18, 19; I2C pins input only
        for name in ("SLG46531", "SLG46533", "SLG46537"):
            p = D[name].packages["STQFN20"]
            self.assertEqual(sorted(set(p.io) - set(p.no_oe)), [3, 5, 7, 10, 13, 14, 16, 18, 19])
            self.assertEqual(sorted(p.inputs.values()), [2, 8, 9])
        self.assertEqual(D["SLG46538"].packages["STQFN20"].power[14], "VCC")
        # logic cells: e.g. the SLG46533's 3 + 12 DFF-capable cells
        self.assertEqual(D["SLG46533"].resources["lut2_dff"] + D["SLG46533"].resources["lut3_dff"], 15)
        self.assertEqual(sum(D["SLG46140"].resources.values()), 16)

    def test_slg46826_from_datasheet(self):
        d = devices.DEVICES["SLG46826"]
        self.assertEqual(sum(d.resources.values()), 19)       # 11 combination + 8 multi-function
        for pkg, scl, io6, vdd2 in (("STQFN20", 8, 10, 14), ("TSSOP20", 13, 11, 7)):
            p = d.packages[pkg]
            self.assertEqual(len(p.io), 15)
            self.assertEqual(p.reserved["SCL"], scl)
            self.assertEqual(p.pin_names[io6], "IO6")
            self.assertIn(io6, p.out_only)
            self.assertEqual(p.pin_names[vdd2], "VDD2")
            self.assertEqual(sorted(p.pin_names[n] for n in p.no_oe), ["IO0", "IO2", "IO3"])

    def test_slg46620_from_datasheet(self):
        d = devices.DEVICES["SLG46620"]
        self.assertEqual(d.resources, {"lut2": 8, "lut3": 16, "lut4": 2, "dff": 12, "inv": 2})
        p = d.packages["TSSOP20"]
        self.assertEqual(p.inputs, {"GPI": 2})
        self.assertEqual(sorted(p.no_oe), [4, 6, 8, 12, 15, 17, 20])
        self.assertEqual(p.power, {1: "VCC", 11: "GND"})


class TestPins(unittest.TestCase):
    def test_tristate_only_on_oe_pins(self):
        for dev, pkg in (("SLG46826", "TSSOP20"), ("SLG46826", "STQFN20"), ("SLG46620", "TSSOP20")):
            with self.subTest(device=dev, package=pkg):
                d = buffers(dev, pkg)
                r = generate.generate(d)
                self.assertEqual(r.errors, [])
                _, p = devices.get_package(dev, pkg)
                for i in range(4):
                    self.assertIn(r.pins[f"Y{i}"], p.oe_pins())
                for name, pin in r.pins.items():
                    if name.startswith(("A", "G")):
                        self.assertNotIn(pin, p.out_only)

    def test_plain_outputs_use_output_only_pins_first(self):
        r = generate.generate(dsg.parse_text(DECODER.format(dev="SLG46826", pkg="TSSOP20")))
        self.assertEqual(r.errors, [])
        _, p = devices.get_package("SLG46826", "TSSOP20")
        outs = {r.pins[n] for n in ("WRAM_CE_n", "PPU_CE_n", "Y2", "ROMSEL_n")}
        self.assertTrue(set(p.out_only) <= outs)

    def test_bad_locks_explained(self):
        d = buffers()
        _, p = devices.get_package("SLG46826", "TSSOP20")
        d.pin_locks = {"Y0": p.no_oe[0], "A0": p.out_only[0], "A1": p.reserved["SCL"]}
        msg = " ".join(generate.generate(d).errors)
        self.assertIn("has no output enable", msg)
        self.assertIn("is output-only", msg)
        self.assertIn("not a usable I/O pin", msg)

    def test_too_many_tristates(self):
        d = buffers("SLG46826", "TSSOP20", 6)          # 6 x 3-state + 6 inputs + enable = 13
        r = generate.generate(d)
        self.assertEqual(r.errors, [])                  # 10 OE pins: fits
        d2 = dsg.parse_text("device SLG46826 TSSOP20\n" + "\n".join(
            f"part U{k} 74x125\nnet E{k} ext: U{k}.1\nnet A{k} ext: U{k}.2\nnet Y{k} ext: U{k}.3"
            for k in range(11)))
        msg = " ".join(generate.generate(d2).errors)
        self.assertIn("need one of the 10 pins with an output enable", msg)

    def test_atf_assignment_unchanged(self):
        r = generate.generate(dsg.load(ROOT / "examples" / "tinytendo.cg"))
        self.assertEqual((r.pins["CPU_A13"], r.pins["M2"], r.pins["CPU_D0"], r.pins["WRAM_CE_n"]),
                         (1, 44, 19, 4))


class TestSheetLogic(unittest.TestCase):
    def test_equations_match_truth_tables(self):
        names = ["a", "b", "c", "d"]
        for w in range(1, 5):
            for truth in itertools.product((0, 1), repeat=1 << w):
                expr = greenpak.sop(names[:w], list(truth))
                py = expr.replace("~", " not ").replace("&", " and ").replace("|", " or ")
                for i in range(1 << w):
                    env = {names[k]: bool(i >> k & 1) for k in range(w)}
                    self.assertEqual(int(eval(py, {}, env)), truth[i], (w, truth, expr))
            if w == 3:
                break                                   # 4 inputs: spot-check below
        rng = random.Random(1)
        for _ in range(300):
            truth = [rng.getrandbits(1) for _ in range(16)]
            expr = greenpak.sop(names, truth)
            py = expr.replace("~", " not ").replace("&", " and ").replace("|", " or ")
            for i in range(16):
                env = {names[k]: bool(i >> k & 1) for k in range(4)}
                self.assertEqual(int(eval(py, {}, env)), truth[i], (truth, expr))

    def test_fit(self):
        dev = devices.DEVICES["SLG46826"]
        lut = lambda w: greenpak.Lut("x", ["i"] * w, [0] * (1 << w))
        ff = greenpak.Flop("DFF", "q", "d", "c")
        self.assertTrue(greenpak.fit(dev, [lut(3)] * 15, []).ok)       # 14 x 3-bit + the 4-bit
        self.assertFalse(greenpak.fit(dev, [lut(3)] * 16, []).ok)
        self.assertTrue(greenpak.fit(dev, [lut(2)] * 4 + [lut(3)] * 10, [ff] * 5).ok)   # 19 cells
        self.assertFalse(greenpak.fit(dev, [lut(2)] * 4 + [lut(3)] * 10, [ff] * 6).ok)
        both = greenpak.Flop("DFF", "q", "d", "c", reset="r", set="s")
        res = greenpak.fit(devices.DEVICES["SLG46620"], [], [both])
        self.assertFalse(res.ok)
        self.assertIn("async set and reset", res.unplaced[0])
        inv = greenpak.Lut("n", ["a"], [1, 0])
        self.assertEqual(greenpak.fit(devices.DEVICES["SLG46620"], [inv] * 2, []).used["inv"], 2)


@unittest.skipUnless(HAVE_YOSYS, "needs Yosys")
class TestMapping(unittest.TestCase):
    def evaluate(self, m, inputs):
        """Value of every net of the mapped LUT network for these inputs."""
        vals = dict(inputs, **{"0": 0, "1": 1})
        for _ in range(len(m.luts) + 1):
            for l in m.luts:
                if all(i in vals for i in l.inputs):
                    idx = sum(vals[i] << k for k, i in enumerate(l.inputs))
                    vals[l.out] = l.truth[idx]
        return vals

    def test_decoder_luts_behave_like_the_design(self):
        d = dsg.parse_text(DECODER.format(dev="SLG46826", pkg="TSSOP20"))
        r = generate.generate(d)
        tmp = Path(tempfile.mkdtemp(prefix="cg_gp_"))
        m = greenpak.map_design(d, r, tmp / "map")
        self.assertTrue(m.fit.ok)
        top = generate.sanitize(d.name)
        sim = Sim.from_file(yosys.sim_netlist([tmp / "map" / f"{top}.v"], top, tmp / "s.json"), top)
        for a13, a14, m2 in itertools.product((0, 1), repeat=3):
            sim.set(A13=a13, A14=a14, M2=m2)
            sim.step()
            vals = self.evaluate(m, {"A13": a13, "A14": a14, "M2": m2})
            for out in ("WRAM_CE_n", "PPU_CE_n", "Y2", "ROMSEL_n"):
                self.assertEqual(vals[out], sim.get(out), (out, a13, a14, m2))

    def test_tinytendo_glue_logic_and_output_enables(self):
        d = dsg.load(ROOT / "examples" / "tinytendo.cg")
        d.device, d.package = "SLG46620", "TSSOP20"
        d.pin_locks = {}
        r = generate.generate(d)
        self.assertIn("design needs 22 pins", " ".join(r.errors))   # too many pins
        r.errors = []                                               # map the logic anyway
        m = greenpak.map_design(d, r, Path(tempfile.mkdtemp(prefix="cg_gp_")))
        self.assertTrue(m.fit.ok)
        self.assertTrue(m.tbufs)                                    # the data bus is 3-state
        self.assertIn("<h2>LUTs", greenpak.sheet_html(d, r, m))

    def test_counter_flip_flops(self):
        d = dsg.parse_text("""
            design ffs
            device SLG46620 TSSOP20
            part U2 74x74
            part U3 74x161
            net CLK ext: U2.3 U3.2
            net D ext: U2.2
            net Q ext: U2.5
            net CLR ext: U2.1
            net VCC: U2.4 U3.1 U3.7 U3.10 U3.9
            net QA ext: U3.14
            net QB ext: U3.13
        """)
        m = greenpak.map_design(d, generate.generate(d), Path(tempfile.mkdtemp(prefix="cg_gp_")))
        self.assertEqual(len(m.flops), 3)
        self.assertEqual([f.reset for f in m.flops if f.q == "Q"], ["CLR"])
        self.assertEqual(m.fit.used["dff"], 3)


if __name__ == "__main__":
    unittest.main()
