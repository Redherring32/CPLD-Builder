"""Check the fitter's result against the design.

The Microchip fitter writes NAME.tt3: the final equations as a Berkeley PLA
(".type fr": a 1 in an output column puts the row's input cube in that
output's on-set, a 0 in its off-set). Evaluating those equations on random
inputs and comparing with the simulator checks the whole chain - cpldglue's
Verilog, Yosys and the fitter - for combinational designs. Equations with
registers (.D/.C/... outputs) are not checked.
"""
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Pla:
    def __init__(self, text: str):
        self.inputs = re.search(r"^\.ilb (.*)$", text, re.M).group(1).split()
        self.outputs = re.search(r"^\.ob (.*)$", text, re.M).group(1).split()
        self.rows: List[Tuple[str, str]] = []
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 2 and set(parts[0]) <= set("01-") and len(parts[0]) == len(self.inputs):
                self.rows.append((parts[0], parts[1]))

    @property
    def registered(self) -> bool:
        return any(re.search(r"\.(D|T|C|CE|AR|AP|SP|LH)$", o) for o in self.outputs)

    def evaluate(self, inputs: Dict[str, int]) -> Dict[str, int]:
        vals = dict(inputs)
        out: Dict[str, int] = {}
        for _ in range(len(self.outputs) + 1):     # internal nodes feed back
            for k, name in enumerate(self.outputs):
                on = [cube for cube, o in self.rows if o[k] == "1"]
                off = [cube for cube, o in self.rows if o[k] == "0"]

                def hit(cube: str) -> bool:
                    return all(c == "-" or vals.get(self.inputs[j], 0) == int(c)
                               for j, c in enumerate(cube))
                if on:
                    out[name] = int(any(hit(c) for c in on))
                elif off:
                    out[name] = 0 if any(hit(c) for c in off) else 1
                else:
                    out[name] = 0
            for n in self.inputs:
                if n in out:
                    vals[n] = out[n]
        return out


def verify(name: str, outdir: Path, vectors: int = 300) -> Optional[str]:
    """Compare NAME.tt3 with a simulation of NAME.v. Returns a one-line
    result, or None if there is nothing to check."""
    from . import yosys
    from .sim import Sim
    tt3 = outdir / f"{name}.tt3"
    if not tt3.exists():
        return None
    pla = Pla(tt3.read_text(encoding="utf-8", errors="replace"))
    if pla.registered:
        return "Fitted logic not checked (it has flip-flops; only combinational logic is checked)."
    sim = Sim.from_file(yosys.sim_netlist([outdir / f"{name}.v"], name, outdir / "fitcheck.json"), name)
    ins = [i for i in pla.inputs if sim.ports.get(i, {}).get("direction") == "input"]
    outs = [o for o in pla.outputs if not o.endswith(".OE") and o in sim.ports]
    rng = random.Random(1)
    bad = []
    for _ in range(vectors):
        v = {i: rng.getrandbits(1) for i in ins}
        sim.set(**v)
        sim.step()
        got = pla.evaluate(v)
        for o in outs:
            want = sim.get(o)
            have = got[o] if got.get(o + ".OE", 1) else None
            if want != have:
                bad.append(f"{o} with {v}")
    if bad:
        return (f"WARNING: the fitted logic differs from the design in {len(bad)} case(s), "
                f"e.g. {bad[0]}")
    return f"Fitted logic matches the design ({len(outs)} outputs, {vectors} random input sets)."
