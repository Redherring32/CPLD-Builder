"""Gowin LittleBee target (GW1NZ-1, GW1N-4, GW1N-9, GW1NR-9), with the open
tool chain.

Yosys synthesises the generated Verilog for the GW1N (synth_gowin),
nextpnr-himbaechel places and routes it against a .cst of the editor's pins,
and gowin_pack (Project Apicula) makes the bitstream (.fs, which
openFPGALoader writes to the chip's own flash). nextpnr comes from the
yowasp-nextpnr-himbaechel-gowin wheel (WebAssembly, like Yosys) and
gowin_pack is pure Python; both can be downloaded from Setup, unless a
native nextpnr-himbaechel / gowin_pack is on the PATH.

Two checks, both simulated against the design with Yosys's Gowin cell models:
the synthesised netlist (as for the iCE40), and the bitstream itself, read
back with Apicula's gowin_unpack and wired up through the pins in the .cst.
The second covers placement, routing, packing and the pin numbers, as far as
Apicula's decoder knows the chip; no cpldglue Gowin build has been tried on a
chip yet.

Pins that program or configure the chip (JTAG, RECONFIG_N, MODE, DONE, READY)
are left alone. Dual-purpose pins the design uses (the SSPI/MSPI/CPU
configuration pins, I2C) are switched to ordinary I/O in the bitstream.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .ice40 import _run, compare

# device, package -> (nextpnr part number, Apicula family)
PARTS = {
    ("GW1NZ-1", "FN32"): ("GW1NZ-LV1FN32C6/I5", "GW1NZ-1"),
    ("GW1N-4", "QN48"): ("GW1N-LV4QN48C6/I5", "GW1N-4"),
    ("GW1N-4", "QN88"): ("GW1N-LV4QN88C6/I5", "GW1N-4"),
    ("GW1N-4", "LQ144"): ("GW1N-LV4LQ144C6/I5", "GW1N-4"),
    ("GW1N-9", "QN48"): ("GW1N-LV9QN48C6/I5", "GW1N-9C"),
    ("GW1N-9", "QN88"): ("GW1N-LV9QN88C6/I5", "GW1N-9C"),
    ("GW1N-9", "LQ144"): ("GW1N-LV9LQ144C6/I5", "GW1N-9C"),
    ("GW1NR-9", "QN88P"): ("GW1NR-LV9QN88PC6/I5", "GW1N-9C"),
}
LUTS = {"GW1NZ-1": 1152, "GW1N-4": 4608, "GW1N-9": 8640, "GW1NR-9": 8640}

# pin function -> the gowin_pack switch that makes it an ordinary I/O
GPIO_SWITCHES = {
    "SSPI_CS_N": "--sspi_as_gpio", "SO": "--sspi_as_gpio", "SI": "--sspi_as_gpio",
    "SCLK": "--sspi_as_gpio",
    "MCLK": "--mspi_as_gpio", "MCS_N": "--mspi_as_gpio", "MO": "--mspi_as_gpio",
    "MI": "--mspi_as_gpio", "FASTRD_N": "--mspi_as_gpio",
    "DIN": "--cpu_as_gpio", "DOUT": "--cpu_as_gpio", "CLKHOLD_N": "--cpu_as_gpio",
    "WE_N": "--cpu_as_gpio", **{f"D{i}": "--cpu_as_gpio" for i in range(8)},
    "SDA": "--i2c_as_gpio", "SCL": "--i2c_as_gpio",
}
NEXTPNR = "nextpnr-himbaechel"
PACK = "gowin_pack"
UNPACK = "gowin_unpack"


# ---- finding nextpnr-himbaechel / gowin_pack ----------------------------------------
def find_tool(name: str) -> List[str]:
    """Command prefix for nextpnr-himbaechel or gowin_pack: $CPLDGLUE_GOWIN_BIN
    (a folder), a native tool on the PATH, the yowasp / Apicula scripts next to
    this Python, or the downloaded copy."""
    exes = {NEXTPNR: [NEXTPNR, "yowasp-nextpnr-himbaechel-gowin"], PACK: [PACK],
            UNPACK: [UNPACK]}[name]
    env = os.environ.get("CPLDGLUE_GOWIN_BIN")
    if env:
        for exe in exes:
            for cand in (Path(env) / exe, Path(env) / f"{exe}.exe"):
                if cand.exists():
                    return [str(cand)]
    for exe in exes:
        p = shutil.which(exe)
        if p:
            return [p]
    scripts = Path(sys.executable).parent
    for exe in exes:
        for cand in (scripts / f"{exe}.exe", scripts / exe, scripts / "Scripts" / f"{exe}.exe"):
            if cand.exists():
                return [str(cand)]
    from . import deps
    from .yosys import self_command
    if deps.gowin_installed():
        return self_command() + [f"_{name}"]
    raise RuntimeError(f"{name} not found. Download the Gowin tools from Setup, run "
                       f"`cpldglue setup gowin`, or: pip install yowasp-nextpnr-himbaechel-gowin")


def tools_found() -> Optional[str]:
    try:
        find_tool(PACK)
        return " ".join(find_tool(NEXTPNR))
    except RuntimeError:
        return None


# ---- the flow -------------------------------------------------------------------------------
def cst_text(pins: Dict[str, int]) -> str:
    return "".join(f'IO_LOC "{sig}" {pin};\n'
                   for sig, pin in sorted(pins.items(), key=lambda kv: kv[1]))


def part_of(design) -> Tuple[str, str, str]:
    """(device name, nextpnr part number, Apicula family) for the design."""
    from . import devices
    dev, pkg = devices.get_package(design.device, design.package)
    part = PARTS.get((dev.name, pkg.name))
    if part is None:
        raise ValueError(f"{design.device} {design.package} is not a Gowin part this tool knows")
    return (dev.name,) + part


def gpio_switches(design, pins: Dict[str, int]) -> List[str]:
    """The gowin_pack switches the design's pins need (dual-purpose pins)."""
    from . import devices
    _, pkg = devices.get_package(design.device, design.package)
    out = []
    for pin in pins.values():
        for fn in pkg.pin_names.get(pin, "").split("/")[1:]:
            sw = GPIO_SWITCHES.get(fn)
            if sw and sw not in out:
                out.append(sw)
    return sorted(out)


