"""Turn a Design into one self-contained Verilog file for the CPLD.

How each net is resolved (only chips inside the CPLD are considered):

  power net                      -> constant 0/1 on every input
  no driver, external            -> top-level input pin
  no driver, internal, named     -> input pin (a labelled net probably
                                    goes somewhere; reported as a note)
  no driver, internal, unnamed   -> tied low, with a warning
  one totem-pole driver          -> plain wire; output pin if external
  3-state / open-collector       -> priority mux of the drivers (CPLDs have
    drivers                         no internal 3-state). External: a
                                    3-state output pin, or an inout pin if
                                    the CPLD also reads the net.
  totem-pole + anything else     -> error (contention)
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import chips, devices
from .units import UNITS
from .design import Design, Net

VERILOG_KEYWORDS = set("""always and assign begin buf case default else end
endcase endmodule for function if initial inout input integer module nand
negedge nor not or output parameter posedge reg supply0 supply1 tri wire xor
xnor generate genvar localparam signed""".split())


@dataclass
class TopPort:
    name: str        # Verilog port name
    direction: str   # input / output / inout
    net: str         # original net name
    drive: str = ""  # outputs: "tri" (3-state), "oc" (open collector), "" (push-pull)


@dataclass
class Result:
    verilog: str = ""
    ports: List[TopPort] = field(default_factory=list)
    pins: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    # net name -> Verilog expression holding its value (a wire/port name or a
    # constant like 1'b0); used by the GUI simulator to show net values.
    net_values: Dict[str, str] = field(default_factory=dict)
    # ref -> indices into units.UNITS[part] of gates left out (nothing uses
    # their outputs, so they cost no logic and their inputs need no pins).
    unused: Dict[str, List[int]] = field(default_factory=dict)
    # Macrocell estimate: (outputs, flip-flops/latches, device total or None).
    macrocells: Optional[Tuple[int, int, Optional[int]]] = None
    # Per chip: ref -> (output pins it drives, flip-flop/latch bits). A pin
    # shared by several 3-state drivers is split between them.
    macrocell_parts: Dict[str, Tuple[float, int, int]] = field(default_factory=dict)
    # Flip-flops/latches that drive an output pin on their own share that
    # pin's macrocell; counted once.
    macrocells_shared: int = 0
    # Variants: the variant this result is for (build mode), all variant
    # names, and (pins mode) each variant's VAR_SEL code, VAR_SEL0 first.
    variant: str = ""
    variants: List[str] = field(default_factory=list)
    select_codes: Dict[str, str] = field(default_factory=dict)

    @property
    def macrocell_estimate(self) -> Optional[int]:
        if self.macrocells is None:
            return None
        return self.macrocells[0] + self.macrocells[1] - self.macrocells_shared

    @property
    def ok(self) -> bool:
        return not self.errors

    def pin_file(self, design: Design) -> str:
        lines = [f'CHIP "{design.name}" ASSIGNED TO AN {design.package}']
        for p in self.ports:
            if p.name in self.pins:
                lines.append(f"{p.name:<16} : {self.pins[p.name]}")
        return "\n".join(lines) + "\n"

    def report(self, design: Design) -> str:
        out = [f"Design {design.name}: {len(design.parts)} chip(s) -> "
               f"{design.device} {design.package}",
               f"Pins used: {len(self.ports)}"]
        if self.select_codes:
            sel = sorted({p.name for p in self.ports if p.name.startswith("VAR_SEL")}, reverse=True)
            out.append(f"Variants, chosen by {' '.join(sel)}: " + ", ".join(
                f"{v} = {code[::-1]}" for v, code in self.select_codes.items()))
        elif self.variant:
            out.append(f"Variant: {self.variant} (of {', '.join(self.variants)})")
        if self.macrocells:
            outs, regs, total = self.macrocells
            shared = (f", {self.macrocells_shared} of them at their own pin"
                      if self.macrocells_shared else "")
            out.append(f"Macrocells: about {self.macrocell_estimate}"
                       + (f" of {total}" if total else "")
                       + f" ({outs} output pin(s) + {regs} flip-flop/latch bit(s){shared}; "
                         f"the fitter report has the real figure)")
        for p in sorted(self.ports, key=lambda p: self.pins.get(p.name, 999)):
            pin = self.pins.get(p.name, "?")
            out.append(f"  pin {pin!s:>3}  {p.direction:<6}  {p.name}"
                       + (f"   (net {p.net})" if p.net != p.name else ""))
        for title, items in (("Errors", self.errors), ("Warnings", self.warnings),
                             ("Notes", self.notes)):
            if items:
                out.append(f"{title}:")
                out += [f"  - {x}" for x in items]
        return "\n".join(out) + "\n"


def sanitize(name: str) -> str:
    s = name.lstrip("/")
    # KiCad escapes characters it uses itself: R{slash}~{W} is the label R/~{W}
    s = re.sub(r"\{(slash|backslash|colon|comma|space|tab|return|lt|gt|quote|dblquote|"
               r"brace|lbrace|rbrace|pipe|caret|tilde)\}", "_", s)
    neg = "~{" in s or s.startswith("~")
    s = re.sub(r"~\{([^}]*)\}", r"\1", s).lstrip("~")
    s = re.sub(r"[^A-Za-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_") or "net"
    if neg:
        s += "_n"
    if s[0].isdigit():
        s = "s" + s
    if s.lower() in VERILOG_KEYWORDS:
        s += "_"
    return s


class _Names:
    def __init__(self):
        self.used = set()

    def take(self, base: str) -> str:
        n, i = base, 2
        while n.lower() in self.used:
            n, i = f"{base}_{i}", i + 1
        self.used.add(n.lower())
        return n


def _list(items: List[str]) -> str:
    """["gate 2", "gate 3"] -> "gates 2 and 3"."""
    heads = {i.rsplit(" ", 1)[0] for i in items}
    if len(items) > 1 and len(heads) == 1 and all(" " in i for i in items):
        head = heads.pop()
        items = [i.rsplit(" ", 1)[1] for i in items]
        prefix = head + "s "
    else:
        prefix = ""
    body = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    return prefix + body


def _live_units(design: Design, pin_net: Dict[Tuple[str, str], Net]) -> Dict[str, List[bool]]:
    """Mark each gate used if one of its outputs goes off-chip, or feeds a
    used gate (directly or through other gates). Bidirectional pins count
    as both inputs and outputs."""
    lib = chips.LIBRARY
    num_of = {ref: {p.name: n for n, p in lib[k].pins.items()}
              for ref, k in design.parts.items()}
    live = {ref: [False] * len(UNITS[k]) for ref, k in design.parts.items()}
    drivers: Dict[str, List[Tuple[str, int]]] = {}       # net -> driving units
    for ref, k in design.parts.items():
        for i, u in enumerate(UNITS[k]):
            outs = u.outputs + (u.inputs if u.symbol == "bidir" else ())
            for name in outs:
                net = pin_net.get((ref, num_of[ref][name]))
                if net is None or net.const is not None:
                    continue
                drivers.setdefault(net.name, []).append((ref, i))
                if net.external:
                    live[ref][i] = True
    todo = [(ref, i) for ref, flags in live.items() for i, f in enumerate(flags) if f]
    while todo:
        ref, i = todo.pop()
        u = UNITS[design.parts[ref]][i]
        ins = u.inputs + u.controls + (u.outputs if u.symbol == "bidir" else ())
        for name in ins:
            net = pin_net.get((ref, num_of[ref][name]))
            if net is None:
                continue
            for d in drivers.get(net.name, []):
                if not live[d[0]][d[1]]:
                    live[d[0]][d[1]] = True
                    todo.append(d)
    return live


def _generate_variant(design: Design, assign: bool) -> Result:
    """Build mode: the active variant on its own, with pins chosen so that
    every variant puts each signal on the same pin (one board, one socket)."""
    name = design.active_variant()
    shared = Design.from_json(design.to_json())
    shared.variant_mode = "pins"
    rs = generate(shared, assign=True)
    v = design.for_variant(name)
    if rs.ok:
        v.pin_locks = {sig: pin for sig, pin in rs.pins.items() if not sig.startswith("VAR_SEL")}
        how = "each signal is on the same pin in every variant"
    else:
        how = ("the variants together don't fit, so pins were placed per variant and "
               "may differ between them")
    r = generate(v, assign)
    r.variant, r.variants = name, list(design.variants)
    r.notes.insert(0, f"Variant {name} of {len(design.variants)} "
                      f"({', '.join(design.variants)}); {how}.")
    return r


def generate(design: Design, assign: bool = True) -> Result:
    if design.variants and design.variant_mode != "pins":
        return _generate_variant(design, assign)
    r = Result()
    names = _Names()
    lib = chips.LIBRARY

    # ---- validate parts and pins -------------------------------------
    for ref, key in design.parts.items():
        if key not in lib:
            r.errors.append(f"{ref}: unknown part {key!r}")
        elif lib[key].warning:
            r.warnings.append(f"{ref} ({key}): {lib[key].warning}")
    if r.errors:
        return r
    for ref in design.parts:
        names.take(ref)

    pin_net: Dict[Tuple[str, str], Net] = {}
    for net in design.nets.values():
        for n in net.nodes:
            if n.ref not in design.parts:
                r.errors.append(f"net {net.name}: {n.ref} is not a CPLD part")
                continue
            if n.pin not in lib[design.parts[n.ref]].pins:
                r.errors.append(f"net {net.name}: {n.ref} has no pin {n.pin}")
                continue
            if (n.ref, n.pin) in pin_net:
                r.errors.append(f"{n.ref}.{n.pin} is on two nets "
                                f"({pin_net[(n.ref, n.pin)].name}, {net.name})")
            pin_net[(n.ref, n.pin)] = net
    if r.errors:
        return r

    # ---- which gates are used --------------------------------------------
    live = _live_units(design, pin_net)
    for ref, key in design.parts.items():
        dead = [i for i, ok in enumerate(live.get(ref, [])) if not ok]
        if dead:
            r.unused[ref] = dead
            units = UNITS[key]
            if len(dead) == len(units):
                r.notes.append(f"{ref} ({key}): nothing uses its outputs, so it is "
                               f"left out entirely")
            else:
                r.notes.append(f"{ref} ({key}): {_list([units[i].name for i in dead])} "
                               f"unused (outputs go nowhere); left out")

    def pin_live(ref: str, num: str) -> bool:
        """False for a pin that only belongs to unused gates."""
        key = design.parts[ref]
        if ref not in live:
            return True
        name = lib[key].pins[num].name
        owners = [i for i, u in enumerate(UNITS[key]) if name in u.pins]
        return not owners or any(live[ref][i] for i in owners)

    # ---- resolve nets ----------------------------------------------------
    decls: List[str] = []
    logic: List[str] = []
    net_value: Dict[str, str] = {}     # net name -> expression readers use
    driver_wires: Dict[Tuple[str, str], str] = {}  # (ref, port) -> wire name
    port_drivers: Dict[str, List[str]] = {}        # output port -> driving chips
    port_pins: Dict[str, List[Tuple[str, str]]] = {}  # output port -> (chip, pin name)

    def dwire(ref: str, port: str) -> str:
        w = names.take(f"{ref}_{port}")
        driver_wires[(ref, port)] = w
        decls.append(f"    wire {w};")
        return w

    # Pins mode: VAR_SEL inputs choose the variant; an optional chip's
    # outputs drive only while a variant that fits it is selected.
    optional = {ref: vs for ref, vs in design.optional_refs().items()
                if ref in design.parts} if design.variants else {}
    vnames = list(design.variants) if optional else []
    active: Dict[str, str] = {}                       # optional chip -> enable expression
    if optional:
        nsel = max(1, (len(vnames) - 1).bit_length())
        sel = [names.take(f"VAR_SEL{i}") for i in range(nsel)]
        for sp in sel:
            r.ports.append(TopPort(sp, "input", sp))
        vwire = {}
        for i, v in enumerate(vnames):
            w = names.take("var_" + sanitize(v))
            bits = " & ".join(sp if i >> k & 1 else f"~{sp}" for k, sp in enumerate(sel))
            decls.append(f"    wire {w};")
            logic.append(f"    assign {w} = {bits};   // variant {v}")
            vwire[v] = w
            r.select_codes[v] = "".join(str(i >> k & 1) for k in range(nsel))
        for ref, vs in optional.items():
            active[ref] = "(" + " | ".join(vwire[v] for v in vs) + ")" if len(vs) > 1 \
                else vwire[vs[0]]
        r.variants = vnames

    for net in design.nets.values():
        every = [(n, lib[design.parts[n.ref]].pins[n.pin]) for n in net.nodes]
        every = [(n, p) for n, p in every if not p.is_power]
        # Wiring mistakes are reported even when the gates involved are unused.
        drv_all = [(n, p) for n, p in every if p.kind in ("o", "t", "oc", "b")]
        clash = None
        if net.const is None:
            for v in (vnames or [None]):                # each variant on its own
                here = [(n, p) for n, p in drv_all
                        if n.ref not in optional or v in optional[n.ref]]
                if any(p.kind == "o" for _, p in here) and len(here) > 1:
                    clash = (v, here)
                    break
        if clash:
            v, here = clash
            who = ", ".join(f"{n.ref}.{n.pin}" for n, _ in here)
            r.errors.append(f"net {net.name}: more than one driver and at least "
                            f"one is not 3-state ({who})"
                            + (f" in variant {v}" if v else ""))
            continue
        kinds = [(n, p) for n, p in every if pin_live(n.ref, n.pin)]
        if net.const is not None:
            net_value[net.name] = f"1'b{net.const}"
            for n, pin in kinds:
                if pin.kind in ("o", "t", "oc"):
                    r.warnings.append(f"{n.ref}.{n.pin} ({pin.name}) is an output "
                                      f"on power net {net.name}; ignored")
                elif pin.kind == "b":
                    r.errors.append(f"{n.ref}.{n.pin} bidirectional pin on power "
                                    f"net {net.name}")
            continue

        # An optional chip's push-pull output acts as a 3-state driver,
        # enabled while its variant is selected.
        plain = [(n, p) for n, p in kinds if p.kind == "o" and n.ref not in optional]
        tri = [(n, p) for n, p in kinds
               if p.kind in ("t", "oc", "b") or (p.kind == "o" and n.ref in optional)]
        loads = [(n, p) for n, p in kinds if p.kind in ("i", "b")]
        has_bidir = any(p.kind == "b" for _, p in kinds)
        if not kinds:
            if net.external and net.nodes and any(
                    not lib[design.parts[n.ref]].pins[n.pin].is_power for n in net.nodes):
                r.notes.append(f"net {net.name} only goes to unused gates, so it "
                               f"gets no CPLD pin")
            continue
        if not loads and not net.external:
            continue        # output(s) going nowhere: leave unconnected

        if len(plain) > 1 or (plain and tri):
            who = ", ".join(f"{n.ref}.{n.pin}" for n, _ in plain + tri)
            r.errors.append(f"net {net.name}: more than one driver and at least "
                            f"one is not 3-state ({who})")
            continue

        if has_bidir and not net.external:
            r.errors.append(f"net {net.name}: bidirectional pins need the net to "
                            f"be a CPLD pin (mark it external)")
            continue

        sig = sanitize(net.name)
        if plain:
            n, p = plain[0]
            src = dwire(n.ref, p.name)
            if net.external:
                port = names.take(sig)
                r.ports.append(TopPort(port, "output", net.name))
                port_drivers[port] = [n.ref]
                port_pins[port] = [(n.ref, p.name)]
                logic.append(f"    assign {port} = {src};")
            net_value[net.name] = src
        elif tri:
            datas, oes = [], []
            for n, p in tri:
                if p.kind == "o":                     # optional chip, push-pull
                    datas.append(dwire(n.ref, p.name))
                    oes.append(active[n.ref])
                    continue
                if p.kind == "t":
                    datas.append(dwire(n.ref, p.name))
                    oes.append(dwire(n.ref, p.name + "_oe"))
                elif p.kind == "b":
                    datas.append(dwire(n.ref, p.name + "_o"))
                    oes.append(dwire(n.ref, p.name + "_oe"))
                else:  # open collector: drives 0 when its output is 0
                    w = dwire(n.ref, p.name)
                    datas.append("1'b0")
                    oes.append(f"~{w}")
                if n.ref in active:                   # only in its variants
                    oes[-1] = f"({oes[-1]} & {active[n.ref]})"
            by_variant = [n.ref for n, _ in tri if n.ref in active]
            if by_variant and len(tri) > 1:
                r.notes.append(f"net {net.name}: driven by "
                               f"{' / '.join(f'{n.ref}.{n.pin}' for n, _ in tri)}, "
                               f"chosen by the variant (VAR_SEL)")
            elif len(tri) > 1:
                r.notes.append(f"net {net.name}: {len(tri)} 3-state drivers merged "
                               f"into a mux (first enabled wins: "
                               f"{', '.join(f'{n.ref}.{n.pin}' for n, _ in tri)})")
            # Shape: any_oe ? (oe1 ? d1 : oe2 ? d2 : ... dN) : idle
            # The Z must sit in the outermost mux for 3-state inference.
            data = datas[-1]
            for d, e in reversed(list(zip(datas[:-1], oes[:-1]))):
                data = f"{e} ? {d} : {data}"
            any_oe = " | ".join(oes)
            if len(oes) > 1:
                any_oe = f"({any_oe})"
            if len(datas) > 1:
                data = f"({data})"
            idle = "1'bz" if net.external else "1'b1"
            mux = f"{any_oe} ? {data} : {idle}"
            if net.external:
                direction = "inout" if loads else "output"
                port = names.take(sig)
                drive = "oc" if all(p.kind == "oc" for _, p in tri) else "tri"
                r.ports.append(TopPort(port, direction, net.name, drive))
                port_drivers[port] = [n.ref for n, _ in tri]
                port_pins[port] = [(n.ref, p.name) for n, p in tri]
                logic.append(f"    assign {port} = {mux};")
                net_value[net.name] = port
            else:
                w = names.take("n_" + sig)
                decls.append(f"    wire {w};")
                logic.append(f"    assign {w} = {mux};")
                net_value[net.name] = w
                r.notes.append(f"net {net.name}: when no driver is enabled it "
                               f"reads 1 (as if pulled up)")
        else:  # no drivers inside the CPLD
            if not loads:
                continue
            if net.external or net.named:
                port = names.take(sig)
                r.ports.append(TopPort(port, "input", net.name))
                net_value[net.name] = port
                if not net.external:
                    r.notes.append(f"net {net.name} has no driver on the "
                                   f"schematic; made it an input pin because it "
                                   f"is labelled")
            else:
                r.warnings.append(f"net {net.name} has no driver; tied low")
                net_value[net.name] = "1'b0"

    # ---- instances ---------------------------------------------------------
    insts: List[str] = []
    for ref, key in design.parts.items():
        part = lib[key]
        conns = []
        for num, pin in part.pins.items():
            if pin.is_power:
                continue
            net = pin_net.get((ref, num))
            val = net_value.get(net.name) if net else None
            if not pin_live(ref, num):                 # pin of an unused gate
                if pin.kind == "i":
                    conns.append((pin.name, "1'b0"))
                elif pin.kind == "b":
                    conns += [(pin.name + "_i", "1'b0"), (pin.name + "_o", ""),
                              (pin.name + "_oe", "")]
                elif pin.kind == "t":
                    conns += [(pin.name, ""), (pin.name + "_oe", "")]
                else:
                    conns.append((pin.name, ""))
                continue
            if pin.kind == "i":
                if val is None:
                    r.warnings.append(f"{ref}.{num} ({pin.name}) input is not "
                                      f"connected; tied low")
                    val = "1'b0"
                conns.append((pin.name, val))
            elif pin.kind in ("o", "oc"):
                conns.append((pin.name, driver_wires.get((ref, pin.name), "")))
            elif pin.kind == "t":
                conns.append((pin.name, driver_wires.get((ref, pin.name), "")))
                conns.append((pin.name + "_oe",
                              driver_wires.get((ref, pin.name + "_oe"), "")))
            elif pin.kind == "b":
                conns.append((pin.name + "_i", val or "1'b0"))
                conns.append((pin.name + "_o",
                              driver_wires.get((ref, pin.name + "_o"), "")))
                conns.append((pin.name + "_oe",
                              driver_wires.get((ref, pin.name + "_oe"), "")))
        body = ",\n".join(f"        .{p}({v})" for p, v in conns)
        insts.append(f"    {part.module} {ref} (  // {key}: {part.title}\n{body}\n    );")

    if r.errors:
        return r
    r.net_values = dict(net_value)

    # ---- pins ----------------------------------------------------------------
    if assign:
        try:
            locks = design.pin_locks
            if design.variant_of:          # locks for other variants' signals don't apply
                here = {p.name for p in r.ports}
                locks = {sig: pin for sig, pin in locks.items() if sig in here}
            pr = devices.assign_pins(design.device, design.package,
                                     [(p.name, p.direction, p.drive) for p in r.ports],
                                     locks, design.keep_jtag)
            r.pins = pr.pins
            r.errors += pr.errors
        except ValueError as e:
            r.errors.append(str(e))

    # ---- capacity / device notes --------------------------------------------
    dev = devices.DEVICES.get(design.device.upper())
    is_gp = bool(dev and dev.kind == "greenpak")
    if is_gp:
        r.notes.append(f"{dev.name} is a GreenPAK: size the logic with the LUT "
                       f"check (needs Yosys) and enter it in Renesas Go Configure "
                       f"from the LUT sheet; {dev.note}.")
        dev = None                 # no macrocell estimate for GreenPAKs
    is_gal = bool(dev and dev.kind == "gal")
    if is_gal:
        r.notes.append(f"{dev.name} is a GAL: the Build button fits the design into its "
                       f"{dev.macrocells} output macrocells (OLMCs) and writes the .jed "
                       f"(needs Yosys); the GAL panel shows the real fit and pins. Every "
                       f"output and every flip-flop or latch takes an OLMC.")
    outs = sum(1 for p in r.ports if p.direction != "input")
    regs = sum(u.storage for ref, k in design.parts.items()
               for i, u in enumerate(UNITS[k]) if i not in r.unused.get(ref, []))
    r.macrocells = (outs, regs, dev.macrocells if dev else None)
    sole = {pins[0] for pins in port_pins.values() if len(pins) == 1}
    per: Dict[str, List[float]] = {ref: [0.0, 0, 0] for ref in design.parts}
    for ref, k in design.parts.items():
        for i, u in enumerate(UNITS[k]):
            if i in r.unused.get(ref, []) or not u.storage:
                continue
            per[ref][1] += u.storage
            at_pins = sum(1 for o in u.outputs if (ref, o) in sole)
            per[ref][2] += min(u.storage, at_pins)
    for refs in port_drivers.values():
        for ref in refs:
            per[ref][0] += 1 / len(refs)
    r.macrocell_parts = {ref: (round(o, 3), int(st), int(sh)) for ref, (o, st, sh) in per.items()}
    r.macrocells_shared = sum(v[2] for v in r.macrocell_parts.values())
    need = r.macrocell_estimate or 0
    if dev and need > dev.macrocells:
        bigger = [n for n, d in devices.DEVICES.items()
                  if d.macrocells >= need and d.vcc == dev.vcc
                  and n == d.family + dev.name[7:]]
        cells = "output macrocells (OLMCs)" if is_gal else "macrocells"
        r.warnings.append(
            f"may not fit: about {need} {cells} needed ({outs} outputs + "
            f"{regs} flip-flops/latches - {r.macrocells_shared} at their own pin), "
            f"{dev.name} has {dev.macrocells}"
            + (f"; try {bigger[0]}" if bigger else "") + ". The fitter has the final word.")
    if is_gp:                      # macrocells don't apply; see greenpak.py
        r.macrocells, r.macrocell_parts, r.macrocells_shared = None, {}, 0
    if dev and dev.vcc < 5:
        r.notes.append(f"{dev.name} runs from 3.3 V. Check the datasheet for 5 V "
                       f"input tolerance and output levels before using it on a "
                       f"5 V board; use an AS/ASL part to replace 5 V logic directly.")

    # ---- emit ----------------------------------------------------------------
    top = sanitize(design.name)
    stamp = datetime.date.today().isoformat()
    head = [f"// {design.name}.v - generated by cpldglue on {stamp}. Do not edit;",
            f"// change the project and regenerate.",
            f"// Replaces: " + ", ".join(f"{ref} ({k})" for ref, k in design.parts.items()),
            f"// Target: {design.device} {design.package}",
            "//",
            f'//PIN: CHIP "{design.name}" ASSIGNED TO AN {design.package}']
    for p in r.ports:
        if p.name in r.pins:
            head.append(f"//PIN: {p.name:<16} : {r.pins[p.name]}")
    portlist = ",\n".join(f"    {p.direction:<6} wire {p.name}" for p in r.ports)
    modules = sorted({lib[k].module for k in design.parts.values()})
    r.verilog = "\n".join(head) + "\n\n" + \
        f"module {top} (\n{portlist}\n);\n" + \
        ("\n".join(decls) + "\n\n" if decls else "") + \
        "\n\n".join(insts) + "\n\n" + "\n".join(logic) + "\nendmodule\n\n" + \
        "// ---- chip models (from cpldglue/hdl/chips.v) ----\n\n" + \
        chips.verilog_modules(modules) + "\n"
    return r
