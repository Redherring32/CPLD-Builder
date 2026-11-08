"""End-to-end checks of the generator.

* The TinyTendo example (U7 + U8 + U9) must behave exactly like the
  hand-written Hardware/Motherboard/Verilog/tinytendo_glue.v.
* Importing straight from the KiCad schematic must give the same design
  (skipped if KiCad or the schematic is not available).
* Internal 3-state nets become muxes; contention is reported.
"""
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import design as dsg, generate, yosys     # noqa: E402
from cpldglue.sim import Sim                            # noqa: E402

REPO = ROOT.parent
HAND = ROOT / "tests" / "reference" / "tinytendo_glue.v"
SCH = REPO / "Hardware" / "Motherboard" / "TinyTendo-schematic.kicad_sch"

# hand-written port -> generated port
PORT_MAP = {
    "m2": "M2", "cpu_a13": "CPU_A13", "cpu_a14": "CPU_A14", "cpu_a15": "CPU_A15",
    "wram_ce_n": "WRAM_CE_n", "ppu_ce_n": "PPU_CE_n", "romsel_n": "ROMSEL_n",
    "ppu_a13": "PPU_A13", "ppu_a13_n": "PPU_A13_n",
    "oe1_n": "OE1_n", "oe2_n": "OE2_n",
    "p1_d0": "s4016_D0", "p1_d3": "s4016_D3", "p1_d4": "s4016_D4",
    "p2_d0": "s4017_D0", "p2_d3": "s4017_D3", "p2_d4": "s4017_D4",
}


def build(d: dsg.Design, tmp: Path) -> Sim:
    r = generate.generate(d)
    assert r.ok, r.report(d)
    top = generate.sanitize(d.name)
    v = tmp / f"{top}.v"
    v.write_text(r.verilog, encoding="utf-8")
    return Sim.from_file(yosys.sim_netlist([v], top, tmp / f"{top}.json"), top), r


def compare_with_hand(test, gen: Sim, vectors=600):
    tmp = Path(tempfile.mkdtemp(prefix="cg_hand_"))
    hand = Sim.from_file(yosys.sim_netlist([HAND], "tinytendo_glue", tmp / "h.json"),
                         "tinytendo_glue")
    ins = [p for p, v in hand.ports.items() if v["direction"] == "input"]
    rng = random.Random(7)
    for _ in range(vectors):
        vals = {p: rng.getrandbits(1) for p in ins}
        if vals["oe1_n"] == 0 and vals["oe2_n"] == 0:
            vals["oe2_n"] = 1      # the 2A03 never reads $4016 and $4017 at once
        hand.set(**vals); hand.step()
        gen.set(**{PORT_MAP[k]: v for k, v in vals.items()}); gen.step()
        for hp, gp in PORT_MAP.items():
            if hand.ports[hp]["direction"] == "output":
                test.assertEqual(gen.get(gp), hand.get(hp), f"{hp} for {vals}")
        hb = hand.ports["cpu_d"]["bits"]
        for i in range(5):
            want = hand._v(hb[i])
            got = gen.get(f"CPU_D{i}")
            test.assertEqual(got, want, f"CPU_D{i} for {vals}")


class TestTinyTendo(unittest.TestCase):
    def test_text_netlist_matches_hand_written(self):
        d = dsg.load(ROOT / "examples" / "tinytendo.cg")
        tmp = Path(tempfile.mkdtemp(prefix="cg_tt_"))
        gen, r = build(d, tmp)
        self.assertEqual(len(r.ports), 22)
        self.assertEqual(len(set(r.pins.values())), 22)
        compare_with_hand(self, gen)

    @unittest.skipUnless(SCH.exists() and dsg.find_kicad_cli(), "needs KiCad + schematic")
    def test_kicad_import_matches_hand_written(self):
        d = dsg.from_kicad(SCH, ["U7", "U8", "U9"], name="tinytendo_glue")
        tmp = Path(tempfile.mkdtemp(prefix="cg_kc_"))
        gen, r = build(d, tmp)
        self.assertEqual(sorted(p.name for p in r.ports),
                         sorted(list(PORT_MAP.values()) + [f"CPU_D{i}" for i in range(5)]))
        compare_with_hand(self, gen)


