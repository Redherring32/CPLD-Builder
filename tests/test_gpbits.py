"""SLG46826/24 bitstreams (gpbits.py): the register-map data, the cell table,
the files, a Go Configure project replayed against its hardware test log
(tests/reference/greenpak), and (with Yosys) that bitstreams for real
designs simulate like the designs, and that a wrong bit is caught."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import design as dsg, devices, generate, gpbits, greenpak, yosys   # noqa: E402

try:
    yosys.find_yosys()
    HAVE_YOSYS = True
except RuntimeError:
    HAVE_YOSYS = False

DESIGNS = {
    "decoder": """design dec
device {dev} {pkg}
part U7 74x139
net A13 ext: U7.2
net A14 ext: U7.3
net M2 ext: U7.1
net WRAM ext: U7.4
net PPU ext: U7.5
net Y2 ext: U7.6
net ROMSEL ext: U7.7
""",
    "flipflops": """design ff
device {dev} {pkg}
part U1 74x74
net P const=1: U1.4 U1.10
net CLR ext: U1.1 U1.13
net D1 ext: U1.2
net CK ext: U1.3 U1.11
net Q1 ext: U1.5
net D2 ext: U1.12
net Q2N ext: U1.8
""",
    "tristate": """design b
device {dev} {pkg}
part U1 74x125
net OE1 ext: U1.1
net A1 ext: U1.2
net Y1 ext: U1.3
net OE2 ext: U1.4
net A2 ext: U1.5
net Y2 ext: U1.6
""",
    "counter": """design ctr
device {dev} {pkg}
part U1 74x161
net CLR ext: U1.1
net CLK ext: U1.2
net A ext: U1.3
net B ext: U1.4
net ENP ext: U1.7
net LD ext: U1.9
net ENT ext: U1.10
net QB ext: U1.13
net QA ext: U1.14
net RCO ext: U1.15
net C const=0: U1.5 U1.6
""",
    "preset_clear": """design pc
device {dev} {pkg}
part U1 74x74
net CLR ext: U1.1
net D1 ext: U1.2
net CK ext: U1.3
net PRE ext: U1.4
net Q1 ext: U1.5
net Q1N ext: U1.6
net P const=1: U1.10 U1.13
net Z const=0: U1.11 U1.12
""",
    "open_drain": """design od
device {dev} {pkg}
part U1 74x05
net A ext: U1.1
net Y ext: U1.2
net B ext: U1.3
net YB ext: U1.4
""",
    "latch": """design l
