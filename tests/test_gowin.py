"""Gowin target: pin tables, the pieces of the flow, and (with the Gowin tools
available) real builds whose synthesised netlist AND bitstream (read back with
gowin_unpack) are simulated against the design."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cpldglue import deps, design as dsg, devices, generate, gowin, yosys  # noqa: E402
from cpldglue.gowinpins import GOWIN_PINS                                  # noqa: E402
from cpldglue.gui import api                                               # noqa: E402

try:
    yosys.find_yosys()
    HAVE_YOSYS = True
except RuntimeError:
    HAVE_YOSYS = False
HAVE_GOWIN = HAVE_YOSYS and gowin.tools_found() is not None

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
DEC = ("design dec\ndevice {dev} {pkg}\npart U1 74x139\nnet G ext: U1.1\nnet A ext: U1.2\n"
       "net B ext: U1.3\nnet Y0 ext: U1.4\nnet Y1 ext: U1.5\nnet Y2 ext: U1.6\nnet Y3 ext: U1.7\n")
PARTS = [(d, p) for d, p in gowin.PARTS]


class TestTables(unittest.TestCase):
    def test_every_pin_once(self):
        for name, pkg in PARTS:
            with self.subTest(device=name, package=pkg):
                dev = devices.DEVICES[name]
                p = dev.packages[pkg]
                self.assertEqual(dev.kind, "gowin")
                groups = [set(p.io), set(p.inputs.values()), set(p.power), set(p.nc),
                          set(p.reserved.values())]
                self.assertEqual(sum(map(len, groups)), p.pin_count)
                self.assertEqual(set().union(*groups), set(range(1, p.pin_count + 1)))
                self.assertEqual(p.pin_count, sum(p.sides))

    def test_programming_pins_are_kept(self):
        for name, pkg in PARTS:
            p = devices.DEVICES[name].packages[pkg]
            fns = {f for n in p.io for f in p.pin_names[n].split("/")[1:]}
            with self.subTest(device=name, package=pkg):
                self.assertFalse(fns & set(devices.GOWIN_RESERVED))
                for jtag in ("TMS", "TCK", "TDI", "TDO"):
                    self.assertTrue(any(jtag in v.split("/") for v in p.reserved))
                for n in p.io:
                    self.assertRegex(p.pin_names[n], r"^IO[LRTB]\d+[A-Z]")

    def test_plain_pins_come_first(self):
        p = devices.DEVICES["GW1NR-9"].packages["QN88P"]
        dual = [bool(set(p.pin_names[n].split("/")[1:]) & devices.GOWIN_CONFIG_PINS)
                for n in p.io]
        self.assertEqual(dual, sorted(dual))
        self.assertIn(True, dual)

    def test_tables_cover_the_parts(self):
        keys = {f"{d}-{p}".replace("GW1NZ-1-FN32", "GW1NZ-1-QN32") for d, p in PARTS}
        self.assertEqual(keys, set(GOWIN_PINS))

    def test_known_pins(self):
        # Tang Nano 9K (GW1NR-9 QN88P): pin 52 is the 27 MHz clock input, IOR17A/GCLKT_3
        p = devices.DEVICES["GW1NR-9"].packages["QN88P"]
        self.assertEqual(p.pin_names[52], "IOR17A/GCLKT_3")
        self.assertIn(52, p.io)
        self.assertEqual(p.reserved["IOL11A/TMS"], 5)


class TestFlowPieces(unittest.TestCase):
    def test_cst(self):
        self.assertEqual(gowin.cst_text({"B": 12, "A": 3}), 'IO_LOC "A" 3;\nIO_LOC "B" 12;\n')

    def test_pad_port(self):
        self.assertEqual(gowin.pad_port("IOR7A/GCLKT_3", "GW1NZ-1"), ("R7C20", "A"))
        self.assertEqual(gowin.pad_port("IOT2B", "GW1N-9C"), ("R1C2", "B"))
        self.assertEqual(gowin.pad_port("IOB29A", "GW1N-9C"), ("R29C29", "A"))
        self.assertEqual(gowin.pad_port("IOL5A/JTAGSEL_N", "GW1N-4"), ("R5C1", "A"))

    def test_gpio_switches(self):
        d = dsg.parse_text(DEC.format(dev="GW1NR-9", pkg="QN88P"))
        self.assertEqual(gowin.gpio_switches(d, {"A": 3, "B": 55, "G": 59}),
                         ["--cpu_as_gpio", "--mspi_as_gpio", "--sspi_as_gpio"])
        self.assertEqual(gowin.gpio_switches(d, {"A": 3}), [])

    def test_part_numbers(self):
        for name, pkg in PARTS:
            dev, part, family = gowin.part_of(dsg.parse_text(DEC.format(dev=name, pkg=pkg)))
            self.assertIn(pkg.rstrip("P") if pkg != "QN88P" else pkg, part)
            self.assertIn(family, gowin.DIMS)

    def test_auto_pins_avoid_config_pins(self):
        d = dsg.parse_text(COUNTER.format(dev="GW1NZ-1", pkg="FN32"))
        r = generate.generate(d)
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(gowin.gpio_switches(d, r.pins), [])
        self.assertTrue(any("on-chip flash" in n for n in r.notes))

    def test_setup_lists_the_gowin_tools(self):
        self.assertIn("gowin", {d["id"] for d in deps.status()})
        self.assertIn("gowin", deps.FETCHERS)
        names = [w.filename for w in deps.GOWIN_WHEELS]
        self.assertTrue(any(n.startswith("apycula-0.32-") for n in names))


@unittest.skipUnless(HAVE_GOWIN, "needs the Gowin tools (cpldglue setup gowin)")
class TestGowinBuild(unittest.TestCase):
    def build(self, text, dev, pkg):
        d = dsg.parse_text(text.format(dev=dev, pkg=pkg))
        out = Path(tempfile.mkdtemp(prefix="gwbuild_"))
        res = api.Builder(None, None).build(d, out)
        return d, out, res

    def checked(self, res):
        self.assertTrue(res["ok"], res["log"])
        self.assertIn("Synthesised netlist matches the design", res["log"])
        self.assertIn("Bitstream (read back with gowin_unpack) matches the design", res["log"])
        self.assertNotIn(" 0 values", res["log"])

    def test_counter_gw1n4(self):
        d, out, res = self.build(COUNTER, "GW1N-4", "LQ144")
        self.checked(res)
        self.assertGreater((out / "ctr.fs").stat().st_size, 100000)
        cst = (out / "ctr.cst").read_text()
        for sig, pin in generate.generate(d).pins.items():
            self.assertIn(f'IO_LOC "{sig}" {pin};', cst)

    def test_bidirectional_tang_nano_9k(self):
        self.checked(self.build(BIDIR, "GW1NR-9", "QN88P")[2])

    def test_decoder_gw1nz1(self):
        self.checked(self.build(DEC, "GW1NZ-1", "FN32")[2])

    def test_preset_clear_and_latches(self):
        # one flip-flop with a clear, one with a preset (releasing both at once
        # is a race in a real 74x74, and in simulation)
        text = ("design ff\ndevice {dev} {pkg}\npart U1 74x74\npart U2 74x373\n"
                "net C1 ext: U1.1\nnet D1 ext: U1.2\nnet K1 ext: U1.3\nnet VCC: U1.4 U1.13\n"
                "net Q1 ext: U1.5\nnet Q1N ext: U1.6\n"
                "net P2 ext: U1.10\nnet K2 ext: U1.11\nnet D2 ext: U1.12\nnet Q2 ext: U1.9\n"
                "net OE ext: U2.1\nnet LE ext: U2.11\nnet LD1 ext: U2.3\nnet LQ1 ext: U2.2\n"
                "net LD2 ext: U2.4\nnet LQ2 ext: U2.5\n")
        d, out, res = self.build(text, "GW1N-9", "QN88")
        self.checked(res)

    def test_config_pins_as_io(self):
        # lock signals onto SSPI / CPU-port pins: gowin_pack needs its switches
        text = DEC.replace("design dec", "design dec\npin Y0 55\npin Y1 59")
        d, out, res = self.build(text, "GW1NR-9", "QN88P")
        self.checked(res)
        self.assertIn("--sspi_as_gpio", res["log"])

    def test_readback_catches_wrong_pins(self):
        d, out, res = self.build(DEC, "GW1N-9", "QN48")
        self.checked(res)
        pins = {s: int(p) for s, p in re.findall(r'IO_LOC "(\S+)" (\d+);',
                                                  (out / "dec.cst").read_text())}
        pins["Y0"], pins["Y1"] = pins["Y1"], pins["Y0"]
        ok, msg = gowin.check_bitstream(d, out, "dec", "GW1N-9C", pins=pins)
        self.assertFalse(ok, msg)
        self.assertIn("differs from the design", msg)


if __name__ == "__main__":
    unittest.main()
