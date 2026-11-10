"""GUI API as plain functions (the HTTP server is a thin wrapper).

Everything returns JSON-ready dicts so it can be unit-tested without a
server or a browser.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from .. import chips, devices, generate
from ..design import Design, load, save as save_design
from ..units import UNITS


def _identifier(stem: str) -> str:
    return generate.sanitize(stem) or "glue"


def parts_payload() -> dict:
    out = []
    for p in chips.LIBRARY.values():
        out.append({
            "key": p.key, "title": p.title, "package": p.package,
            "warning": p.warning,
            "units": [u.to_json() for u in UNITS[p.key]],
            "pins": [{"number": pin.number, "name": pin.name, "kind": pin.kind}
                     for pin in sorted(p.pins.values(), key=lambda x: int(x.number))],
        })
    return {"parts": out}


def devices_payload() -> dict:
    out = []
    for dev in devices.DEVICES.values():
        for pkg in dev.packages.values():
            out.append({
                "device": dev.name, "package": pkg.name, "macrocells": dev.macrocells,
                "io": pkg.io, "inputs": pkg.inputs, "jtag": pkg.jtag,
                "power": {str(k): v for k, v in pkg.power.items()},
                "pin_count": pkg.pin_count,
                "nc": pkg.nc, "vcc": dev.vcc,
                "kind": dev.kind, "resources": dev.resources, "supply": dev.supply,
                "note": dev.note, "out_only": pkg.out_only, "no_oe": pkg.no_oe,
                "reserved": pkg.reserved,
                "pin_names": {str(k): v for k, v in pkg.pin_names.items()},
                "style": pkg.style, "sides": list(pkg.sides) if pkg.sides else None,
            })
    return {"devices": out}


def capacity(design: Design) -> Optional[int]:
    try:
        _, pkg = devices.get_package(design.device, design.package)
    except ValueError:
        return None
    jtag = len(pkg.jtag) if design.keep_jtag else 0
    return len(pkg.io) - jtag + len(pkg.inputs)


def generate_payload(design: Design) -> dict:
    """Run the generator and describe the result for the GUI."""
    r = generate.generate(design)
    port_of_net = {p.net: p for p in r.ports}
    nets = {}
    for name, net in design.nets.items():
        port = port_of_net.get(name)
        nets[name] = {
            "external": net.external,
            "const": net.const,
            "port": port.name if port else None,
            "direction": port.direction if port else None,
            "pin": r.pins.get(port.name) if port else None,
        }
    return {
        "ok": r.ok,
        "ports": [{"name": p.name, "direction": p.direction, "net": p.net, "drive": p.drive,
                   "pin": r.pins.get(p.name)} for p in r.ports],
        "capacity": capacity(design),
        "macrocells": None if r.macrocells is None else {
            "outputs": r.macrocells[0], "storage": r.macrocells[1],
            "shared": r.macrocells_shared, "estimate": r.macrocell_estimate,
            "total": r.macrocells[2],
            "parts": {ref: {"outputs": o, "storage": st, "shared": sh,
                            "estimate": round(o + st - sh, 3)}
                      for ref, (o, st, sh) in r.macrocell_parts.items()}},
        "nets": nets,
        "unused": r.unused,
        "errors": r.errors,
        "warnings": r.warnings,
        "notes": r.notes,
        "verilog": r.verilog,
        "pin_file": r.pin_file(design) if r.verilog else "",
        "report": r.report(design),
    }


class KiCadImporter:
    """Reads KiCad schematics for the import dialog. The netlist export
    (kicad-cli, a second or two) is cached per file and modification time."""

    def __init__(self):
        self._cache: dict = {}

    def _netlist(self, path: Path):
        import tempfile
        from .. import design as dsg
        p = Path(path).expanduser()
        if not p.is_file():
            raise ValueError(f"no such file: {p}")
        key = (str(p.resolve()), p.stat().st_mtime)
        if key not in self._cache:
            if p.suffix == ".kicad_sch":
                with tempfile.TemporaryDirectory() as tmp:
                    net = Path(tmp) / "export.net"
                    dsg.export_kicad_netlist(p, net)
                    self._cache[key] = dsg.read_kicad_netlist(net)
            elif p.suffix == ".net":
                self._cache[key] = dsg.read_kicad_netlist(p)
            else:
                raise ValueError("pick a .kicad_sch schematic or a KiCad .net netlist")
        return p, self._cache[key]

    def components(self, path) -> dict:
        p, (comps, nets) = self._netlist(Path(path))
        groups = alternatives(comps, nets)
        group_of = {ref: g for g in groups for ref in g["refs"]}
        rows = []
        for ref, value in sorted(comps.items(), key=lambda kv: _natural(kv[0])):
            part = chips.lookup(value)
            g = group_of.get(ref)
            rows.append({"ref": ref, "value": value, "part": part.key if part else None,
                         "alternatives": [r for r in g["refs"] if r != ref] if g else []})
        return {"path": str(p), "components": rows, "alternatives": groups}

    def design(self, path, refs, overrides=None, base: Optional[Design] = None,
               variants: Optional[dict] = None) -> Design:
        from .. import design as dsg
        p, (comps, knets) = self._netlist(Path(path))
        d = dsg.design_from_netlist(comps, knets, refs, "glue", overrides or {})
        if base is not None:
            d.name, d.device, d.package = base.name, base.device, base.package
            d.keep_jtag = base.keep_jtag
        if variants:                   # "keep as variants" in the import dialog
            d.variants = {k: list(v) for k, v in variants.items()}
            d.variant_mode = base.variant_mode if base is not None and base.variants else "build"
            d.variant = next(iter(d.variants))
        return d

    def preview(self, path, refs, overrides=None, base: Optional[Design] = None,
                variants: Optional[dict] = None) -> dict:
        d = self.design(path, refs, overrides, base, variants)
        r = generate.generate(d)
        errors = list(r.errors)
        _, (comps, nets) = self._netlist(Path(path))
        chosen = set(refs)
        kept = {r for refs_ in (variants or {}).values() for r in refs_}
        for g in alternatives(comps, nets, overrides):
            both = [x for x in g["refs"] if x in chosen and x not in kept]
            if len(both) > 1:
                errors.insert(0, f"{_join(both)} drive the same nets ({_join(g['nets'][:3])}"
                                 f"{', …' if len(g['nets']) > 3 else ''}): they look like "
                                 f"alternative parts for one place on the board. Tick only "
                                 f"the one you fit.")
        return {"pins": len(r.ports), "capacity": capacity(d), "errors": errors,
                "warnings": r.warnings, "design": _design_dict(d)}


def _join(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def alternatives(comps: dict, nets: dict, overrides: Optional[dict] = None) -> list:
    """Groups of chips whose outputs drive the same nets. Two push-pull
    outputs on one net can't both be fitted, so on a real board these are
    alternatives for one position ("populate U4A *or* U4B")."""
    overrides = overrides or {}
    kind_of = {}
    for ref, value in comps.items():
        part = chips.LIBRARY.get(overrides.get(ref, "")) or chips.lookup(value)
        if part:
            kind_of[ref] = {n: pin.kind for n, pin in part.pins.items()}
    parent = {ref: ref for ref in kind_of}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    shared: Dict[frozenset, list] = {}
    for name, nodes in nets.items():
        drivers = [(n.ref, kind_of[n.ref].get(n.pin)) for n in nodes if n.ref in kind_of]
        push = {ref for ref, k in drivers if k == "o"}
        others = {ref for ref, k in drivers if k in ("o", "t", "oc", "b")}
        if push and len(others) > 1:
            refs = sorted(others, key=_natural)
            for r in refs[1:]:
                parent[find(r)] = find(refs[0])
            shared.setdefault(frozenset(refs), []).append(name)
    out: Dict[str, dict] = {}
    for refs, names in shared.items():
        root = find(next(iter(refs)))
        g = out.setdefault(root, {"refs": set(), "nets": []})
        g["refs"] |= refs
        g["nets"] += [n.lstrip("/") for n in names]
    return [{"refs": sorted(g["refs"], key=_natural), "nets": sorted(set(g["nets"]), key=_natural)}
            for g in out.values()]


def _natural(s: str):
    import re
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


KICAD_EXTS = (".kicad_sch", ".net")


def list_dir(path: str, start: Path, exts=KICAD_EXTS) -> dict:
    """One folder for the in-app file browser: its subfolders and the files
    with the given extensions (hidden entries and KiCad backups left out).
    An empty or missing path starts at `start`; a file path opens its folder."""
    p = Path(path.strip().strip('"')).expanduser() if path and path.strip() else start
    if p.is_file():
        p = p.parent
    while not p.is_dir() and p != p.parent:   # a mistyped path: nearest real folder
        p = p.parent
    p = p.resolve()
    dirs, files = [], []
    try:
        entries = sorted(p.iterdir(), key=lambda e: e.name.lower())
    except OSError as e:
        raise ValueError(f"can't read {p}: {e.strerror or e}") from None
    for e in entries:
        if e.name.startswith((".", "$")) or "backup" in e.name.lower() or "_autosave" in e.name:
            continue
        try:
            if e.is_dir():
                dirs.append(e.name)
            elif e.suffix.lower() in exts:
                files.append(e.name)
        except OSError:
            continue
    roots = []
    if os.name == "nt":
        import string
        roots = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        roots = ["/", str(Path.home())]
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else None,
            "dirs": dirs, "files": files, "roots": roots, "sep": os.sep}


def find_schematics(start: Path, limit: int = 40) -> list:
    """KiCad schematics near the project: its folder, then up to two parent
    folders, searching a few levels down. Skips backup folders."""
    seen, out = set(), []
    bases = [start] + list(start.parents)[:2]
    for base in bases:
        if not base.is_dir():
            continue
        for depth in range(0, 4):
            pattern = "/".join(["*"] * depth + ["*.kicad_sch"])
            for f in base.glob(pattern):
                s = str(f.resolve())
                if s in seen or "backup" in s.lower() or "_autosave" in f.name:
                    continue
                seen.add(s)
                out.append(s)
                if len(out) >= limit:
                    break
    # Most recently edited first: that's usually the board being worked on.
    def mtime(f):
        try:
            return os.path.getmtime(f)
        except OSError:
            return 0
    return sorted(out, key=mtime, reverse=True)[:limit]


class Builder:
    """Runs the ATF15xx flow for the Build button."""

    def __init__(self, flow_dir: Optional[Path], fitter_dir: Optional[Path]):
        self._flow_dir = Path(flow_dir) if flow_dir else None
        self.fitter_dir = Path(fitter_dir) if fitter_dir else None

    @property
    def flow_dir(self) -> Optional[Path]:
        """--flow-dir if given, else the copy downloaded from Setup (checked
        each time, so a download takes effect without a restart)."""
        from .. import deps
        return self._flow_dir or deps.flow_dir()

    def config(self, design: Optional[Design] = None) -> dict:
        from .. import yosys
        fitter = None
        if design is not None:
            f = yosys.find_fitter(design.device, self.fitter_dir)
            fitter = str(f) if f else None
        flow_ok = bool(self.flow_dir and (self.flow_dir / "cells.lib").exists()
                       and (self.flow_dir / "techmap.v").exists())
        from .. import ice40, max7000
        q = max7000.find_quartus()
        return {"flow_dir": str(self.flow_dir) if self.flow_dir else None,
                "flow_ok": flow_ok, "fitter": fitter,
                "nextpnr": ice40.tools_found(), "quartus": str(q) if q else None,
                "enabled": True}       # always shown; the dialog says what's missing

    def build(self, design: Design, outdir: Path) -> dict:
        """Build the design; in variant build mode, one .jed per variant (each
        in its own subfolder, all with the same pins)."""
        if design.variants and design.variant_mode != "pins":
            logs, oks = [], []
            for v in design.variants:
                dv = Design.from_json(design.to_json())
                dv.variant = v
                res = self._build_one(dv, outdir / generate.sanitize(v), f"_{generate.sanitize(v)}")
                logs.append(f"=== variant {v} ===\n{res['log']}")
                oks.append(res["ok"])
            return {"ok": all(oks), "log": "\n\n".join(logs), "outdir": str(outdir)}
        return self._build_one(design, outdir)

    def _build_one(self, design: Design, outdir: Path, suffix: str = "") -> dict:
        from .. import yosys
        r = generate.generate(design)
        if not r.ok:
            return {"ok": False, "log": "Fix the report errors first:\n" + "\n".join(r.errors)}
        top = generate.sanitize(design.name) + suffix
        outdir.mkdir(parents=True, exist_ok=True)
        dev = devices.DEVICES.get(design.device.upper())
        if dev is not None and dev.kind == "gal":
            return self._build_gal(design, r, outdir, top)
        if dev is not None and dev.kind == "ice40":
            from .. import ice40
            try:
                res = ice40.build(design, r, outdir, top)
            except (RuntimeError, ValueError) as e:
                return {"ok": False, "log": str(e), "outdir": str(outdir)}
            return {**res, "outdir": str(outdir)}
        if dev is not None and dev.kind == "max7000":
            from .. import max7000
            try:
                res = max7000.build(design, r, outdir, top)
            except (RuntimeError, ValueError) as e:
                return {"ok": False, "log": str(e), "outdir": str(outdir)}
            return {**res, "outdir": str(outdir)}
        verilog = r.verilog.replace(f"module {generate.sanitize(design.name)} (",
                                    f"module {top} (", 1)
        (outdir / f"{top}.v").write_text(verilog, encoding="utf-8")
        (outdir / f"{top}.pin").write_text(r.pin_file(design), encoding="utf-8")
        log = [f"Wrote {outdir / (top + '.v')} and {top}.pin"]
        if self.flow_dir is None:
            return {"ok": False, "log": "\n".join(log + [
                "The atf15xx_yosys files are missing: download them from Setup."])}
        try:
            log.append(yosys.run_atf_flow(top, outdir, design.device, design.package,
                                          self.flow_dir, self.fitter_dir))
            ok = (outdir / f"{top}.jed").exists()
        except RuntimeError as e:
            log.append(str(e))
            ok = False
        return {"ok": ok, "log": "\n".join(log), "outdir": str(outdir)}


    def _build_gal(self, design: Design, r, outdir: Path, top: str) -> dict:
        from .. import gal
        try:
            b = gal.build(design, r, outdir / "gal-work")
        except (RuntimeError, ValueError) as e:
            return {"ok": False, "log": str(e)}
        log = gal.report_lines(b, design.device)
        if b.fit.ok:
            files = gal.write_files(b, design, outdir, top)
            (outdir / f"{top}.v").write_text(r.verilog, encoding="utf-8")
            log.append("Wrote " + ", ".join(f.name for f in files) + f" and {top}.v in {outdir}")
        return {"ok": b.ok, "log": "\n".join(log), "outdir": str(outdir)}


class SimSession:
    """One live simulation of the design. Rebuilt (via Yosys) only when the
    generated Verilog changes; register state survives other edits."""

    def __init__(self):
        import threading
        self.lock = threading.Lock()
        self.key = ""
        self.sim = None
        self.ports: list = []
        self.net_values: dict = {}
        self.workdir: Optional[Path] = None

    def build(self, design: Design, fresh: bool = False) -> dict:
        import hashlib
        import tempfile
        from .. import yosys
        from ..sim import Sim
        r = generate.generate(design, assign=False)
        if not r.verilog:
            return {"ok": False, "error": "; ".join(r.errors) or "nothing to simulate"}
        # Ignore the date stamp so identical logic reuses the simulation.
        body = r.verilog.split("\n", 1)[1]
        key = hashlib.sha256(body.encode()).hexdigest()
        with self.lock:
            if fresh or key != self.key or self.sim is None:
                if self.workdir is None:
                    self.workdir = Path(tempfile.mkdtemp(prefix="cpldglue_sim_"))
                top = generate.sanitize(design.name)
                v = self.workdir / f"{top}.v"
                v.write_text(r.verilog, encoding="utf-8")
                try:
                    j = yosys.sim_netlist([v], top, self.workdir / f"{top}.json")
                    self.sim = Sim.from_file(j, top)
                except (RuntimeError, ValueError) as e:
                    self.sim, self.key = None, ""
                    return {"ok": False, "error": str(e).splitlines()[0][:300]}
                self.key = key
            self.ports = [{"name": p.name, "direction": p.direction, "net": p.net}
                          for p in r.ports]
            self.net_values = r.net_values
            return {"ok": True, "ports": self.ports, **self._state()}

    def step(self, steps: list) -> dict:
        with self.lock:
            if self.sim is None:
                return {"ok": False, "error": "simulation not built"}
            known = {p["name"] for p in self.ports if p["direction"] != "output"}
            trace = []          # every port's value after each step (for waveforms)
            for values in steps:
                vals = {k: (None if v is None else int(v)) for k, v in values.items()
                        if k in known}
                if vals:
                    self.sim.set(**vals)
                self.sim.step()
                trace.append({p["name"]: self.sim.get(p["name"]) for p in self.ports})
            return {"ok": True, "trace": trace, **self._state()}

    def _state(self) -> dict:
        s = self.sim
        ports = {p["name"]: s.get(p["name"]) for p in self.ports}
        nets = {}
        for net, expr in self.net_values.items():
            if expr in ("1'b0", "1'b1"):
                nets[net] = int(expr[-1])
            elif expr in s.ports:
                nets[net] = s.get(expr)
            else:
                nets[net] = s.get_wire(expr)
        return {"values": ports, "nets": nets,
                "contention": bool(s.contention)}


class Project:
    """The project file the GUI has open. Reloads when the file changes."""

    def __init__(self, path):
        self.path = Path(path)
        self.mtime = 0.0
        self.design = Design()
        self.error = ""
        self.reload()

    def reload(self) -> None:
        if not self.path.exists():           # new project: start empty
            self.mtime = 0.0
            self.design = Design(name=_identifier(self.path.stem))
            self.error = ""
            return
        try:
            self.mtime = self.path.stat().st_mtime
            self.design = load(self.path)
            self.error = ""
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.error = f"{type(e).__name__}: {e}"

    def open(self, path) -> None:
        """Switch to another project file (it may not exist yet: new project)."""
        p = Path(path).expanduser()
        if p.suffix.lower() not in (".cg", ".json"):
            raise ValueError("projects are .cg or .json files")
        if not p.parent.is_dir():
            raise ValueError(f"folder {p.parent} does not exist")
        self.path = p.resolve()
        self.mtime = 0.0
        self.reload()
        from .. import deps
        deps.remember_project(self.path)

    def save_as(self, design: Design, path) -> dict:
        self.open(path)
        return self.save(design, None, force=True)

    def save(self, design: Design, base_mtime: Optional[float],
             force: bool = False) -> dict:
        """Write the project. Refuses (conflict) if the file changed on disk
        since the editor loaded it, unless force is set."""
        current = self.path.stat().st_mtime if self.path.exists() else 0.0
        if not force and base_mtime is not None and abs(current - base_mtime) > 1e-6:
            return {"conflict": True, "mtime": current}
        first = not self.path.exists()
        save_design(design, self.path)
        if first:                             # a new project: now it's a recent one
            from .. import deps
            deps.remember_project(self.path)
        self.mtime = self.path.stat().st_mtime
        self.design = design
        self.error = ""
        return {"conflict": False, "mtime": self.mtime}

    def check_changed(self) -> bool:
        try:
            m = self.path.stat().st_mtime
        except OSError:
            return False
        if m != self.mtime:
            self.reload()
            return True
        return False

    def payload(self) -> dict:
        self.check_changed()
        from .. import deps
        return {
            "path": str(self.path),
            "recent": [p for p in deps.recent_projects() if p != str(self.path.resolve())],
            "mtime": self.mtime,
            "error": self.error,
            "design": _design_dict(self.design),
        }


def _design_dict(d: Design) -> dict:
    import json
    return json.loads(d.to_json())
