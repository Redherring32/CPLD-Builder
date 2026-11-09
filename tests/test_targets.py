"""iCE40 and MAX 7000S targets: pin tables, the Quartus project, and (with
nextpnr-ice40 available) a real iCE40 build whose synthesised netlist is
simulated against the design."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cpldglue import deps, design as dsg, devices, generate, ice40, max7000, yosys  # noqa: E402
from cpldglue.gui import api                                                           # noqa: E402
from cpldglue.pintables import TABLES                                                  # noqa: E402
from cpldglue.sim import Sim                                                           # noqa: E402

try:
    yosys.find_yosys()
    HAVE_YOSYS = True
except RuntimeError:
    HAVE_YOSYS = False
HAVE_NEXTPNR = HAVE_YOSYS and ice40.tools_found() is not None

COUNTER = """design ctr
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
BIDIR = ("design b245\ndevice {dev} {pkg}\npart U1 74x245\nnet DIR ext: U1.1\nnet OE ext: U1.19\n"
         + "".join(f"net A{i} ext: U1.{a}\nnet B{i} ext: U1.{b}\n"
                   for i, (a, b) in enumerate([(2, 18), (3, 17), (4, 16)])))


class TestTables(unittest.TestCase):
    def test_ice40_every_pin_once(self):
        for name, pkg, io in (("ICE40HX1K", "TQ144", 96), ("ICE40HX4K", "TQ144", 107),
                              ("ICE40UP5K", "SG48", 39)):
            with self.subTest(name):
                dev = devices.DEVICES[name]
                p = dev.packages[pkg]
                self.assertEqual(dev.kind, "ice40")
                self.assertEqual(len(p.io), io)
                groups = [set(p.io), set(p.inputs.values()), set(p.power), set(p.nc),
                          set(p.reserved.values())]
                self.assertEqual(sum(map(len, groups)), p.pin_count)
                self.assertEqual(set().union(*groups), set(range(1, p.pin_count + 1)))
                self.assertIn("CDONE", p.reserved)
        up = devices.DEVICES["ICE40UP5K"].packages["SG48"]
        self.assertEqual(up.out_only, [39, 40, 41])            # RGB LED drivers

    def test_max7000s_shares_the_atf_pinouts(self):
        for name, fam in (("EPM7032S", "ATF1502"), ("EPM7064S", "ATF1504"), ("EPM7128S", "ATF1508")):
            dev = devices.DEVICES[name]
            self.assertEqual(dev.kind, "max7000")
            for pkg in dev.packages.values():
                t = TABLES[(fam, pkg.name)]
                with self.subTest(device=name, package=pkg.name):
                    self.assertEqual((pkg.io, pkg.inputs, pkg.jtag, pkg.power),
                                     (list(t["io"]), dict(t["inputs"]), dict(t["jtag"]),
                                      dict(t["power"])))
                    self.assertIn(pkg.name, max7000.PARTS[name])
        # Altera's 44-pin PLCC: dedicated inputs 1, 2, 43, 44; JTAG 7, 13, 32, 38
        p = devices.DEVICES["EPM7064S"].packages["PLCC44"]
        self.assertEqual(sorted(p.inputs.values()), [1, 2, 43, 44])
        self.assertEqual(sorted(p.jtag.values()), [7, 13, 32, 38])


class TestMax7000(unittest.TestCase):
    def test_quartus_project(self):
        d = dsg.parse_text(COUNTER.format(dev="EPM7064S", pkg="PLCC44"))
        r = generate.generate(d)
        self.assertTrue(r.ok, r.errors)
        qsf = max7000.qsf_text(d, "ctr", r.pins)
        self.assertIn('FAMILY "MAX7000S"', qsf)
        self.assertIn("DEVICE EPM7064SLC44-10", qsf)
        for sig, pin in r.pins.items():
            self.assertIn(f"set_location_assignment PIN_{pin} -to {sig}", qsf)
        self.assertTrue(set(r.pins.values()).isdisjoint({7, 13, 32, 38}))   # JTAG kept
        out = Path(tempfile.mkdtemp(prefix="maxtest_"))
        res = api.Builder(None, None).build(d, out)
        for ext in ("qpf", "qsf", "v"):
            self.assertTrue((out / f"ctr.{ext}").exists())
        if max7000.find_quartus() is None:
            self.assertFalse(res["ok"])
            self.assertIn("Quartus II 13.0 SP1 isn't installed", res["log"])

    def test_setup_lists_the_new_tools(self):
        ids = {d["id"] for d in deps.status()}
        self.assertTrue({"nextpnr", "quartus"} <= ids)


@unittest.skipUnless(HAVE_YOSYS, "needs Yosys")
class TestIce40Check(unittest.TestCase):
    def test_compare_catches_a_difference(self):
        d = dsg.parse_text(COUNTER.format(dev="iCE40HX1K", pkg="TQ144"))
        r = generate.generate(d)
        work = Path(tempfile.mkdtemp(prefix="icetest_"))
        (work / "a.v").write_text(r.verilog.replace("module ctr (", "module a ("))
        bad = r.verilog.replace("module ctr (", "module a (").replace(
            "assign rco = ", "assign rco = ~")
        if bad == r.verilog.replace("module ctr (", "module a ("):
            self.skipTest("RCO model changed")
        (work / "b.v").write_text(bad)
        ref = Sim.from_file(yosys.sim_netlist([work / "a.v"], "a", work / "a.json"), "a")
        same = Sim.from_file(yosys.sim_netlist([work / "a.v"], "a", work / "a2.json"), "a")
        dut = Sim.from_file(yosys.sim_netlist([work / "b.v"], "a", work / "b.json"), "a")
        self.assertTrue(ice40.compare(ref, same)[0])
        ref = Sim.from_file(work / "a.json", "a")
        self.assertFalse(ice40.compare(ref, dut)[0])


@unittest.skipUnless(HAVE_NEXTPNR, "needs nextpnr-ice40 (pip install yowasp-nextpnr-ice40)")
class TestIce40Build(unittest.TestCase):
    def build(self, text, dev, pkg):
        d = dsg.parse_text(text.format(dev=dev, pkg=pkg))
        out = Path(tempfile.mkdtemp(prefix="icebuild_"))
        res = api.Builder(None, None).build(d, out)
        return d, out, res

    def test_counter_hx1k(self):
        d, out, res = self.build(COUNTER, "iCE40HX1K", "TQ144")
        self.assertTrue(res["ok"], res["log"])
        self.assertTrue(res["check_ok"])
        self.assertGreater((out / "ctr.bin").stat().st_size, 30000)
        self.assertIn("Synthesised netlist matches the design", res["log"])
        pcf = (out / "ctr.pcf").read_text()
        r = generate.generate(d)
        for sig, pin in r.pins.items():
            self.assertIn(f"set_io {sig} {pin}", pcf)

    def test_bidirectional_up5k(self):
        d, out, res = self.build(BIDIR, "iCE40UP5K", "SG48")
        self.assertTrue(res["ok"], res["log"])
        self.assertNotIn(" 0 values", res["log"])
        r = generate.generate(d)
        self.assertTrue(set(r.pins.values()).isdisjoint({39, 40, 41}))   # RGB pins: outputs only


if __name__ == "__main__":
    unittest.main()
