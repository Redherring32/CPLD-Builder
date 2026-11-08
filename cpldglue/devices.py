"""ATF15xx devices, packages and pin assignment.

Pin tables are generated from Atmel's BSDL files (see pintables.py and
tools/bsdl_to_pins.py), so they include every package's VCC/GND pins.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .pintables import TABLES


@dataclass
class Package:
    name: str
    io: List[int]
    inputs: Dict[str, int]      # dedicated input-only pins
    jtag: Dict[str, int]        # subset of io
    power: Dict[int, str] = field(default_factory=dict)   # pin -> VCC/GND
    pin_count: int = 44
    nc: List[int] = field(default_factory=list)            # no-connect pins


@dataclass
class Device:
    name: str
    macrocells: int
    packages: Dict[str, Package]
    vcc: float = 5.0
    fitter_tech: str = ""       # -tech name the Microchip fitter accepts

    @property
    def family(self) -> str:    # ATF1502 / ATF1504 / ATF1508
        return self.name[:7]


# Packages per family, from the Microchip datasheets / BSDL set.
_FAMILIES = {
    "ATF1502": (32, ["PLCC44", "TQFP44"]),
    "ATF1504": (64, ["PLCC44", "TQFP44", "PLCC68", "PLCC84", "TQFP100", "PQFP100"]),
    "ATF1508": (128, ["PLCC84", "TQFP100", "PQFP100", "PQFP160"]),
}
# Variants: AS = 5 V, ASL = 5 V low-power, ASV = 3.3 V, ASVL = 3.3 V low-power.
# The L parts are the same silicon as far as the fitter is concerned.
_VARIANTS = {
    "ATF1502": ["AS", "ASL", "ASV"],
    "ATF1504": ["AS", "ASL", "ASV", "ASVL"],
    "ATF1508": ["AS", "ASL", "ASV", "ASVL"],
}


def _package(family: str, name: str) -> Package:
    t = TABLES[(family, name)]
    return Package(name, list(t["io"]), dict(t["inputs"]), dict(t["jtag"]),
                   dict(t["power"]), t["total"], list(t["nc"]))


def _build() -> Dict[str, Device]:
    out: Dict[str, Device] = {}
    for fam, (mc, pkgs) in _FAMILIES.items():
        packages = {p: _package(fam, p) for p in pkgs}
        for v in _VARIANTS[fam]:
            name = fam + v
            out[name] = Device(name, mc, packages, 3.3 if "V" in v else 5.0,
                               fam + ("ASV" if "V" in v else "AS"))
    return out


DEVICES: Dict[str, Device] = _build()


def get_package(device: str, package: str) -> Tuple[Device, Package]:
    dev = DEVICES.get(device.upper())
    if dev is None:
        raise ValueError(f"unknown device {device!r}; known: {', '.join(DEVICES)}")
    pkg = dev.packages.get(package.upper())
    if pkg is None:
        raise ValueError(f"{dev.name} has no package {package!r}; known: "
                         f"{', '.join(dev.packages)}")
    return dev, pkg


@dataclass
class PinResult:
    pins: Dict[str, int] = field(default_factory=dict)    # signal -> pin number
    errors: List[str] = field(default_factory=list)
    free_io: List[int] = field(default_factory=list)
    free_inputs: List[int] = field(default_factory=list)


def assign_pins(device: str, package: str, signals: List[Tuple[str, str]],
                locks: Dict[str, int], keep_jtag: bool = True) -> PinResult:
    """signals: (name, 'input'|'output'|'inout'). Returns pin numbers.

    Locked signals keep their pins. Remaining inputs go to the dedicated
    input-only pins first, then everything fills the general I/O pins in
    ascending order. JTAG pins are reserved unless keep_jtag is False.
    """
    res = PinResult()
    dev, pkg = get_package(device, package)
    in_only = set(pkg.inputs.values())
    usable_io = [p for p in pkg.io if not (keep_jtag and p in pkg.jtag.values())]
    free_io = list(usable_io)
    free_in = sorted(in_only)
    directions = dict(signals)

    for sig, pin in locks.items():
        if sig not in directions:
            res.errors.append(f"pin lock for unknown signal {sig!r}")
            continue
        pin = int(pin)
        if pin in in_only:
            if directions[sig] != "input":
                res.errors.append(f"{sig} is an {directions[sig]} but pin {pin} "
                                  f"is input-only")
                continue
            free_in.remove(pin) if pin in free_in else res.errors.append(
                f"pin {pin} locked twice")
        elif pin in free_io:
            free_io.remove(pin)
        elif keep_jtag and pin in pkg.jtag.values():
            res.errors.append(f"pin {pin} is a JTAG pin (use --no-jtag to free it)")
            continue
        else:
            res.errors.append(f"pin {pin} is not a usable I/O pin on "
                              f"{dev.name} {pkg.name} (or is locked twice)")
            continue
        res.pins[sig] = pin

    todo = [(s, d) for s, d in signals if s not in res.pins]
    for sig, d in todo:
        if d == "input" and free_in:
            res.pins[sig] = free_in.pop(0)
    for sig, d in todo:
        if sig in res.pins:
            continue
        if not free_io:
            need = len(todo) - sum(1 for s, _ in todo if s in res.pins)
            res.errors.append(
                f"design needs {len(signals)} pins; {dev.name} {pkg.name} has "
                f"{len(usable_io) + len(in_only)} usable "
                f"({len(usable_io)} I/O + {len(in_only)} input-only"
                f"{', JTAG reserved' if keep_jtag else ''}). {need} signal(s) left over.")
            break
        res.pins[sig] = free_io.pop(0)
    res.free_io, res.free_inputs = free_io, free_in
    return res


def parse_pin_file(text: str) -> Dict[str, int]:
    """Read a .pin file ('SIGNAL : PIN' lines, as written by cpldglue and
    the atf15xx_yosys flow). The CHIP header line and comments are ignored."""
    out: Dict[str, int] = {}
    lines = text.splitlines()
    if any(l.lstrip().startswith("//PIN:") for l in lines):     # a Verilog file
        lines = [l for l in lines if l.lstrip().startswith("//PIN:")]
    for raw in lines:
        line = raw.strip()
        if line.startswith("//PIN:"):
            line = line[6:].strip()
        if not line or line.startswith(("#", "//")) or line.upper().startswith("CHIP "):
            continue
        name, sep, pin = line.partition(":")
        if not sep:
            raise ValueError(f"bad .pin line: {raw!r}")
        out[name.strip()] = int(pin.strip())
    return out
