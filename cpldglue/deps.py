"""Optional tools: find them, or download them when the user asks.

Everything goes in a per-user folder (data_dir()), never next to the app:

  yosys/          Yosys as WebAssembly (the yowasp-yosys wheel and the small
                  runtime it needs), pinned versions, SHA-256 checked
  atf15xx_yosys/  cells.lib + techmap.v from hoglet67/atf15xx_yosys, pinned
                  commit, SHA-256 checked
  prochip/        Microchip's ProChip download, unpacked; its installer is
                  then opened for the user to run (it shows Microchip's
                  licence, and puts the fitters in C:\\ATMEL_PLS_Tools)

KiCad is too big to fetch this way; status() just reports whether it's
installed and where to get it.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


def data_dir() -> Path:
    env = os.environ.get("CPLDGLUE_HOME")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "cpldglue"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "cpldglue"


@dataclass(frozen=True)
class Download:
    url: str
    sha256: str
    size: int
    filename: str


_PY = "https://files.pythonhosted.org/packages"
YOSYS_WHEELS = [
    Download(f"{_PY}/eb/0d/baff1eec0c9e25afbde50e6cdc4c5d748fea04828faa4655e67cc281625a/"
             "yowasp_yosys-0.70.0.0.post1259-py3-none-any.whl",
             "38a5ce6af95045b5b1ad795de7a73cfe88cf70c19f7b95f027f4a377a85310c0", 16636403,
             "yowasp_yosys-0.70.0.0.post1259-py3-none-any.whl"),
    Download(f"{_PY}/92/e2/4dd5c8392a3f085f5ba81b5a4ac5f59923a0c3b36a35351975d8d7de19c9/"
             "yowasp_runtime-1.96-py3-none-any.whl",
             "4ff456a4a6dff9d689c7feac9f68fb1492bed4cf873450d7b41259fa31645783", 5212,
             "yowasp_runtime-1.96-py3-none-any.whl"),
    Download(f"{_PY}/40/4b/2028861e724d3bd36227adfa20d3fd24c3fc6d52032f4a93c133be5d17ce/"
             "platformdirs-4.4.0-py3-none-any.whl",
             "abd01743f24e5287cd7a5db3752faf1a2d65353f38ec26d98e25a6db65958c85", 18654,
             "platformdirs-4.4.0-py3-none-any.whl"),
]
WASMTIME = {
    "win32-amd64": Download(
        f"{_PY}/90/e4/8603bd4a360edbe5178efe4e7b48f1677749a96a3caa3fc68ab23b0de62c/"
        "wasmtime-47.0.1-py3-none-win_amd64.whl",
        "4e46a4a29092a2ac1001159d5673e2a23996f4474261c791401867b1630429f4", 8069924,
        "wasmtime-47.0.1-py3-none-win_amd64.whl"),
    "linux-x86_64": Download(
        f"{_PY}/5e/ba/f321faaad1d616b94fe70a62ebb7e4054cfe41a6a46aa796ad2bb07fa08c/"
        "wasmtime-47.0.1-py3-none-manylinux1_x86_64.whl",
        "9724600b036c6e95c4fe952e29fad83b4f02bdc11d23f25c4ee3ffff2c1d7257", 9963365,
        "wasmtime-47.0.1-py3-none-manylinux1_x86_64.whl"),
    "linux-aarch64": Download(
        f"{_PY}/d7/93/f12469c859fed8332961c4efa68c1f1981542b9ce95248b617255938a55d/"
        "wasmtime-47.0.1-py3-none-manylinux2014_aarch64.whl",
        "4f72162ceed1d50de8226fac6b12e1ecce54883a0c3f7355bb141eae40df488a", 8822179,
        "wasmtime-47.0.1-py3-none-manylinux2014_aarch64.whl"),
}

FLOW_COMMIT = "936d58e94b12f36b5ba2a565ffcf4a18136fd8e2"
FLOW_ZIP = f"https://codeload.github.com/hoglet67/atf15xx_yosys/zip/{FLOW_COMMIT}"
FLOW_FILES = {      # name -> sha256 at FLOW_COMMIT
    "cells.lib": "f10b8a31ff3c76aef58ac852723eebd9e24179bbcc18cc32939fd7f52502ce44",
    "techmap.v": "330fcd736b54630f976b82d49316df55bfd7fcea1439f86d5f4940c80343e45e",
    "README.txt": "d206c3303737984c7d590e37c9708aa363dd27d7547ad5fecbd452f0b83d79f3",
}

PROCHIP = Download("http://ww1.microchip.com/downloads/en/DeviceDoc/ProChip5.0.1.zip",
                   "ffdfc6ed6a05461ad6df34b6088fc8b6d31ef298b20adb3211dbb180b7b714aa", 223730759, "ProChip5.0.1.zip")
PROCHIP_INSTALL_DIRS = [Path("C:/ATMEL_PLS_Tools/Prochip/pldfit"),
                        Path.home() / ".wine/drive_c/ATMEL_PLS_Tools/Prochip/pldfit"]

KICAD_URL = "https://www.kicad.org/download/"


def platform_key() -> str:
    m = platform.machine().lower()
    if sys.platform == "win32":
        return "win32-amd64" if m in ("amd64", "x86_64") else f"win32-{m}"
    m = {"amd64": "x86_64", "arm64": "aarch64"}.get(m, m)
    return f"{sys.platform}-{m}"


# ---- locations ---------------------------------------------------------------
def yosys_dir() -> Path:
    return data_dir() / "yosys"


def flow_dir() -> Optional[Path]:
    """The atf15xx_yosys files: $CPLDGLUE_FLOW_DIR, or the downloaded copy."""
    for d in (os.environ.get("CPLDGLUE_FLOW_DIR"), data_dir() / "atf15xx_yosys"):
        if d and (Path(d) / "cells.lib").exists() and (Path(d) / "techmap.v").exists():
            return Path(d)
    return None


def fitter_dirs() -> List[Path]:
    return list(PROCHIP_INSTALL_DIRS)


def yosys_installed() -> bool:
    return (yosys_dir() / "yowasp_yosys" / "__init__.py").exists() and \
        (yosys_dir() / "wasmtime").is_dir()


def run_yosys(argv: List[str]) -> int:
    """Run the downloaded Yosys in this process (used by `cpldglue _yosys`)."""
    sys.path.insert(0, str(yosys_dir()))
    import yowasp_yosys          # noqa: E402  (from the download folder)
    return yowasp_yosys.run_yosys(argv)


# ---- remembered settings --------------------------------------------------------
def _settings_file() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(_settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remember_project(path: Path) -> None:
    s = load_settings()
    p = str(Path(path).resolve())
    s["recent"] = [p] + [x for x in s.get("recent", []) if x != p][:7]
    try:
        _settings_file().parent.mkdir(parents=True, exist_ok=True)
        _settings_file().write_text(json.dumps(s, indent=1), encoding="utf-8")
    except OSError:
        pass


def recent_projects() -> List[str]:
    return [p for p in load_settings().get("recent", []) if Path(p).exists()]


# ---- downloading -------------------------------------------------------------
Progress = Callable[[int, Optional[int], str], None]     # done, total, message


def download(d: Download, dest_dir: Path, progress: Progress, label: str = "") -> Path:
    """Download d into dest_dir (resuming nothing; cached if already good)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / d.filename
    if out.exists() and _sha256(out) == d.sha256:
        return out
    part = out.with_suffix(out.suffix + ".part")
    h = hashlib.sha256()
    done = 0
    req = urllib.request.Request(d.url, headers={"User-Agent": "cpldglue"})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or d.size or 0) or None
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            progress(done, total, label or f"Downloading {d.filename}")
    if h.hexdigest() != d.sha256:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{d.filename}: checksum mismatch (got {h.hexdigest()}); "
                           f"the download was corrupted or the file changed upstream")
    part.replace(out)
    return out


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_yosys(progress: Progress) -> str:
    key = platform_key()
    if key not in WASMTIME:
        raise RuntimeError(f"no prebuilt WebAssembly runtime for {key}; install a "
                           f"native Yosys instead (e.g. from your package manager)")
    wheels = YOSYS_WHEELS + [WASMTIME[key]]
    total = sum(w.size for w in wheels)
    base = 0
    cache = data_dir() / "downloads"
    files = []
    for w in wheels:
        files.append(download(w, cache, lambda d, t, m, b=base: progress(b + d, total, m)))
        base += w.size
    tmp = data_dir() / "yosys.new"
    shutil.rmtree(tmp, ignore_errors=True)
    for f in files:
        progress(total, total, f"Unpacking {f.name}")
        with zipfile.ZipFile(f) as z:
            z.extractall(tmp)
    (tmp / "cpldglue-installed.json").write_text(
        json.dumps({"wheels": [w.filename for w in wheels]}, indent=1), encoding="utf-8")
    shutil.rmtree(yosys_dir(), ignore_errors=True)
    tmp.replace(yosys_dir())
    for f in files:                       # the unpacked copy is all we need
        f.unlink(missing_ok=True)
    return ("Yosys installed. The first simulation compiles it, which takes a "
            "minute or so; after that it starts in a second or two.")