def build(design, r, outdir: Path, top: str) -> dict:
    """Synthesise, place and route, pack. Returns {"ok", "log", "luts", "check_ok"}."""
    from . import yosys
    name, part, family = part_of(design)
    outdir.mkdir(parents=True, exist_ok=True)
    verilog = r.verilog.replace(f"module {_base(design)} (", f"module {top} (", 1)
    (outdir / f"{top}.v").write_text(verilog, encoding="utf-8")
    (outdir / f"{top}.cst").write_text(cst_text(r.pins), encoding="utf-8")
    log = [f"Wrote {top}.v and {top}.cst"]
    yosys.run_script(f"read_verilog {top}.v\nsynth_gowin -noalu -top {top} -json {top}.json\n",
                     outdir, "gowin_synth.log")
    log.append("Synthesised with Yosys (synth_gowin -noalu: no carry chains, which glue "
               "logic doesn't need and gowin_unpack doesn't read back faithfully)")
    nlog = _run(find_tool(NEXTPNR) +
                ["--device", part, "--vopt", f"family={family}", "--vopt", f"cst={top}.cst",
                 "--json", f"{top}.json", "--write", f"{top}_pnr.json",
                 "--log", "nextpnr.log", "-q"], outdir, "nextpnr-himbaechel")
    text = (outdir / "nextpnr.log").read_text(encoding="utf-8", errors="replace") \
        if (outdir / "nextpnr.log").exists() else nlog
    m = re.search(r"LUT4:\s+(\d+)/\s*(\d+)", text)
    luts = (int(m.group(1)), int(m.group(2))) if m else None
    log.append(f"Placed and routed with nextpnr-himbaechel ({part})" +
               (f": {luts[0]} of {luts[1]} LUTs" if luts else ""))
    best = {}
    for clk, mhz in re.findall(r"Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz", text):
        best[clk.split("$")[0]] = mhz                 # the last report is after routing
    for clk, mhz in best.items():
        log.append(f"  max frequency for {clk}: {mhz} MHz")
    sw = gpio_switches(design, r.pins)
    _run(find_tool(PACK) + ["-d", family] + sw + ["-o", f"{top}.fs", f"{top}_pnr.json"],
         outdir, "gowin_pack")
    log.append(f"Wrote {top}.fs (bitstream; program it with openFPGALoader -f {top}.fs, "
               f"or Gowin's programmer)" + (f"; {' '.join(sw)}" if sw else ""))
    ok, msg = check(outdir, top)
    log.append(msg)
    try:
        bok, bmsg = check_bitstream(design, outdir, top, family)
    except (RuntimeError, ValueError, KeyError) as e:
        bok, bmsg = False, f"WARNING: could not read the bitstream back: {e}"
    log.append(bmsg)
    ok = ok and bok
    return {"ok": ok and (outdir / f"{top}.fs").exists(), "log": "\n".join(log),
            "luts": luts, "check_ok": ok}


def _base(design) -> str:
    from .generate import sanitize
    return sanitize(design.name)


