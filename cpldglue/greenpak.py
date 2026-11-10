"""GreenPAK target: size the design in LUTs and DFFs, and print it for
Renesas Go Configure.

There is no open flow to program GreenPAKs any more (Yosys dropped
synth_greenpak4), so this maps the generated Verilog onto 2-4 input LUTs and
D flip-flops/latches with Yosys, checks that they fit the part's logic cells
(a proper matching, since on some parts a cell is a LUT *or* a DFF), and
writes a sheet listing every LUT's truth table, every DFF and every pin, to
enter by hand in Go Configure's schematic editor.
"""
from __future__ import annotations

import hashlib
import html
import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import devices, yosys
from .design import Design
from .generate import Result, sanitize

# What each kind of GreenPAK logic cell can hold.
SLOT_TITLES = {
    "lut2_dff": "2-bit LUT or DFF/latch", "lut2": "2-bit LUT",
    "lut3_dff": "3-bit LUT or DFF/latch", "lut3": "3-bit LUT",
    "lut4_dff": "4-bit LUT or DFF/latch", "lut4": "4-bit LUT",
    "dff": "DFF/latch", "inv": "inverter",
}

LEGAL_FFS = ["$_DFF_P_", "$_DFF_N_", "$_DFF_PN0_", "$_DFF_PN1_", "$_DFF_NN0_", "$_DFF_NN1_",
             "$_DFFSR_PNN_", "$_DLATCH_P_", "$_DLATCH_N_", "$_DLATCH_PN0_", "$_DLATCH_PN1_"]


def script(top: str, verilog: str, lut: int = 4) -> str:
    legal = " ".join(f"-cell {c} 01" for c in LEGAL_FFS)
    return f"""read_verilog {verilog}
hierarchy -top {top}
proc
flatten
tribuf
synth -top {top} -flatten
dfflegalize {legal}
abc -lut {lut}
opt_clean
write_json mapped.json
"""


@dataclass
class Lut:
    out: str
    inputs: List[str]
    truth: List[int]                 # truth[i]: output when inputs = bits of i (IN0 = bit 0)

    @property
    def width(self) -> int:
        return len(self.inputs)

    @property
    def is_inverter(self) -> bool:
        return self.width == 1 and self.truth == [1, 0]

    def expression(self) -> str:
        return sop(self.inputs, self.truth)


@dataclass
class Flop:
    kind: str                        # "DFF" or "latch"
    q: str
    d: str
    clock: str                       # clock (DFF) or enable (latch) net
    clock_falling: bool = False      # DFF clocked on the falling edge / latch open when low
    reset: Optional[str] = None      # active-low async reset net (to 0)
    set: Optional[str] = None        # active-low async set net (to 1)

    @property
    def placeable(self) -> bool:     # GreenPAK DFFs have nRESET *or* nSET
        return not (self.reset and self.set)


@dataclass
class Fit:
    ok: bool
    used: Dict[str, int]             # slot type -> cells used
    total: Dict[str, int]            # slot type -> cells on the part
    unplaced: List[str] = field(default_factory=list)


@dataclass
class Mapping:
    luts: List[Lut]
    flops: List[Flop]
    tbufs: Dict[str, str]            # output port -> output-enable net
    pins: Dict[str, int]
    fit: Fit
    notes: List[str] = field(default_factory=list)
    tbuf_data: Dict[str, str] = field(default_factory=dict)   # 3-state port -> data net
    port_nets: Dict[str, str] = field(default_factory=dict)   # output/inout port -> its net


# ---- logic minimisation for the readable equations --------------------------
def sop(names: List[str], truth: List[int]) -> str:
    """Minimal-ish sum of products for up to 4 inputs (brute-force primes)."""
    n = len(names)
    ones = {i for i, v in enumerate(truth) if v}
    if not ones:
        return "0"
    if len(ones) == len(truth):
        return "1"
    cubes = []                                   # (mask of cared bits, values)
    for care in range(1 << n):
        for val in range(1 << n):
            if val & ~care:
                continue
            covered = {i for i in range(1 << n) if i & care == val}
            if covered <= ones:
                cubes.append((care, val, covered))
    primes = [c for c in cubes if not any(o[2] > c[2] for o in cubes)]
    chosen, left = [], set(ones)
    while left:
        best = max(primes, key=lambda c: (len(c[2] & left), -bin(c[0]).count("1")))
        chosen.append(best)
        left -= best[2]

    def term(care: int, val: int) -> str:
        lits = [(names[k] if val >> k & 1 else f"~{names[k]}")
                for k in range(n) if care >> k & 1]
        return " & ".join(lits) if lits else "1"
    terms = [term(c, v) for c, v, _ in chosen]
    return " | ".join(f"({t})" if " & " in t and len(terms) > 1 else t for t in terms)


