"""Running Yosys: generic synthesis checks, simulation netlists, and the
ATF15xx flow (Yosys -> EDIF -> Microchip fitter -> .jed)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def no_window() -> dict:
    """subprocess kwargs that stop console programs flashing a window when
    started from the windowed desktop app."""
    if sys.platform == "win32":
        return {"creationflags": 0x08000000}          # CREATE_NO_WINDOW
    return {}


def find_yosys() -> List[str]:
    """Command prefix for Yosys: $CPLDGLUE_YOSYS, yosys, or yowasp-yosys."""
    env = os.environ.get("CPLDGLUE_YOSYS")
    if env:
        return [env]
    for exe in ("yosys", "yowasp-yosys"):
        p = shutil.which(exe)
        if p:
            return [p]
    # yowasp installed in the running interpreter's environment
    scripts = Path(sys.executable).parent
    for cand in (scripts / "yowasp-yosys.exe", scripts / "yowasp-yosys",
                 scripts / "Scripts" / "yowasp-yosys.exe"):
        if cand.exists():
            return [str(cand)]
    # downloaded by the Setup dialog / `cpldglue setup yosys`
    from . import deps
    if deps.yosys_installed():
        return self_command() + ["_yosys"]
    raise RuntimeError("Yosys not found. Download it from Setup in the editor, run "
                       "`cpldglue setup yosys`, or: pip install yowasp-yosys")


def self_command() -> List[str]:
    """How to run cpldglue itself as a subprocess (packaged app or Python)."""
    if getattr(sys, "frozen", False):
        # Prefer the console tool bundled next to the windowed app.
        exe = Path(sys.executable)
        cli = exe.with_name("cpldglue.exe" if sys.platform == "win32" else "cpldglue")
        return [str(cli if cli.exists() else exe)]
    # Not `-m cpldglue`: the subprocess runs in a work folder, where the
    # package may not be importable unless it is pip-installed.
    root = str(Path(__file__).resolve().parent.parent)
    return [sys.executable, "-c",
            f"import sys; sys.path.insert(0, {root!r}); "
            f"from cpldglue.cli import main; sys.exit(main(sys.argv[1:]))"]


def run_script(script: str, cwd: Path, log_name: str = "yosys.log") -> str:
    cwd.mkdir(parents=True, exist_ok=True)
    (cwd / "script.ys").write_text(script, encoding="utf-8")
    try:
        r = subprocess.run(find_yosys() + ["-q", "-l", log_name, "-s", "script.ys"],
                           cwd=str(cwd), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, **no_window())
    except OSError as e:
        raise RuntimeError(f"could not run Yosys ({e}). Install it with: "
                           f"pip install yowasp-yosys") from None
    log = (cwd / log_name).read_text(encoding="utf-8", errors="replace") \
        if (cwd / log_name).exists() else ""
    if r.returncode != 0:
        raise RuntimeError(f"Yosys failed:\n{r.stdout}{r.stderr}\n{log[-3000:]}")
    return log


def rel(path: Path, cwd: Path) -> str:
    """A path as Yosys should see it from its working folder `cwd`.

    Relative, because the WebAssembly Yosys (yowasp) maps /tmp on Linux to a
    private folder of its own: an absolute /tmp/... path would point to the
    wrong place. Falls back to absolute across Windows drives."""
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(cwd).resolve())).as_posix()
    except ValueError:                                  # different drive
        return Path(path).resolve().as_posix()


def sim_netlist(verilog_files: List[Path], top: str, out_json: Path) -> Path:
    """Flatten to simple gates for cpldglue.sim (DFFs as $_DFFSR_PPP_)."""
    cwd = out_json.parent
    cwd.mkdir(parents=True, exist_ok=True)
    reads = "\n".join(f"read_verilog {rel(f, cwd)}" for f in verilog_files)
    script = f"""{reads}
hierarchy -top {top}
setattr -set keep 1 {top}/w:*
proc
flatten
tribuf
opt_clean
techmap
opt -fast
dfflegalize -cell $_DFFSR_PPP_ 01 -cell $_DLATCH_P_ 01
opt_clean
write_json {out_json.name}
"""
    run_script(script, cwd, out_json.stem + ".log")
    return out_json


def library_netlist(out_json: Path, verilog: Optional[Path] = None) -> Path:
    """Every chip model as a separate simulation-ready module, in one run."""
    from .chips import HDL_DIR
    out_json.parent.mkdir(parents=True, exist_ok=True)
    src = rel(verilog or HDL_DIR / "chips.v", out_json.parent)
    script = f"""read_verilog {src}
proc
tribuf
opt_clean
techmap
opt -fast
dfflegalize -cell $_DFFSR_PPP_ 01 -cell $_DLATCH_P_ 01
opt_clean
write_json {out_json.name}
"""
    run_script(script, out_json.parent, out_json.stem + ".log")
    return out_json


def check_synth(verilog: Path, top: str, workdir: Path) -> str:
    """Generic synthesis as a sanity check; returns the stat report."""
    workdir.mkdir(parents=True, exist_ok=True)
    script = f"""read_verilog {rel(verilog, workdir)}
hierarchy -check -top {top}
synth -flatten -top {top}
tee -o stat.txt stat
"""
    run_script(script, workdir, "check.log")
    return (workdir / "stat.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# ATF15xx flow, after https://github.com/hoglet67/atf15xx_yosys
# ---------------------------------------------------------------------------
# 3-state output pins use the bidirectional pad (bibuf) with its input side
# unused. The reference flow maps them to TRI, which the fitter only knows as
# an internal buffer: any design with a plain 3-state output then stops with
# "INTERNAL ERROR - Please contact your Hot-Line".
def atf_yosys_script(name: str, flow_dir: Path, cwd: Path = Path(".")) -> str:
    lib = rel(flow_dir / "cells.lib", cwd)
    tmap = rel(flow_dir / "techmap.v", cwd)
    return f"""read_liberty -lib {lib}
