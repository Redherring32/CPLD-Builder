"""Variants: boards with "fit one of" chips (e.g. the MouseBite Labs
discrete-mapper cartridge: a 74x377 *or* one of two 74x161s).

Build mode makes one design per variant with the same pins in each; pins
mode puts every variant in one CPLD, chosen by VAR_SEL pins. The key check:
with a variant's code on VAR_SEL, the pins-mode design behaves exactly like
that variant built on its own.
"""
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import design as dsg, generate, yosys       # noqa: E402
from cpldglue.sim import Sim                              # noqa: E402

try:
    yosys.find_yosys()
    HAVE_YOSYS = True
except RuntimeError:
    HAVE_YOSYS = False

# A cut-down version of the mapper: a 74x377 latch or a 74x161 counter
# drives the bank outputs Q0..Q3; a 74x32 is fitted in every variant.
MAPPER = """
design mapper
device ATF1504AS PLCC44
part U4A 74x377
part U4B 74x161
part U5 74x32
net D0 ext: U4A.3 U4B.3
net D1 ext: U4A.4 U4B.4
net D2 ext: U4A.7 U4B.5
net D3 ext: U4A.8 U4B.6
net CLK ext: U4A.11 U4B.2
net WE_n ext: U4A.1 U4B.9
net Q0 ext: U4A.2 U4B.14 U5.1
net Q1 ext: U4A.5 U4B.13 U5.4
net Q2 ext: U4A.6 U4B.12
net Q3 ext: U4A.9 U4B.11
net A14 ext: U5.2 U5.5
net OUT0 ext: U5.3
net OUT1 ext: U5.6
net VCC: U4B.1 U4B.7 U4B.10
variant AxROM: U4A
variant UxROM: U4B
"""


def mapper(mode="build", active=""):
    d = dsg.parse_text(MAPPER)
    d.variant_mode, d.variant = mode, active
    return d


class TestModel(unittest.TestCase):
    def test_text_round_trip(self):
        d = mapper("pins", "UxROM")
        d2 = dsg.parse_text(dsg.to_text(d))
        self.assertEqual((d2.variants, d2.variant_mode, d2.variant),
                         ({"AxROM": ["U4A"], "UxROM": ["U4B"]}, "pins", "UxROM"))
        self.assertEqual(dsg.Design.from_json(d.to_json()).variants, d.variants)

    def test_for_variant(self):
        v = mapper().for_variant("UxROM")
        self.assertEqual(set(v.parts), {"U4B", "U5"})
        self.assertTrue(all(n.ref != "U4A" for net in v.nets.values() for n in net.nodes))
        self.assertEqual(v.variant_of, "UxROM")
        with self.assertRaises(ValueError):
            mapper().for_variant("nope")


class TestGenerate(unittest.TestCase):
    def test_build_mode_shares_pins(self):
        pins = {}
        for v in ("AxROM", "UxROM"):
            r = generate.generate(mapper("build", v))
            self.assertEqual(r.errors, [], v)
            self.assertEqual(r.variant, v)
            pins[v] = r.pins
        common = set(pins["AxROM"]) & set(pins["UxROM"])
        self.assertGreaterEqual(len(common), 10)
        for sig in common:
            self.assertEqual(pins["AxROM"][sig], pins["UxROM"][sig], sig)

    def test_pins_mode_adds_select_and_no_contention(self):
        r = generate.generate(mapper("pins"))
        self.assertEqual(r.errors, [])
        self.assertIn("VAR_SEL0", [p.name for p in r.ports])
        self.assertEqual(r.select_codes, {"AxROM": "0", "UxROM": "1"})
        self.assertIn("chosen by the variant", " ".join(r.notes))

    def test_without_variants_it_is_still_contention(self):
        d = mapper()
        d.variants = {}
        self.assertIn("more than one driver", " ".join(generate.generate(d).errors))

    def test_contention_inside_one_variant_is_caught(self):
        d = mapper("pins")
        d.variants = {"both": ["U4A", "U4B"]}
        self.assertIn("in variant both", " ".join(generate.generate(d).errors))


@unittest.skipUnless(HAVE_YOSYS, "needs Yosys")
class TestEquivalence(unittest.TestCase):
    def sim(self, d, tmp):
        r = generate.generate(d)
        self.assertEqual(r.errors, [])
        top = generate.sanitize(d.name)
        v = tmp / f"{top}_{d.variant_mode}_{d.variant}.v"
        v.write_text(r.verilog, encoding="utf-8")
        return Sim.from_file(yosys.sim_netlist([v], top, v.with_suffix(".json")), top)

    def test_select_pins_behave_like_each_variant(self):
        tmp = Path(tempfile.mkdtemp(prefix="cg_var_"))
        both = self.sim(mapper("pins"), tmp)
        for code, v in enumerate(("AxROM", "UxROM")):
            single = self.sim(mapper("build", v), tmp)
            rng = random.Random(code)
            compared = 0
            ins = [p for p, d in single.ports.items() if d["direction"] == "input"]
            outs = [p for p, d in single.ports.items() if d["direction"] != "input"]
            for step in range(300):
                vals = {p: rng.getrandbits(1) for p in ins if p != "CLK"}
                for clk in (0, 1):                       # one clock edge per step
                    vals["CLK"] = clk
                    single.set(**vals)
                    single.step()
                    both.set(VAR_SEL0=code, **vals)
                    both.step()
                    for o in outs:
                        want = single.get(o)
                        if want is not None:             # registers start unknown
                            self.assertEqual(both.get(o), want, (v, step, o))
                            compared += 1
            self.assertGreater(compared, 1000, v)


if __name__ == "__main__":
    unittest.main()