def fetch_flow(progress: Progress) -> str:
    progress(0, None, "Downloading atf15xx_yosys")
    req = urllib.request.Request(FLOW_ZIP, headers={"User-Agent": "cpldglue"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    progress(len(data), len(data), "Unpacking")
    import io
    out = data_dir() / "atf15xx_yosys"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name, sha in FLOW_FILES.items():
            member = f"atf15xx_yosys-{FLOW_COMMIT}/{name}"
            body = z.read(member)
            if hashlib.sha256(body).hexdigest() != sha:
                raise RuntimeError(f"{name}: checksum mismatch")
            (out / name).write_bytes(body)
    return f"atf15xx_yosys files saved to {out}"


def prochip_setup() -> Optional[Path]:
    root = data_dir() / "prochip"
    hits = sorted(root.rglob("*etup*.exe")) if root.is_dir() else []
    return hits[0] if hits else None


def fetch_fitter(progress: Progress, launch: bool = True) -> str:
    if sys.platform != "win32" and not shutil.which("wine"):
        raise RuntimeError("The Microchip fitter is a Windows program; install Wine "
                           "first (e.g. sudo apt install wine), then try again.")
    z = download(PROCHIP, data_dir() / "downloads", progress, "Downloading ProChip (224 MB)")
    progress(PROCHIP.size, PROCHIP.size, "Unpacking")
    root = data_dir() / "prochip"
    shutil.rmtree(root, ignore_errors=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(root)
    z.unlink(missing_ok=True)
    setup = prochip_setup()
    if setup is None:
        raise RuntimeError(f"no installer found in {root}")
    if launch:
        open_installer(setup)
    return (f"The ProChip installer is open. Install with the default folder; the "
            f"fitters end up in {PROCHIP_INSTALL_DIRS[0 if sys.platform == 'win32' else 1]}. "
            f"(Installer: {setup})")


def open_installer(setup: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(setup))             # type: ignore[attr-defined]
    else:
        subprocess.Popen(["wine", str(setup)], cwd=str(setup.parent))


FETCHERS = {"yosys": fetch_yosys, "flow": fetch_flow, "fitter": fetch_fitter}


# ---- status ------------------------------------------------------------------
def status() -> List[dict]:
    from . import yosys as ys
    from .design import find_kicad_cli
    out = []
    try:
        ycmd = ys.find_yosys()
        where = (f"{yosys_dir()} (downloaded)" if ycmd[-1] == "_yosys"
                 else " ".join(ycmd))
    except RuntimeError:
        where = None
    out.append({"id": "yosys", "title": "Yosys", "found": where is not None, "where": where,
                "needed_for": "Simulate tab, synthesis check, Build",
                "download": "about 25 MB from PyPI (yowasp-yosys, runs as WebAssembly)",
                "can_fetch": platform_key() in WASMTIME})
    fd = flow_dir()
    out.append({"id": "flow", "title": "ATF15xx Yosys flow files", "found": fd is not None,
                "where": str(fd) if fd else None, "needed_for": "Build (.jed)",
                "download": "about 30 KB from GitHub (hoglet67/atf15xx_yosys)",
                "can_fetch": True})
    fitters = {n: ys.find_fitter(n, None) for n in ("ATF1502AS", "ATF1504AS", "ATF1508AS")}
    found = [str(p) for p in fitters.values() if p]
    out.append({"id": "fitter", "title": "Microchip fitters (fit1502/1504/1508)",
                "found": bool(found), "where": str(Path(found[0]).parent) if found else None,
                "needed_for": "Build (.jed)",
                "download": "224 MB from microchip.com (ProChip 5.0.1); you then run "
                            "Microchip's installer and accept its licence"
                            + ("" if sys.platform == "win32" else "; needs Wine"),
                "can_fetch": sys.platform == "win32" or bool(shutil.which("wine")),
                "installer": str(prochip_setup()) if prochip_setup() else None})
    k = find_kicad_cli()
    out.append({"id": "kicad", "title": "KiCad (kicad-cli)", "found": bool(k), "where": k,
                "needed_for": "Import KiCad…", "download": f"install from {KICAD_URL}",
                "can_fetch": False, "url": KICAD_URL})
    return out


class Jobs:
    """Background downloads for the GUI, one per dependency."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: Dict[str, dict] = {}

    def start(self, dep: str) -> dict:
        if dep not in FETCHERS:
            raise ValueError(f"unknown dependency {dep!r}")
        with self.lock:
            j = self.jobs.get(dep)
            if j and j["state"] == "running":
                return j
            j = self.jobs[dep] = {"state": "running", "done": 0, "total": None,
                                  "message": "Starting…"}

        def progress(done, total, msg):
            j.update(done=done, total=total, message=msg)

        def run():
            try:
                j.update(state="done", message=FETCHERS[dep](progress))
            except Exception as e:                       # report it in the dialog
                j.update(state="error", message=f"{type(e).__name__}: {e}")

        threading.Thread(target=run, daemon=True).start()
        return j

    def snapshot(self) -> Dict[str, dict]:
        with self.lock:
            return {k: dict(v) for k, v in self.jobs.items()}