# ---- fitting -------------------------------------------------------------------
def _accepts(slot: str, item: Tuple[str, int, object]) -> bool:
    kind, width, obj = item
    if kind == "flop":
        return slot.endswith("dff") and obj.placeable
    if slot == "inv":
        return obj.is_inverter
    if slot == "dff":
        return False
    size = int(slot[3])                          # lut2 / lut3 / lut4 (+ _dff)
    return width <= size


def fit(dev: devices.Device, luts: List[Lut], flops: List[Flop]) -> Fit:
    slots = [t for t, n in dev.resources.items() for _ in range(n)]
    # Cheapest slots first, so small LUTs don't take the big ones.
    order = {"inv": 0, "dff": 1, "lut2": 2, "lut2_dff": 3, "lut3": 4, "lut3_dff": 5,
             "lut4": 6, "lut4_dff": 7}
    slots.sort(key=lambda t: order[t])
    items = [("flop", 0, f) for f in flops] + \
            sorted((("lut", l.width, l) for l in luts), key=lambda x: -x[1])
    match: Dict[int, int] = {}                   # slot index -> item index

    def augment(i: int, seen: set) -> bool:
        for s, slot in enumerate(slots):
            if s in seen or not _accepts(slot, items[i]):
                continue
            seen.add(s)
            if s not in match or augment(match[s], seen):
                match[s] = i
                return True
        return False

    unplaced = []
    for i, it in enumerate(items):
        if not augment(i, set()):
            kind, w, obj = it
            unplaced.append(f"{'DFF/latch ' + obj.q if kind == 'flop' else f'{w}-input LUT ' + obj.out}"
                            + ("" if kind != "flop" or obj.placeable
                               else " (needs both async set and reset; GreenPAK DFFs have one)"))
    used = {t: 0 for t in dev.resources}
    for s in match:
        used[slots[s]] += 1
    return Fit(not unplaced, used, dict(dev.resources), unplaced)


# ---- reading the mapped netlist ------------------------------------------------
def _read(mapped: dict, top: str):
    mod = mapped["modules"][top]
    names: Dict[object, str] = {}
    for pname, p in mod["ports"].items():
        for i, b in enumerate(p["bits"]):
            names.setdefault(b, pname if len(p["bits"]) == 1 else f"{pname}[{i}]")
    for nname, n in sorted(mod["netnames"].items(), key=lambda kv: len(kv[0])):
        if n.get("hide_name"):
            continue
        for i, b in enumerate(n["bits"]):
            names.setdefault(b, nname if len(n["bits"]) == 1 else f"{nname}[{i}]")
    counter = itertools.count(1)

    def name(b) -> str:
        if b in ("0", "1"):
            return b
        if b not in names:
            names[b] = f"n{next(counter)}"
        return names[b]

    luts, flops, tbufs, tbuf_data = [], [], {}, {}
    for cell in mod["cells"].values():
        t, c = cell["type"], cell["connections"]
        if t == "$lut":
            w = int(cell["parameters"]["WIDTH"], 2)
            bits = cell["parameters"]["LUT"].rjust(1 << w, "0")
            truth = [int(bits[len(bits) - 1 - i]) for i in range(1 << w)]
            luts.append(Lut(name(c["Y"][0]), [name(b) for b in c["A"]], truth))
        elif t.startswith("$_DFF") or t.startswith("$_DLATCH"):
            latch = t.startswith("$_DLATCH")
            pol = t.split("_")[2]                 # e.g. P, PN0, PNN
            f = Flop("latch" if latch else "DFF", name(c["Q"][0]), name(c["D"][0]),
                     name(c["E" if latch else "C"][0]), pol[0] == "N")
            if "R" in c:
                f.reset = name(c["R"][0])
            if "S" in c:
                f.set = name(c["S"][0])
            if t[-2] == "1" and "R" in c and "S" not in c:   # ..._PN1_: async set
                f.set, f.reset = f.reset, None
            flops.append(f)
        elif t == "$_TBUF_":
            tbufs[name(c["Y"][0])] = name(c["E"][0])
            tbuf_data[name(c["Y"][0])] = name(c["A"][0])
    port_nets = {p: name(info["bits"][0]) for p, info in mod["ports"].items()
                 if info["direction"] != "input"}
    return luts, flops, tbufs, tbuf_data, port_nets