# Yosys's Gowin IOBUF model drives I from IO; the pad goes to O.
IOBUF_FIX = """module IOBUF (O, IO, I, OEN);
  input I, OEN;
  output O;
  inout IO;
  assign IO = OEN ? 1'bz : I;
  assign O = IO;
endmodule
"""
SIM_FLOW = """hierarchy -top {top}
proc
flatten -wb
tribuf
opt_clean
techmap
opt -fast
dfflegalize -cell $_DFFSR_PPP_ 01 -cell $_DLATCH_P_ 01
opt_clean
write_json {out}
"""


def _cells(outdir: Path) -> str:
    (outdir / "gowin_iobuf.v").write_text(IOBUF_FIX, encoding="utf-8")
    return "read_verilog +/gowin/cells_sim.v\ndelete IOBUF\nread_verilog gowin_iobuf.v\n"


def check(outdir: Path, top: str, steps: int = 600) -> Tuple[bool, str]:
    """Simulate the synthesised netlist against the design."""
    from . import yosys
    from .sim import Sim
    ref = Sim.from_file(yosys.sim_netlist([outdir / f"{top}.v"], top, outdir / "ref_sim.json"), top)
    yosys.run_script(f"read_json {top}.json\ndelete =A:blackbox\n" + _cells(outdir)
                     + SIM_FLOW.format(top=top, out="synth_sim.json"), outdir, "gowin_check.log")
    dut = Sim.from_file(outdir / "synth_sim.json", top)
    return compare(ref, dut, steps)


# ---- reading the bitstream back ----------------------------------------------------------
# Die size (rows, columns) per Apicula family: I/O bel IOR7A is row 7 of the
# last column, and so on.
DIMS = {"GW1NZ-1": (11, 20), "GW1N-4": (20, 38), "GW1N-9C": (29, 47)}


def pad_port(pin_name: str, family: str) -> Tuple[str, str]:
    """('R7C20', 'A') for pin name 'IOR7A/...' on an 11x20 die."""
    rows, cols = DIMS[family]
    m = re.match(r"IO([LRTB])(\d+)([A-Z])", pin_name)
    if not m:
        raise ValueError(f"{pin_name} is not an I/O pin")
    side, n, ab = m.group(1), int(m.group(2)), m.group(3)
    r, c = {"T": (1, n), "B": (rows, n), "L": (n, 1), "R": (n, cols)}[side]
    return f"R{r}C{c}", ab


def check_bitstream(design, outdir: Path, top: str, family: str,
                    pins: Optional[Dict[str, int]] = None, steps: int = 600) -> Tuple[bool, str]:
    """Read the .fs back with gowin_unpack (Apicula's decoder) and simulate
    that netlist, through the pins in the .cst, against the design."""
    from . import devices, yosys
    from .sim import Sim
    _, pkg = devices.get_package(design.device, design.package)
    _run(find_tool(UNPACK) + ["-d", family, "-o", f"{top}_unpacked.v", f"{top}.fs"],
         outdir, "gowin_unpack")
    src = (outdir / f"{top}_unpacked.v").read_text(encoding="utf-8", errors="replace")
    src, clocks = _reconnect_clocks(src, outdir / f"{top}_pnr.json")
    src = _blank_luts(src)
    (outdir / f"{top}_unpacked.v").write_text(src, encoding="utf-8")
    dirs = {n: d for d, n in re.findall(r"^(input|output|inout) (\S+);", src, re.M)}
    if pins is None:
        pins = {s: int(p) for s, p in re.findall(r'IO_LOC "(\S+)" (\d+);',
                                                  (outdir / f"{top}.cst").read_text())}
    ref_json = outdir / "ref_sim.json"
    ref = Sim.from_file(ref_json if ref_json.exists() else
                        yosys.sim_netlist([outdir / f"{top}.v"], top, ref_json), top)
    conns, used = [], set()
    for port in ref.ports:
        rc, ab = pad_port(pkg.pin_names[pins[port]], family)
        k = next((k for k in (f"{rc}_IO{ab}", f"{rc}_O{ab}", f"{rc}_I{ab}") if k in dirs), None)
        if k is None:
            return False, (f"WARNING: the bitstream has no I/O for {port} at pin "
                           f"{pins[port]} ({rc}{ab})")
        conns.append(f".{k}({port})")
        used.add(k)
    conns += [f".{k}(1'b0)" for k, d in dirs.items() if d == "input" and k not in used]
    decl = "".join(f"  {p['direction']} {n};\n" for n, p in ref.ports.items())
    (outdir / f"{top}_readback.v").write_text(
        f"module readback({', '.join(ref.ports)});\n{decl}"
        f"  top u({', '.join(conns)});\nendmodule\n", encoding="utf-8")
    yosys.run_script(f"read_verilog {top}_unpacked.v\n" + _cells(outdir)
                     + f"read_verilog {top}_readback.v\n"
                     + SIM_FLOW.format(top="readback", out="readback_sim.json"),
                     outdir, "gowin_readback.log")
    dut = Sim.from_file(outdir / "readback_sim.json", "readback")
    ok, msg = compare(ref, dut, steps)
    msg = (msg.replace("Synthesised netlist", "Bitstream (read back with gowin_unpack)")
           .replace("the synthesised netlist", "the bitstream (read back with gowin_unpack)"))
    if clocks:
        msg += (f" gowin_unpack doesn't follow the global clock network, so the clock (or latch enable) pins of "
                f"{clocks} flip-flop(s)/latch(es) were connected from nextpnr's netlist.")
    return ok, msg