device {dev} {pkg}
part U1 74x573
net OE const=0: U1.1
net LE ext: U1.11
net D0 ext: U1.2
net Q0 ext: U1.19
net D1 ext: U1.3
net Q1 ext: U1.18
""",
}


class DataTest(unittest.TestCase):
    def setUp(self):
        self.data = gpbits.load_data()

    def test_matrix_tables_are_complete(self):
        self.assertEqual(len(self.data["matrix_inputs"]), 64)
        outs = self.data["matrix_outputs"]
        self.assertEqual(len(outs), 96)
        for n, o in outs.items():
            self.assertEqual(o["bits"], [6 * int(n), 6 * int(n) + 5], o)

    def test_pins_match_the_device_tables(self):
        names = set()
        for dev in gpbits.SUPPORTED:
            for pkg in devices.DEVICES[dev].packages.values():
                names |= {n for n in pkg.pin_names.values() if re.fullmatch(r"IO\d+", n)}
        self.assertEqual(names, set(self.data["pins"]))
        for name, p in self.data["pins"].items():
            self.assertIn("matrix_in", p, name)

    def test_cells_dont_overlap(self):
        seen = {}
        used_outs = set()
        for c in gpbits.CELLS:
            bits = list(range(c.truth[0], c.truth[1] + 1)) + list(c.zero)
            if c.select is not None:
                bits.append(c.select)
            for b in bits:
                self.assertNotIn(b, seen, f"{c.name} and {seen.get(b)} share bit {b}")
                seen[b] = c.name
            for i in c.inputs:
                self.assertNotIn(i, used_outs, c.name)
                self.assertNotIn(i, gpbits.RESERVED_OUTPUTS, c.name)
                used_outs.add(i)
            self.assertEqual(c.truth[1] - c.truth[0] + 1, 2 ** len(c.inputs), c.name)

    def test_byte_order(self):
        bits = [0] * 2048
        bits[3] = bits[9] = 1
        b = gpbits.to_bytes(bits)
        self.assertEqual(len(b), 256)
        self.assertEqual(b[0], 0x08)
        self.assertEqual(b[1], 0x02)
        self.assertEqual(gpbits.from_bytes(b), bits)


REF = ROOT / "tests" / "reference" / "greenpak"


def gp6(name):
    """(NVM bits, XML text) of a Go Configure project."""
    text = (REF / name).read_text(encoding="utf-8")
    hexs = re.search(r"<nvmData[^>]*>([^<]*)<", text).group(1).split()
    return gpbits.from_bytes(bytes(int(x, 16) for x in hexs)), text


class EdgeDetModel(gpbits.GpModel):
    """GpModel plus the filter/edge detector (matrix out 55 -> in 27), which
    GreenHAL uses and cpldglue doesn't: an edge gives one short pulse."""
    def __init__(self, *a):
        super().__init__(*a)
        self.prev = None
        self.pulse = 0

    def settle(self):
        self.extra = {27: self.pulse ^ self.bits[1244]}
        super().settle()

    def step(self):
        super().step()
        x, mode = self.sel(55), self.field(1245, 1246)
        edge = self.prev is not None and x != self.prev and (mode == 2 or x == (mode == 0))
        self.prev = x
        if edge and self.bits[1243]:
            self.pulse = 1
            super().step()
            self.pulse = 0
            super().step()


class ReferenceTest(unittest.TestCase):
    """GreenHAL: an SLG46826 design made in Go Configure, and its hardware
    test log. Decoding its NVM with our register map and simulating it must
    reproduce every line."""
    PINS = {"iowr": "IO1", "a15": "IO3", "a14": "IO4", "cpu": "IO5", "cas": "IO8", "d2": "IO9",
            "d1": "IO10", "ramdis": "IO11", "reset": "IO12", "d0": "IO13", "d76": "IO14"}
    OUTS = {"a15": "IO7", "a14": "IO0", "cas0": "IO2", "cas1": "IO6"}

    def replay(self, project):
        bits, _ = gp6(project)
        m = EdgeDetModel(bits, gpbits.load_data())

        def put(**kw):
            for k, v in kw.items():
                m.ext[self.PINS[k]] = v
                m.step()
        put(iowr=1, a15=0, a14=0, cpu=1, cas=1, d2=0, d1=0, d0=0, ramdis=0, reset=1, d76=0)
        lines = bad = 0
        for line in (REF / "GreenHALTests.txt").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("Reset"):
                put(reset=0)
                put(reset=1)
            elif line.startswith("Set config"):          # OUT &7Fxx: A15 low, D7 D6 = 11
                n = int(line.split(":")[1])
                put(a15=0, d0=n & 1, d1=n >> 1 & 1, d2=n >> 2 & 1, d76=1)
                put(iowr=0)
                put(iowr=1)
                put(d76=0)
            elif line.startswith("bank"):
                v = dict(re.findall(r"(\w+)=(\d)", line))
                put(a15=int(v["a15"]), a14=int(v["a14"]))
            elif line.startswith("cpu"):
                ins, outs = re.split(r"\s{3,}", line, 1)
                for k, v in re.findall(r"(\w+)=(\d)", ins):
                    put(**{k: int(v)})
                want = {k: int(v) for k, v in re.findall(r"(\w+)=(\d)", outs)}
                got = {k: m.output(io) for k, io in self.OUTS.items()}
                lines += 1
                if got != want:
                    bad += 1
        return lines, bad

    def test_hardware_log_replays(self):
        for project in ("SLG46826G_TSSOP.gp6", "SLG46826V_QFN_DIP.gp6"):
            with self.subTest(project):
                lines, bad = self.replay(project)
                self.assertEqual(lines, 504)
                self.assertEqual(bad, 0, f"{bad} of {lines} lines differ")

    def test_output_pads_match_the_project(self):
        bits, text = gp6("SLG46826G_TSSOP.gp6")
        m = gpbits.GpModel(bits, gpbits.load_data())
        pads = dict((io, mode) for mode, io in
                    re.findall(r'<IOPad id="\d+" useCaseMode="(\d)">\s*<item id="\d+" caption="PIN \d+ \((IO\d+)\)', text))
        for io, mode in pads.items():
            p = gpbits.load_data()["pins"][io]
            if p.get("oe_bit"):
                self.assertEqual(bits[p["oe_bit"][0]], 1 if mode == "2" else 0, io)

    def test_multifunction_dffs_are_the_projects(self):
        """GreenHAL's MF1/MF4/MF6 are DFFs (shown as DFF/LATCH10/13/15); the
        LUT-mode MF cells aren't."""
        bits, text = gp6("SLG46826G_TSSOP.gp6")
        dff = {c.name for c in gpbits.CELLS if c.select is not None and c.dff and bits[c.select]}
        for n, cell in ((10, "3-bit LUT7/DFF10"), (13, "3-bit LUT10/DFF13"), (15, "3-bit LUT12/DFF15")):
            self.assertIn(f"DFF/LATCH{n} (MF", text)
            self.assertIn(cell, dff)
        for cell in ("4-bit LUT0/DFF9", "3-bit LUT8/DFF11", "3-bit LUT11/DFF14", "3-bit LUT13/DFF16"):
            self.assertNotIn(cell, dff)