def map_design(design: Design, r: Result, workdir: Path, lut: int = 4) -> Mapping:
    dev, _ = devices.get_package(design.device, design.package)
    if dev.kind != "greenpak":
        raise ValueError(f"{dev.name} is not a GreenPAK")
    if not r.ok:
        raise ValueError("fix the report errors first: " + "; ".join(r.errors))
    top = sanitize(design.name)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / f"{top}.v").write_text(r.verilog, encoding="utf-8")
    yosys.run_script(script(top, f"{top}.v", lut), workdir, "greenpak.log")
    luts, flops, tbufs, tbuf_data, port_nets = _read(
        json.loads((workdir / "mapped.json").read_text(encoding="utf-8")), top)
    m = Mapping(luts, flops, tbufs, dict(r.pins), fit(dev, luts, flops),
                tbuf_data=tbuf_data, port_nets=port_nets)
    if any(not f.placeable for f in flops):
        m.notes.append("Some flip-flops need both an async set and an async reset (like a "
                       "74x74 with PRE and CLR both used); GreenPAK DFFs have one or the other.")
    if any(f.kind == "DFF" and f.clock_falling for f in flops):
        m.notes.append("Falling-edge flip-flops: set the DFF's clock polarity in Go "
                       "Configure, or put an inverter on its clock.")
    return m


class Session:
    """Cached GreenPAK mapping for the editor (keyed by the generated Verilog)."""

    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.cache: Dict[str, dict] = {}

    def payload(self, design: Design, r: Result) -> dict:
        key = hashlib.sha1((design.device + design.package + r.verilog
                            + json.dumps(r.pins, sort_keys=True)).encode()).hexdigest()
        if key not in self.cache:
            m = map_design(design, r, self.workdir / key[:12])
            self.cache = {key: {
                "ok": True, "fits": m.fit.ok, "notes": m.notes, "unplaced": m.fit.unplaced,
                "cells": [{"type": t, "title": SLOT_TITLES[t], "used": m.fit.used[t],
                           "total": m.fit.total[t]} for t in m.fit.total],
                "luts": len(m.luts), "flops": len(m.flops), "oe": len(m.tbufs),
                "sheet": sheet_html(design, r, m),
                "bitstream": bitstream_payload(design, r, m, self.workdir / key[:12] / "bits"),
            }}
        return self.cache[key]


def bitstream_payload(design: Design, r: Result, m: Mapping, workdir: Path) -> Optional[dict]:
    """For parts with a known register map: the bitstream, checked, and the
    files to program it (see gpbits.py). None for other GreenPAKs."""
    from . import gpbits
    if devices.DEVICES[design.device.upper()].name not in gpbits.SUPPORTED:
        return None
    if not m.fit.ok:
        return {"ok": False, "errors": ["the design doesn't fit"], "check": ""}
    try:
        b = gpbits.build(design, r, m, workdir)
    except (RuntimeError, ValueError) as e:
        return {"ok": False, "errors": [str(e)], "check": ""}
    out = {"ok": b.ok, "errors": b.errors, "notes": b.notes, "check": b.check,
           "placement": [f"{c}: {w}" for c, w in b.placement]}
    if b.bits:
        import base64
        out["files"] = {
            "txt": gpbits.txt_file(b.bits, b.owned),
            "ino": gpbits.arduino_sketch(b.bits, b.owned, design.name),
            "bin": base64.b64encode(gpbits.to_bytes(b.bits)).decode(),
            "mask": base64.b64encode(gpbits.to_bytes(b.owned)).decode(),
        }
    return out


# ---- the sheet -----------------------------------------------------------------
def _pin_rows(design: Design, r: Result, m: Mapping):
    _, pkg = devices.get_package(design.device, design.package)
    port_of = {p.name: p for p in r.ports}
    rows = []
    for name, pin in sorted(m.pins.items(), key=lambda kv: kv[1]):
        p = port_of[name]
        if p.direction == "input":
            mode = "Digital input"
        elif p.direction == "inout":
            mode = f"Digital in/out (output enable: {m.tbufs.get(name, '?')})"
        elif name in m.tbufs:
            mode = f"Push-pull output, 3-state (output enable: {m.tbufs[name]})"
        elif p.drive == "oc":
            mode = "Open-drain NMOS output"
        else:
            mode = "Push-pull output"
        rows.append((pin, pkg.pin_names.get(pin, ""), name, p.net, mode))
    return rows