def _blank_luts(src: str) -> str:
    """A LUT with no fuses set is all ones (Apicula: INIT = 0xffff - fuses),
    so it outputs 1; gowin_unpack leaves its output undriven instead. nextpnr
    uses such LUTs to feed a constant 1 to a flip-flop or latch."""
    used = set(re.findall(r"\.\w+\((R\d+C\d+_F[0-7])\)", src))
    driven = set(re.findall(r"\.(?:F|O|Q|SUM|COUT)\((R\d+C\d+_F[0-7])\)", src)) | \
        set(re.findall(r"^assign (R\d+C\d+_F[0-7]) =", src, re.M))
    blank = sorted(used - driven)
    if not blank:
        return src
    extra = "".join(f"assign {w} = 1'b1;\n" for w in blank)
    i = src.rindex("endmodule")
    return src[:i] + extra + src[i:]


def _bel_wire(bel: str, port: str) -> Optional[str]:
    """The unpacked netlist's wire for a placed cell's output: IOBA -> F6,
    IOBB -> Q6, LUTn -> Fn, DFFn -> Qn (tile XxYy is RyCx, 1-based)."""
    m = re.match(r"X(\d+)Y(\d+)/(\w+?)(\d*)$", bel)
    if not m:
        return None
    x, y, kind, n = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    rc = f"R{y + 1}C{x + 1}"
    if kind == "IOB" and n == "" or kind in ("IOBA", "IOBB"):
        return f"{rc}_{'F6' if bel.endswith('A') else 'Q6'}"
    if kind == "LUT" and n:
        return f"{rc}_F{n}"
    if kind == "DFF" and n and port == "Q":
        return f"{rc}_Q{n}"
    return None


def _reconnect_clocks(src: str, pnr_json: Path) -> Tuple[str, int]:
    """Point each used flip-flop's CLK at the wire that drives its clock (an
    input pad or a LUT), found through nextpnr's netlist, since gowin_unpack
    leaves clocks on the global network undriven."""
    import json
    if not pnr_json.exists():
        return src, 0
    mod = next(iter(json.loads(pnr_json.read_text(encoding="utf-8"))["modules"].values()))
    cells = mod["cells"]
    driver = {}                                     # net bit -> (cell, port)
    for name, c in cells.items():
        for port, bits in c.get("connections", {}).items():
            if c.get("port_directions", {}).get(port) == "output":
                for b in bits:
                    driver[b] = (name, port)
    n = 0
    for name, c in cells.items():
        if not c["type"].startswith("DFF"):
            continue
        bel = c.get("attributes", {}).get("NEXTPNR_BEL", "")
        m = re.match(r"X(\d+)Y(\d+)/DFF(\d)$", bel)
        clk = c.get("connections", {}).get("CLK")
        if not m or not clk:
            continue
        bit = clk[0]
        for _ in range(4):                           # through BUFG / DQCE / DCS
            d = driver.get(bit)
            if d is None or not cells[d[0]]["type"].startswith(("BUFG", "DQCE", "DCS")):
                break
            bit = cells[d[0]]["connections"]["I" if "I" in cells[d[0]]["connections"]
                                             else "CLKIN"][0]
        d = driver.get(bit)
        wire = _bel_wire(cells[d[0]]["attributes"].get("NEXTPNR_BEL", ""), d[1]) if d else None
        if wire is None:
            continue
        inst = f"R{int(m.group(2)) + 1}C{int(m.group(1)) + 1}_(?:DFFE|DLE)_{m.group(3)}"
        src, k = re.subn(rf"(\b{inst} \(\s*\.CLK\()[^)]*\)", rf"\g<1>{wire})", src)
        n += k
    return src, n