class TestRules(unittest.TestCase):
    def test_internal_tristate_becomes_mux(self):
        # Two 74x125 buffers drive one internal net that feeds an inverter.
        d = dsg.parse_text("""
            design mux
            part U1 74x125
            part U2 74x04
            net A ext: U1.2
            net B ext: U1.5
            net EA ext: U1.1
            net EB ext: U1.4
            net BUS: U1.3 U1.6 U2.1
            net Y ext: U2.2
            net GND: U1.7 U1.9 U1.10 U1.12 U1.13
        """)
        gen, r = build(d, Path(tempfile.mkdtemp(prefix="cg_mux_")))
        # EA/EB are active-low enables. Nothing enabled: BUS idles high.
        for a, b, ea, eb, want in [(1, 0, 0, 1, 0), (0, 1, 1, 0, 0), (1, 1, 1, 1, 0),
                                   (0, 1, 0, 1, 1), (0, 0, 1, 1, 0),
                                   (0, 1, 0, 0, 1)]:          # both: first (A) wins
            gen.set(A=a, B=b, EA=ea, EB=eb)
            gen.step()
            self.assertEqual(gen.get("Y"), want, (a, b, ea, eb))

    def test_contention_is_an_error(self):
        d = dsg.parse_text("""
            part U1 74x04
            net X: U1.2 U1.4 U1.5
        """)
        r = generate.generate(d)
        self.assertFalse(r.ok)
        self.assertIn("more than one driver", " ".join(r.errors))

    def test_unused_gates_are_left_out(self):
        # Gate 1 drives Y. Gate 2 only feeds gate 3, whose output goes nowhere:
        # both are unused, so U_IN (external, into gate 2) needs no pin.
        # Gate 4 feeds gate 1, so it is used even though its output is internal.
        d = dsg.parse_text("""
            design prune
            part U1 74x32
            part U2 74x74
            net A ext: U1.1
            net Y ext: U1.3
            net U_IN ext: U1.4
            net CHAIN: U1.6 U1.9
            net LOOP: U1.11 U1.2
            net C ext: U1.12
            net CLK ext: U2.3
            net Q ext: U2.5
            net D ext: U2.2
            net VCC: U2.1 U2.4
            net GND: U1.13
        """)
        r = generate.generate(d)
        self.assertTrue(r.ok, r.report(d))
        self.assertEqual(r.unused, {"U1": [1, 2], "U2": [1]})
        self.assertEqual(sorted(p.name for p in r.ports), ["A", "C", "CLK", "D", "Q", "Y"])
        self.assertEqual(r.macrocells, (2, 1, 32))
        self.assertEqual(r.macrocell_estimate, 2)          # the flip-flop sits at Q
        self.assertEqual(r.macrocell_parts, {"U1": (1, 0, 0), "U2": (1, 1, 1)})
        text = " ".join(r.notes)
        self.assertIn("U1 (74x32): gates 2 and 3 unused", text)
        self.assertIn("U2 (74x74): flip-flop 2 unused", text)
        self.assertIn("net U_IN only goes to unused gates", text)
        self.assertNotIn("not connected", " ".join(r.warnings))   # no noise from unused gates

    def test_whole_part_unused(self):
        d = dsg.parse_text("""
            part U1 74x138
            net A ext: U1.1
            net X: U1.15
        """)
        r = generate.generate(d)
        self.assertEqual(r.ports, [])
        self.assertIn("left out entirely", " ".join(r.notes))

    def test_too_many_pins(self):
        lines = ["part U1 74x541", "part U2 74x541", "part U3 74x541"]
        for u in (1, 2, 3):
            for k in range(1, 9):
                lines.append(f"net A{u}{k} ext: U{u}.{k + 1}")
                lines.append(f"net Y{u}{k} ext: U{u}.{19 - k}")
        r = generate.generate(dsg.parse_text("\n".join(lines)))
        self.assertIn("design needs 48 pins", " ".join(r.errors))

    def test_open_collector_wired_and(self):
        # Two open-collector inverters on one internal net = wired-AND of ~a, ~b
        d = dsg.parse_text("""
            design oc
            part U1 74x05
            part U2 74x04
            net A ext: U1.1
            net B ext: U1.3
            net W: U1.2 U1.4 U2.1
            net Y ext: U2.2
        """)
        gen, r = build(d, Path(tempfile.mkdtemp(prefix="cg_oc_")))
        for a in (0, 1):
            for b in (0, 1):
                gen.set(A=a, B=b); gen.step()
                wired = int(not (a or b))          # low if either input is high
                self.assertEqual(gen.get("Y"), 1 - wired)


if __name__ == "__main__":
    unittest.main()
