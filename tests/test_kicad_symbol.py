"""KiCad symbol export: pin roles, grid alignment, and (with KiCad
installed) a round trip through kicad-cli to check every pin lands on the
net its label names."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import design as dsg, devices, generate, kicad_symbol as ks   # noqa: E402

EXAMPLE = ROOT / "examples" / "tinytendo.cg"


def small(device="ATF1502AS", package="PLCC44"):
    """One inverter: two pins used, so most pins are spare."""
    return dsg.parse_text(f"""
        design inv
        device {device} {package}
        part U1 74x04
        net "/IN-A" ext: U1.1
        net "/OUT-~{{Y}}" ext: U1.2
        net GND: U1.3
    """)


class TestSymbol(unittest.TestCase):
    def test_label_text(self):
        self.assertEqual(ks.label_text("/CPU-A13"), "CPU-A13")
        self.assertEqual(ks.label_text("/Sheet/PPU-~{CE}"), "PPU-~{CE}")
        self.assertEqual(ks.label_text("M2"), "M2")

    def test_every_pin_once_and_on_grid(self):
        for dev, pkg in (("ATF1502AS", "PLCC44"), ("ATF1504AS", "TQFP100"),
                         ("ATF1508ASV", "PQFP160")):
            with self.subTest(device=dev, package=pkg):
                e = ks.build(small(dev, pkg))
                nums = [int(n) for n in re.findall(r'\(number "(\d+)"', e.library)]
                total = devices.DEVICES[dev].packages[pkg].pin_count
                self.assertEqual(sorted(nums), list(range(1, total + 1)))
                for x, y in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", e.clipboard):
                    self.assertAlmostEqual(float(x) / 1.27, round(float(x) / 1.27), places=6)
                    self.assertAlmostEqual(float(y) / 1.27, round(float(y) / 1.27), places=6)

    def test_pin_roles(self):
        e = ks.build(small())
        clip = e.clipboard
        self.assertIn('(label "IN-A"', clip)
        self.assertIn('(label "OUT-~{Y}"', clip)
        for fn in ("TDI", "TMS", "TCK", "TDO"):                 # JTAG header nets
            self.assertIn(f'(label "{fn}"', clip)
        # IN-A takes one dedicated input; the other three are tied to GND
        self.assertEqual(clip.count('(label "GND"'), 4 + 3)
        self.assertEqual(clip.count('(label "VCC"'), 4)
        spare_io = 32 - 4 - 1                                    # I/O minus JTAG minus OUT
        self.assertEqual(clip.count("(no_connect"), spare_io)
        self.assertIn('(pin output line', e.library)
        self.assertIn('Package_LCC:PLCC-44', e.library)

    def test_3v3_parts_use_3v3_label(self):
        clip = ks.build(small("ATF1504ASV", "TQFP44")).clipboard
        self.assertIn('(label "+3V3"', clip)
        self.assertNotIn('(label "VCC"', clip)

    def test_tristate_pins(self):
        e = ks.build(dsg.load(EXAMPLE))
        self.assertIn('(pin tri_state line', e.library)          # CPU data bus
        self.assertEqual(e.warnings, [])

    def test_unlabelled_net_warns(self):
        d = dsg.parse_text("""
            part U1 74x04
            net "Net-(U1-Pad1)" ext: U1.1
            net Y ext: U1.2
        """)
        self.assertIn("has no label", " ".join(ks.build(d).warnings))

    def test_report_errors_refuse(self):
        d = dsg.parse_text("part U1 74x04\nnet X: U1.2 U1.4 U1.5")
        with self.assertRaises(ValueError):
            ks.build(d)


@unittest.skipUnless(dsg.find_kicad_cli(), "needs KiCad (kicad-cli)")
class TestKiCadRoundTrip(unittest.TestCase):
    def test_pins_land_on_their_label_nets(self):
        tmp = Path(tempfile.mkdtemp(prefix="cg_ksym_"))
        for d in (dsg.load(EXAMPLE), small("ATF1508AS", "PQFP160")):
            with self.subTest(design=d.name, package=d.package):
                r = generate.generate(d)
                e = ks.build(d, r)
                sch = tmp / f"{e.name}.kicad_sch"
                sch.write_text(ks.wrap_schematic(e.clipboard), encoding="utf-8")
                net = tmp / f"{e.name}.net"
                subprocess.run([dsg.find_kicad_cli(), "sch", "export", "netlist",
                                "--format", "kicadsexpr", "-o", str(net), str(sch)],
                               capture_output=True, check=True)
                _, nets = dsg.read_kicad_netlist(net)
                got = {int(n.pin): name.lstrip("/") for name, nodes in nets.items()
                       for n in nodes}
                for p in r.ports:
                    self.assertEqual(got[r.pins[p.name]], ks.label_text(p.net), p.name)
                _, pkg = devices.get_package(d.device, d.package)
                for pin, kind in pkg.power.items():
                    self.assertEqual(got[pin], kind)
                self.assertEqual(len(got), pkg.pin_count)
        lib = tmp / "lib.kicad_sym"
        lib.write_text(e.library, encoding="utf-8")
        out = subprocess.run([dsg.find_kicad_cli(), "sym", "export", "svg", "-o", str(tmp / "svg"),
                              str(lib)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main()
