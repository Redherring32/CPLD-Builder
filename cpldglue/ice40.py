"""Lattice iCE40 target (HX1K, HX4K, UP5K), with the open tool chain.

Yosys synthesises the generated Verilog for the iCE40 (synth_ice40), nextpnr
places and routes it against a .pcf of the editor's pins, and icepack makes
the bitstream (.bin, for the configuration flash or iceprog). nextpnr and
icepack come from the yowasp-nextpnr-ice40 wheel (WebAssembly, the same way
Yosys does) unless a native nextpnr-ice40 / icepack is on the PATH.

The check: the synthesised netlist (SB_LUT4s, SB_DFFs, ...) is simulated
against the design with Yosys's own iCE40 cell models. Placement and routing
are nextpnr's; they aren't simulated here.

iCE40 I/O is 3.3 V and NOT 5 V tolerant: on a 5 V board it needs level
shifters (or series resistors and care).
"""
from __future__ import annotations

import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# nextpnr-ice40 device and package arguments, and LUT counts
NEXTPNR_ARGS = {
    "iCE40HX1K": ["--hx1k", "--package", "tq144"],
    "iCE40HX4K": ["--hx8k", "--package", "tq144:4k"],     # the 4K is an 8K die, limited
    "iCE40UP5K": ["--up5k", "--package", "sg48"],
}
LUTS = {"iCE40HX1K": 1280, "iCE40HX4K": 3520, "iCE40UP5K": 5280}


# ---- finding nextpnr / icepack ---------------------------------------------------------
def find_tool(name: str) -> List[str]:
    """Command prefix for nextpnr-ice40 or icepack: $CPLDGLUE_ICE40_BIN (a
    folder), a native tool on the PATH, yowasp-<name>, or the downloaded copy."""
    env = os.environ.get("CPLDGLUE_ICE40_BIN")
    if env:
        for cand in (Path(env) / name, Path(env) / f"{name}.exe"):
            if cand.exists():
                return [str(cand)]
    for exe in (name, f"yowasp-{name}"):
        p = shutil.which(exe)
        if p:
            return [p]
    scripts = Path(sys.executable).parent
    for cand in (scripts / f"yowasp-{name}.exe", scripts / f"yowasp-{name}",
                 scripts / "Scripts" / f"yowasp-{name}.exe"):
        if cand.exists():
            return [str(cand)]
    from . import deps
    from .yosys import self_command
    if deps.nextpnr_installed():
        return self_command() + [f"_{name}"]
    raise RuntimeError(f"{name} not found. Download nextpnr from Setup in the editor, run "
                       f"`cpldglue setup nextpnr`, or: pip install yowasp-nextpnr-ice40")


def tools_found() -> Optional[str]:
    try:
        return " ".join(find_tool("nextpnr-ice40"))
    except RuntimeError:
        return None


def _run(cmd: List[str], cwd: Path, what: str) -> str:
    from .yosys import no_window
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, **no_window())
    except OSError as e:
        raise RuntimeError(f"could not run {what} ({e})") from None
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed:\n{out[-4000:]}")
    return out


# ---- the flow -------------------------------------------------------------------------------
def pcf_text(pins: Dict[str, int]) -> str:
    return "".join(f"set_io {sig} {pin}\n" for sig, pin in sorted(pins.items(), key=lambda kv: kv[1]))