read_verilog {name}.v
tribuf
synth -flatten -noabc -top {name}
techmap -map {tmap} -D skip_DFFE_XX_
simplemap
dfflibmap -liberty {lib}
abc -liberty {lib}
iopadmap -bits -inpad INBUF Q:A -outpad BUF A:Q -toutpad bibuf EN:A:PAD -tinoutpad bibuf EN:Q:A:PAD
clean
hierarchy
splitnets -format _
rename -wire -suffix _reg t:*DFF*
rename -wire -suffix _comb
delete t:$scopeinfo
write_edif -lsbidx {name}.edif
"""


def fitter_tech(device: str) -> str:
    """The -tech name the fitter accepts: ATF15xxAS or ATF15xxASV. The
    low-power L parts use the same name (the fitter's help lists only AS,
    ASV and BE)."""
    from .devices import DEVICES
    dev = DEVICES.get(device.upper())
    return dev.fitter_tech if dev else device.upper()


def find_fitter(device: str, fitter_dir: Optional[Path]) -> Optional[Path]:
    exe = "fit" + "".join(c for c in device if c.isdigit()) + ".exe"
    dirs = [fitter_dir] if fitter_dir else []
    env = os.environ.get("CPLDGLUE_FITTER_DIR")
    if env:
        dirs.append(Path(env))
    from . import deps
    dirs += [Path("C:/Wincupl/WinCupl/Fitters"), Path("C:/Wincupl/Fitters"),
             Path("C:/ProChip/pldfit"), Path("C:/Microchip/ProChip/pldfit")] + deps.fitter_dirs()
    for d in dirs:
        if d and (d / exe).exists():
            return d / exe
    return None


def run_atf_flow(name: str, outdir: Path, device: str, package: str,
                 flow_dir: Path, fitter_dir: Optional[Path], speed: int = 15,
                 extra: Optional[List[str]] = None) -> str:
    """Yosys -> EDIF, then the Microchip fitter -> .jed. Returns a summary."""
    for f in ("cells.lib", "techmap.v"):
        if not (flow_dir / f).exists():
            raise RuntimeError(f"{flow_dir} has no {f}; point --flow-dir at a "
                               f"checkout of github.com/hoglet67/atf15xx_yosys")
    outdir.mkdir(parents=True, exist_ok=True)
    run_script(atf_yosys_script(name, flow_dir, outdir), outdir, "atf_yosys.log")
    fitter = find_fitter(device, fitter_dir)
    if fitter is None:
        return (f"EDIF written to {outdir / (name + '.edif')}. Fitter not found "
                f"(fit{''.join(c for c in device if c.isdigit())}.exe). Get it from Setup "
                f"(or pass --fitter-dir) to finish the .jed.")
    # The fitter reads its device database (atmel.std) from the folder it runs
    # in, not from its own; without it every design fails with "Checking
    # Extra wiring failed".
    std = fitter.parent / "atmel.std"
    if std.exists():
        shutil.copyfile(std, outdir / "atmel.std")
    cmd = [str(fitter), "-i", f"{name}.edif", "-ifmt", "edif", "-o", f"{name}.jed",
           "-lib", str(fitter.parent / "aprim.lib"), "-tech", fitter_tech(device),
           "-device", package, "-tpd", str(speed), "-preassign", "keep"]
    if sys.platform != "win32":
        cmd = ["wine"] + cmd
    cmd += extra or []
    from .devices import parse_pin_file
    pinf = outdir / f"{name}.pin"
    wanted = parse_pin_file(pinf.read_text(encoding="utf-8")) if pinf.exists() else {}
    r = subprocess.run(cmd, cwd=str(outdir), capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, **no_window())
    (outdir / "fitter.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode != 0 or not (outdir / f"{name}.jed").exists():
        tail = " ".join((r.stdout + r.stderr).split()[-12:])
        raise RuntimeError(f"fitter failed ({tail}); see {outdir / 'fitter.log'} "
                           f"and {name}.fit")
    fit = outdir / f"{name}.fit"
    placed = fitted_pins(fit.read_text(encoding="utf-8", errors="replace")) if fit.exists() else {}
    moved = {sig: (pin, placed.get(sig)) for sig, pin in wanted.items()
             if placed and placed.get(sig) != pin}
    if moved:
        raise RuntimeError("the fitter moved pins (the board would not match): " + ", ".join(
            f"{sig} {want}->{got}" for sig, (want, got) in moved.items())
            + f"; see {fit}")
    from .fitcheck import verify
    try:
        check = verify(name, outdir) or ""
    except Exception as e:                      # the check must not hide a good build
        check = f"Fitted logic not checked ({type(e).__name__}: {e})."
    return (f"JEDEC file: {outdir / (name + '.jed')}\n"
            f"Fitter report: {fit}\n"
            f"All {len(wanted)} signals are on the pins cpldglue assigned.\n" + check).rstrip()


def fitted_pins(fit_text: str) -> dict:
    """Signal -> pin from the 'Pin/Node Placement' list of a fitter report."""
    import re
    out = {}
    for m in re.finditer(r"^Pin\s+(\d+)\s*=\s*([A-Za-z_]\w*)\s*;", fit_text, re.M):
        out[m.group(2)] = int(m.group(1))
    return out