def sheet_html(design: Design, r: Result, m: Mapping) -> str:
    dev, pkg = devices.get_package(design.device, design.package)
    e = html.escape
    parts = [f"<h1>{e(design.name)} on {e(dev.name)} {e(pkg.name)}</h1>",
             f"<p>Enter this in Renesas Go Configure (GreenPAK Designer): set up the "
             f"pins, then add each LUT and DFF and wire its inputs. {e(dev.note[:1].upper() + dev.note[1:])}.</p>"]
    status = "fits" if m.fit.ok else "does NOT fit"
    parts.append(f"<h2>Resources: {status}</h2><table><tr><th>Cell</th><th>Used</th><th>On chip</th></tr>")
    for t, n in m.fit.total.items():
        parts.append(f"<tr><td>{e(SLOT_TITLES[t])}</td><td>{m.fit.used[t]}</td><td>{n}</td></tr>")
    parts.append("</table>")
    for u in m.fit.unplaced:
        parts.append(f"<p class='bad'>No room for: {e(u)}</p>")
    for n in m.notes:
        parts.append(f"<p class='note'>{e(n)}</p>")

    parts.append("<h2>Pins</h2><table><tr><th>Pin</th><th>Name</th><th>Signal</th><th>Net</th>"
                 "<th>Mode</th></tr>")
    for pin, pname, sig, net, mode in _pin_rows(design, r, m):
        parts.append(f"<tr><td>{pin}</td><td>{e(pname)}</td><td>{e(sig)}</td>"
                     f"<td>{e(net)}</td><td>{e(mode)}</td></tr>")
    parts.append("</table>")

    parts.append(f"<h2>LUTs ({len(m.luts)})</h2>")
    for i, l in enumerate(sorted(m.luts, key=lambda l: (-l.width, l.out)), 1):
        ins = " ".join(f"<th>IN{k}<br><small>{e(n)}</small></th>" for k, n in reversed(list(enumerate(l.inputs))))
        rows = "".join(
            "<tr>" + "".join(f"<td>{idx >> k & 1}</td>" for k in reversed(range(l.width)))
            + f"<td class='out'>{v}</td></tr>" for idx, v in enumerate(l.truth))
        parts.append(f"<div class='lut'><h3>LUT {i}: {l.width}-bit &rarr; {e(l.out)}</h3>"
                     f"<p class='eq'>{e(l.out)} = {e(l.expression())}</p>"
                     f"<table class='tt'><tr>{ins}<th>OUT</th></tr>{rows}</table></div>")
    if m.flops:
        parts.append(f"<h2>DFFs / latches ({len(m.flops)})</h2><table><tr><th>Type</th><th>Q</th>"
                     "<th>D</th><th>Clock / enable</th><th>nRESET</th><th>nSET</th></tr>")
        for f in m.flops:
            clk = f"{f.clock} ({'falling' if f.clock_falling else 'rising'} edge)" if f.kind == "DFF" \
                else f"{f.clock} (open when {'low' if f.clock_falling else 'high'})"
            parts.append(f"<tr><td>{f.kind}</td><td>{e(f.q)}</td><td>{e(f.d)}</td><td>{e(clk)}</td>"
                         f"<td>{e(f.reset or '-')}</td><td>{e(f.set or '-')}</td></tr>")
        parts.append("</table>")
    if m.tbufs:
        parts.append("<h2>Output enables</h2><table><tr><th>Pin signal</th><th>OE net</th></tr>")
        for port, oe in m.tbufs.items():
            parts.append(f"<tr><td>{e(port)}</td><td>{e(oe)}</td></tr>")
        parts.append("</table>")
    style = ("body{font:13px system-ui,sans-serif;margin:24px;color:#1d2330}"
             "table{border-collapse:collapse;margin:6px 0 14px}td,th{border:1px solid #ccd;"
             "padding:2px 8px;text-align:left}th small{font-weight:400;color:#556}"
             ".tt td{text-align:center;font-family:monospace}.tt td.out{font-weight:700}"
             ".lut{display:inline-block;vertical-align:top;margin:0 18px 10px 0}"
             ".eq{font-family:monospace}.bad{color:#b00020;font-weight:600}.note{color:#555}"
             "@media print{.lut{break-inside:avoid}}")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{e(design.name)} "
            f"- GreenPAK sheet</title><style>{style}</style></head><body>"
            + "\n".join(parts) + "</body></html>")