def build(design, r, outdir: Path, top: str) -> dict:
    """Synthesise, place and route, pack. Returns {"ok", "log", "luts", "check_ok"}."""
    from . import yosys
    dev = design.device.upper()
    name = next((n for n in NEXTPNR_ARGS if n.upper() == dev), None)
    if name is None:
        raise ValueError(f"{design.device} is not an iCE40 this tool knows")
    outdir.mkdir(parents=True, exist_ok=True)
    verilog = r.verilog.replace(f"module {_base(design)} (", f"module {top} (", 1)
    (outdir / f"{top}.v").write_text(verilog, encoding="utf-8")
    (outdir / f"{top}.pcf").write_text(pcf_text(r.pins), encoding="utf-8")
    log = [f"Wrote {top}.v and {top}.pcf"]
    yosys.run_script(f"read_verilog {top}.v\nsynth_ice40 -top {top} -json {top}.json\n"
                     f"write_verilog -noattr {top}_synth.v\n", outdir, "ice40_synth.log")
    log.append("Synthesised with Yosys (synth_ice40)")
    nlog = _run(find_tool("nextpnr-ice40") + NEXTPNR_ARGS[name] +
                ["--json", f"{top}.json", "--pcf", f"{top}.pcf", "--asc", f"{top}.asc",
                 "--log", "nextpnr.log", "-q"], outdir, "nextpnr-ice40")
    text = (outdir / "nextpnr.log").read_text(encoding="utf-8", errors="replace") \
        if (outdir / "nextpnr.log").exists() else nlog
    m = re.search(r"ICESTORM_LC:\s+(\d+)/\s*(\d+)", text)
    luts = (int(m.group(1)), int(m.group(2))) if m else None
    fmax = re.findall(r"Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz", text)
    log.append("Placed and routed with nextpnr-ice40" +
               (f": {luts[0]} of {luts[1]} logic cells" if luts else ""))
    best = {}
    for clk, mhz in fmax:                          # the last report is after routing
        best[clk.split("$")[0]] = mhz
    for clk, mhz in best.items():
        log.append(f"  max frequency for {clk}: {mhz} MHz")
    _run(find_tool("icepack") + [f"{top}.asc", f"{top}.bin"], outdir, "icepack")
    log.append(f"Wrote {top}.bin (bitstream for the SPI flash or iceprog)")
    ok, msg = check(outdir, top)
    log.append(msg)
    return {"ok": ok and (outdir / f"{top}.bin").exists(), "log": "\n".join(log),
            "luts": luts, "check_ok": ok}


def _base(design) -> str:
    from .generate import sanitize
    return sanitize(design.name)


def check(outdir: Path, top: str, steps: int = 600) -> Tuple[bool, str]:
    """Simulate the synthesised netlist against the design."""
    from . import yosys
    from .sim import Sim
    ref = Sim.from_file(yosys.sim_netlist([outdir / f"{top}.v"], top, outdir / "ref_sim.json"), top)
    yosys.run_script(f"""read_json {top}.json
delete =A:blackbox
read_verilog -D NO_ICE40_DEFAULT_ASSIGNMENTS -specify +/ice40/cells_sim.v
hierarchy -top {top}
proc
flatten -wb
tribuf
opt_clean
techmap
opt -fast
dfflegalize -cell $_DFFSR_PPP_ 01 -cell $_DLATCH_P_ 01
opt_clean
write_json synth_sim.json
""", outdir, "ice40_check.log")
    dut = Sim.from_file(outdir / "synth_sim.json", top)
    return compare(ref, dut, steps)


def compare(ref, dut, steps: int = 600, seed: int = 1) -> Tuple[bool, str]:
    """Drive both simulations with the same inputs, changing one or two at a
    time (so a clock never moves together with its data), and compare every
    output the design defines."""
    ins = [n for n, p in ref.ports.items() if p["direction"] == "input"]
    outs = [n for n, p in ref.ports.items() if p["direction"] != "input"]
    inouts = [n for n in outs if ref.ports[n]["direction"] == "inout"]
    tbuf_en = {y: e for _, e, y in ref.tbuf}

    def design_drives(port: str) -> bool:
        e = tbuf_en.get(ref.ports[port]["bits"][0])
        return e is not None and ref._v(e) == 1

    rng = random.Random(seed)
    bad, n = [], 0
    v = {i: 0 for i in ins}
    for k in range(steps):
        for i in rng.sample(ins, min(len(ins), rng.choice((1, 2)))) if ins else []:
            v[i] ^= 1
        released = {i: None for i in inouts}
        for s in (ref, dut):
            s.set(**v, **released)
            s.step()
        # drive the bidirectional pins the design isn't driving
        ext = {i: rng.getrandbits(1) for i in inouts if not design_drives(i)}
        if ext:
            for s in (ref, dut):
                s.set(**ext)
                s.step()
        for o in outs:
            w = ref.get(o)
            if w is None or o in ext:
                continue
            n += 1
            if dut.get(o) != w:
                bad.append(f"{o} = {dut.get(o)}, expected {w} (step {k})")
    if bad:
        return False, (f"WARNING: the synthesised netlist differs from the design in "
                       f"{len(bad)} case(s), e.g. {bad[0]}")
    return True, (f"Synthesised netlist matches the design ({len(outs)} outputs, {n} values "
                  f"compared over {steps} input changes).")
