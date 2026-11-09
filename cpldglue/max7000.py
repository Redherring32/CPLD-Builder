"""Altera/Intel MAX 7000S target (EPM7032S, EPM7064S, EPM7128S).

The MAX 7000S parts are pin-compatible with the ATF1502AS/1504AS/1508AS
(same dedicated inputs, JTAG and power pins; checked against the pin-out
diagrams in Altera's MAX 7000 data sheet), so they share those pin tables.

Build writes a Quartus project (NAME.qpf/.qsf with the device and every pin
assignment, and the Verilog). If Quartus II 13.0 SP1 - the last version that
supports MAX 7000S - is installed, it also compiles it to NAME.pof (for a
USB-Blaster) and converts that to NAME.svf (for other JTAG programmers).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# device -> package -> Quartus part number (speed grade -10)
PARTS = {
    "EPM7032S": {"PLCC44": "EPM7032SLC44-10", "TQFP44": "EPM7032STC44-10"},
    "EPM7064S": {"PLCC44": "EPM7064SLC44-10", "TQFP44": "EPM7064STC44-10",
                 "PLCC84": "EPM7064SLC84-10"},
    "EPM7128S": {"PLCC84": "EPM7128SLC84-10"},
}

QUARTUS_DIRS = [
    Path("C:/altera/13.0sp1/quartus"), Path("C:/altera/13.0/quartus"),
    Path("C:/intelFPGA/13.0sp1/quartus"), Path.home() / "altera/13.0sp1/quartus",
    Path("/opt/altera/13.0sp1/quartus"), Path("/opt/altera/13.0/quartus"),
]


def find_quartus() -> Optional[Path]:
    """The folder with quartus_sh: $QUARTUS_ROOTDIR, PATH, or the usual installs."""
    names = ("quartus_sh.exe", "quartus_sh")
    env = os.environ.get("QUARTUS_ROOTDIR")
    roots = ([Path(env)] if env else []) + QUARTUS_DIRS
    for root in roots:
        for sub in ("bin64", "bin", ""):
            for n in names:
                if (root / sub / n).exists():
                    return root / sub
    p = shutil.which("quartus_sh")
    return Path(p).parent if p else None


def qsf_text(design, top: str, pins) -> str:
    part = PARTS[design.device.upper()][design.package.upper()]
    lines = [f"# Quartus II settings for {design.name}, written by cpldglue",
             'set_global_assignment -name FAMILY "MAX7000S"',
             f"set_global_assignment -name DEVICE {part}",
             f"set_global_assignment -name TOP_LEVEL_ENTITY {top}",
             f"set_global_assignment -name VERILOG_FILE {top}.v",
             'set_global_assignment -name RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"',
             # JTAG pins stay JTAG unless the design freed them (--no-jtag)
             "set_global_assignment -name MAX7000_ENABLE_JTAG_BST_SUPPORT "
             + ("ON" if design.keep_jtag else "OFF")]
    for sig, pin in sorted(pins.items(), key=lambda kv: kv[1]):
        lines.append(f"set_location_assignment PIN_{pin} -to {sig}")
    return "\n".join(lines) + "\n"


def qpf_text(top: str) -> str:
    return (f'QUARTUS_VERSION = "13.0"\nPROJECT_REVISION = "{top}"\n')


def _run(cmd: List[str], cwd: Path, what: str) -> str:
    from .yosys import no_window
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, **no_window())
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed:\n{out[-4000:]}")
    return out


def build(design, r, outdir: Path, top: str) -> dict:
    from .generate import sanitize
    if design.device.upper() not in PARTS or design.package.upper() not in PARTS[design.device.upper()]:
        raise ValueError(f"no Quartus part for {design.device} {design.package}")
    outdir.mkdir(parents=True, exist_ok=True)
    verilog = r.verilog.replace(f"module {sanitize(design.name)} (", f"module {top} (", 1)
    (outdir / f"{top}.v").write_text(verilog, encoding="utf-8")
    (outdir / f"{top}.qsf").write_text(qsf_text(design, top, r.pins), encoding="utf-8")
    (outdir / f"{top}.qpf").write_text(qpf_text(top), encoding="utf-8")
    log = [f"Wrote the Quartus project {top}.qpf / {top}.qsf and {top}.v in {outdir}"]
    q = find_quartus()
    if q is None:
        log.append("Quartus II 13.0 SP1 isn't installed, so it wasn't compiled. Open the "
                   "project in Quartus (or install it and build again) to make the .pof.")
        return {"ok": False, "log": "\n".join(log), "project_only": True}
    exe = lambda n: str(q / (n + (".exe" if sys.platform == "win32" else "")))
    out = _run([exe("quartus_sh"), "--flow", "compile", top], outdir, "Quartus compile")
    pof = outdir / f"{top}.pof"
    if not pof.exists():
        found = list(outdir.rglob(f"{top}.pof"))
        pof = found[0] if found else pof
    log.append("Compiled with Quartus" + (f": {pof.name}" if pof.exists() else " (no .pof?)"))
    for line in out.splitlines():
        if "Total macrocells" in line or "Total pins" in line:
            log.append("  " + line.strip(" ;"))
    if pof.exists():
        try:
            _run([exe("quartus_cpf"), "-c", "-q", "10MHz", "-g", "3.3", "-n", "p",
                  str(pof), f"{top}.svf"], outdir, "quartus_cpf")
            log.append(f"Converted to {top}.svf for other JTAG programmers")
        except (RuntimeError, OSError) as e:
            log.append(f"(no .svf: {e})")
    return {"ok": pof.exists(), "log": "\n".join(log)}