@unittest.skipUnless(HAVE_YOSYS, "needs Yosys")
class BuildTest(unittest.TestCase):
    def build(self, name, dev="SLG46826", pkg="TSSOP20"):
        d = dsg.parse_text(DESIGNS[name].format(dev=dev, pkg=pkg))
        r = generate.generate(d)
        self.assertTrue(r.ok, r.errors)
        w = Path(tempfile.mkdtemp())
        m = greenpak.map_design(d, r, w / "map")
        return d, r, w, gpbits.build(d, r, m, w / "bits")

    def test_designs_simulate_like_the_design(self):
        for name in DESIGNS:
            with self.subTest(name):
                _, _, _, b = self.build(name)
                self.assertTrue(b.ok, (b.errors, b.check))
                self.assertTrue(b.check_ok)

    def test_dff_with_preset_and_clear_uses_the_4bit_cell(self):
        _, _, _, b = self.build("preset_clear")
        self.assertTrue(b.ok, (b.errors, b.check))
        self.assertIn("4-bit LUT0/DFF9", [c for c, what in b.placement if what.startswith("dff")])

    def test_open_drain_outputs(self):
        d, r, _, b = self.build("open_drain")
        self.assertTrue(b.ok, (b.errors, b.check))
        data = gpbits.load_data()
        pkg = devices.get_package(d.device, d.package)[1]
        for port in ("Y", "YB"):
            p = data["pins"][pkg.pin_names[r.pins[port]]]
            lo, hi = p["output_mode"]
            self.assertEqual((b.bits[lo], b.bits[hi]), (0, 1), f"{port}: 1x open-drain")

    def test_unused_pins_are_pulled_down(self):
        d, r, _, b = self.build("decoder")
        data = gpbits.load_data()
        pkg = devices.get_package(d.device, d.package)[1]
        used = {pkg.pin_names[p] for p in r.pins.values()}
        for io, p in data["pins"].items():
            lo, hi = p["pull_res"]
            want = (0, 0) if io in used else (1, 1)          # floating / 1M
            self.assertEqual((b.bits[lo], b.bits[hi]), want, io)
            self.assertEqual(b.bits[p["pull_up"][0]], 0, io)

    def test_slg46824_and_stqfn(self):
        _, _, _, b = self.build("decoder", "SLG46824", "STQFN20")
        self.assertTrue(b.ok, (b.errors, b.check))

    def test_owned_bits_leave_the_chip_settings_alone(self):
        _, _, _, b = self.build("decoder")
        owned = gpbits.to_bytes(b.owned)
        self.assertEqual(owned[0xE0:], bytes(32), "pages 14/15 must never be touched")
        lo, hi = gpbits.CONTROL_CODE_BITS
        self.assertFalse(any(b.owned[lo:hi + 1]), "the I2C address stays the chip's")
        self.assertEqual([b.bits[i] for i in range(lo, hi + 1)], [1, 0, 0, 0])

    def test_files(self):
        d, _, w, b = self.build("counter")
        files = gpbits.write_files(b, d, w / "out", "ctr")
        names = sorted(f.name for f in files)
        self.assertEqual(names, ["ctr.bin", "ctr.txt", "ctr_mask.bin", "ctr_programmer.ino"])
        self.assertEqual(len((w / "out" / "ctr.bin").read_bytes()), 256)
        ino = (w / "out" / "ctr_programmer.ino").read_text(encoding="utf-8")
        for arr in ("DATA", "MASK"):
            m = re.search(r"\b" + arr + r"\w*\[[^\]]*\]\s*(?:PROGMEM\s*)?=\s*\{([^}]*)\}", ino)
            self.assertIsNotNone(m, arr)
            self.assertEqual(len(re.findall(r"0x[0-9A-F]{2}", m.group(1))), 224, arr)
        txt = (w / "out" / "ctr.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(1 for l in txt if re.match(r"\d+\t", l)), 2048)

    def test_a_wrong_bit_is_caught(self):
        d, r, w, b = self.build("decoder")
        data = gpbits.load_data()
        pkg = devices.get_package(d.device, d.package)[1]
        pins = {s: pkg.pin_names[p] for s, p in r.pins.items()}
        top = generate.sanitize(d.name)
        net = w / "bits" / "gp_sim.json"
        ok, _ = gpbits.verify(net, top, b.bits, data, pins)
        self.assertTrue(ok)
        # flip one truth-table bit of every used LUT in turn: each must be seen
        used = {c for c, _ in b.placement}
        for c in gpbits.CELLS:
            if c.name not in used:
                continue
            for bit in range(c.truth[0], c.truth[1] + 1):
                bad = list(b.bits)
                bad[bit] ^= 1
                if not gpbits.verify(net, top, bad, data, pins)[0]:
                    break
            else:
                self.fail(f"no wrong truth bit of {c.name} was caught")

    def test_panel_payload(self):
        d = dsg.parse_text(DESIGNS["decoder"].format(dev="SLG46826", pkg="TSSOP20"))
        r = generate.generate(d)
        m = greenpak.map_design(d, r, Path(tempfile.mkdtemp()))
        p = greenpak.bitstream_payload(d, r, m, Path(tempfile.mkdtemp()))
        self.assertTrue(p["ok"], p)
        self.assertEqual(set(p["files"]), {"txt", "ino", "bin", "mask"})
        json.dumps(p)

    def test_other_greenpaks_have_no_bitstream(self):
        d = dsg.parse_text(DESIGNS["decoder"].format(dev="SLG46621", pkg="STQFN20"))
        r = generate.generate(d)
        m = greenpak.map_design(d, r, Path(tempfile.mkdtemp()))
        self.assertIsNone(greenpak.bitstream_payload(d, r, m, Path(tempfile.mkdtemp())))


if __name__ == "__main__":
    unittest.main()
