"""Device and package tables for the whole ATF15xx family.

The tables are generated from Atmel's BSDL files. These tests check that
every package is fully described (each pin is I/O, a dedicated input,
power or NC exactly once), spot-check values against the BSDL files, and
pin down the 44-pin tables the project started with.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import design as dsg, devices, generate, yosys     # noqa: E402

SCH = ROOT.parent / "Hardware" / "Motherboard" / "TinyTendo-schematic.kicad_sch"

EXPECTED = {   # family -> (macrocells, {package: I/O pins incl. JTAG})
    "ATF1502": (32, {"PLCC44": 32, "TQFP44": 32}),
    "ATF1504": (64, {"PLCC44": 32, "TQFP44": 32, "PLCC68": 48, "PLCC84": 64,
                     "TQFP100": 64, "PQFP100": 64}),
    "ATF1508": (128, {"PLCC84": 64, "TQFP100": 80, "PQFP100": 80, "PQFP160": 96}),
}


class TestTables(unittest.TestCase):
    def test_family_and_variants(self):
        self.assertEqual(set(devices.DEVICES), {
            "ATF1502AS", "ATF1502ASL", "ATF1502ASV",
            "ATF1504AS", "ATF1504ASL", "ATF1504ASV", "ATF1504ASVL",
            "ATF1508AS", "ATF1508ASL", "ATF1508ASV", "ATF1508ASVL"})
        for name, dev in devices.DEVICES.items():
            with self.subTest(device=name):
                mc, pkgs = EXPECTED[dev.family]
                self.assertEqual(dev.macrocells, mc)
                self.assertEqual({p: len(k.io) for p, k in dev.packages.items()}, pkgs)
                self.assertEqual(dev.vcc, 3.3 if "ASV" in name else 5.0)

    def test_every_pin_accounted_for(self):
        for name, dev in devices.DEVICES.items():
            for pkg in dev.packages.values():
                with self.subTest(device=name, package=pkg.name):
                    total = int("".join(c for c in pkg.name if c.isdigit()))
                    self.assertEqual(pkg.pin_count, total)
                    groups = [set(pkg.io), set(pkg.inputs.values()), set(pkg.power),
                              set(pkg.nc)]
                    self.assertEqual(sum(len(g) for g in groups), total)
                    self.assertEqual(set().union(*groups), set(range(1, total + 1)))
                    self.assertTrue(set(pkg.jtag.values()) <= set(pkg.io))
                    self.assertEqual(set(pkg.inputs), {"GCLK1", "OE1", "GCLR", "GCLK2/OE2"})
                    self.assertEqual(sorted(pkg.power.values()), ["GND"] * (len(pkg.power) // 2)
                                     + ["VCC"] * (len(pkg.power) // 2))

    def test_44_pin_tables_unchanged(self):
        # The tables the tool shipped with (now confirmed by the BSDL files).
        p = devices.DEVICES["ATF1502AS"].packages["PLCC44"]
        self.assertEqual(p.io, [4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21,
                                24, 25, 26, 27, 28, 29, 31, 32, 33, 34, 36, 37, 38, 39, 40, 41])
        self.assertEqual(p.inputs, {"GCLR": 1, "GCLK2/OE2": 2, "GCLK1": 43, "OE1": 44})
        self.assertEqual(p.jtag, {"TDI": 7, "TMS": 13, "TCK": 32, "TDO": 38})
        self.assertEqual(p.power, {3: "VCC", 15: "VCC", 23: "VCC", 35: "VCC",
                                   10: "GND", 22: "GND", 30: "GND", 42: "GND"})
        t = devices.DEVICES["ATF1504AS"].packages["TQFP44"]
        self.assertEqual(t.inputs, {"GCLK1": 37, "OE1": 38, "GCLR": 39, "GCLK2/OE2": 40})
        self.assertEqual(t.jtag, {"TDI": 1, "TMS": 7, "TCK": 26, "TDO": 32})
        self.assertEqual(sorted(k for k, v in t.power.items() if v == "VCC"), [9, 17, 29, 41])

    def test_bsdl_spot_checks(self):
        p = devices.DEVICES["ATF1504AS"].packages["PLCC84"]      # 1504AS_J84.bsd
        self.assertEqual(p.jtag, {"TDI": 14, "TMS": 23, "TCK": 62, "TDO": 71})
        self.assertEqual(sorted(k for k, v in p.power.items() if v == "VCC"),
                         [3, 13, 26, 38, 43, 53, 66, 78])
        self.assertEqual(sorted(k for k, v in p.power.items() if v == "GND"),
                         [7, 19, 32, 42, 47, 59, 72, 82])
        self.assertEqual(p.inputs, {"GCLR": 1, "GCLK2/OE2": 2, "GCLK1": 83, "OE1": 84})
        q = devices.DEVICES["ATF1508AS"].packages["PQFP160"]     # 1508AS_Q160.bsd
        self.assertEqual(q.jtag, {"TDI": 9, "TMS": 22, "TCK": 99, "TDO": 112})
        self.assertEqual(len(q.nc), 44)
        self.assertEqual(q.inputs, {"GCLK1": 139, "OE1": 140, "GCLR": 141, "GCLK2/OE2": 142})

    def test_assign_fills_every_package(self):
        for name, dev in devices.DEVICES.items():
            for pkg in dev.packages.values():
                with self.subTest(device=name, package=pkg.name):
                    n = len(pkg.io) - 4 + 4      # I/O minus JTAG, plus input-only
                    sigs = [(f"I{i}", "input") for i in range(4)] + \
                           [(f"O{i}", "output") for i in range(n - 4)]
                    r = devices.assign_pins(name, pkg.name, sigs, {})
                    self.assertEqual(r.errors, [])
                    self.assertEqual(len(set(r.pins.values())), n)
                    self.assertFalse(set(r.pins.values()) & (set(pkg.power) | set(pkg.nc)))
                    r = devices.assign_pins(name, pkg.name, sigs + [("X", "output")], {})
                    self.assertTrue(r.errors)

    def test_nc_and_power_pins_cannot_be_locked(self):
        pkg = devices.DEVICES["ATF1508AS"].packages["PQFP160"]
        for pin in (pkg.nc[0], next(iter(pkg.power))):
            r = devices.assign_pins("ATF1508AS", "PQFP160", [("A", "output")], {"A": pin})
            self.assertIn("not a usable I/O pin", " ".join(r.errors))

    def test_fitter_tech_names(self):
        self.assertEqual(yosys.fitter_tech("ATF1504ASL"), "ATF1504AS")
        self.assertEqual(yosys.fitter_tech("ATF1508ASVL"), "ATF1508ASV")
        self.assertEqual(yosys.fitter_tech("atf1502asv"), "ATF1502ASV")


class TestGenerate(unittest.TestCase):
    def wide(self, device, package):
        lines = [f"device {device} {package}",
                 "part U1 74x541", "part U2 74x541", "part U3 74x541"]
        for u in (1, 2, 3):
            for k in range(1, 9):
                lines.append(f"net A{u}{k} ext: U{u}.{k + 1}")
                lines.append(f"net Y{u}{k} ext: U{u}.{19 - k}")
        return dsg.parse_text("\n".join(lines))

    def test_48_pins_fit_an_84_pin_part(self):
        d = self.wide("ATF1504AS", "PLCC84")
        r = generate.generate(d)
        self.assertEqual(r.errors, [])
        self.assertEqual(len(r.pins), 48)
        self.assertIn("Macrocells: about 24 of 64", r.report(d))

    def test_macrocell_warning_suggests_bigger_part(self):
        lines = ["device ATF1502AS PLCC44"]
        for u in range(1, 6):                         # 5 x 595 = 80 register bits
            lines.append(f"part U{u} 74x595")
            lines.append(f"net SER{u} ext: U{u}.14")
            lines.append(f"net Q{u} ext: U{u}.15")
        lines.append("net SRCLK ext: " + " ".join(f"U{u}.11" for u in range(1, 6)))
        lines.append("net RCLK ext: " + " ".join(f"U{u}.12" for u in range(1, 6)))
        lines.append("net VCC: " + " ".join(f"U{u}.10" for u in range(1, 6)))
        lines.append("net GND: " + " ".join(f"U{u}.13" for u in range(1, 6)))
        r = generate.generate(dsg.parse_text("\n".join(lines)))
        msg = " ".join(r.warnings)
        # 5 x (16 bits + 1 output pin); each QA pin holds its own bit
        self.assertIn("may not fit: about 80 macrocells", msg)
        self.assertIn("try ATF1508AS", msg)

    def test_3v3_note(self):
        d = self.wide("ATF1504ASV", "TQFP100")
        r = generate.generate(d)
        self.assertIn("runs from 3.3 V", " ".join(r.notes))
        self.assertNotIn("3.3 V", " ".join(generate.generate(
            self.wide("ATF1504AS", "TQFP100")).notes))

    @unittest.skipUnless(SCH.exists() and dsg.find_kicad_cli(), "needs KiCad + schematic")
    def test_full_tinytendo_merge_on_plcc84(self):
        d = dsg.from_kicad(SCH, ["U5", "U7", "U8", "U9"], name="tinytendo_full")
        d.device, d.package = "ATF1504AS", "PLCC84"
        r = generate.generate(d)
        self.assertEqual(r.errors, [])
        self.assertEqual(len(r.pins), 39)
        self.assertEqual(r.macrocells, (17, 8, 64))
        # the 373's latches drive their own pins, so they share those macrocells
        self.assertEqual(r.macrocell_estimate, 17)
        self.assertEqual(r.macrocell_parts["U5"], (8, 8, 8))
        self.assertAlmostEqual(sum(o + s - sh for o, s, sh in r.macrocell_parts.values()), 17)


if __name__ == "__main__":
    unittest.main()
