"""Target devices, their packages, and pin assignment.

ATF15xx CPLDs: pin tables generated from Atmel's BSDL files (pintables.py,
tools/bsdl_to_pins.py), so they include every package's VCC/GND pins.

GreenPAK (Renesas SLG466xx): pin tables and logic resources typed in from
the Renesas datasheets (SLG46826 rev 3.25, SLG46620 rev 1.22). These are
design-and-check targets: there is no open flow to program them, so the
tool sizes the design in LUTs/DFFs and prints a sheet for Go Configure.
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
    # Pin capabilities (all subsets of io). Empty for the ATF parts, where
    # every I/O can be an input, output, 3-state or bidirectional pin.
    out_only: List[int] = field(default_factory=list)      # outputs only
    no_oe: List[int] = field(default_factory=list)         # no output enable
    reserved: Dict[str, int] = field(default_factory=dict) # e.g. I2C SCL/SDA
    pin_names: Dict[int, str] = field(default_factory=dict)  # datasheet names
    # Drawing: "plcc" (pin 1 mid-top) or "qfn" (pin 1 top-left, CCW), and
    # pins per side (left, bottom, right, top); None = square.
    style: str = ""
    sides: Optional[Tuple[int, int, int, int]] = None
    footprint: str = ""                                    # KiCad footprint

    @property
    def restricted(self) -> bool:
        return bool(self.out_only or self.no_oe)

    def oe_pins(self) -> List[int]:
        return [p for p in self.io if p not in self.no_oe and p not in self.out_only]


@dataclass
class Device:
    name: str
    macrocells: int
    packages: Dict[str, Package]
    vcc: float = 5.0
    fitter_tech: str = ""       # -tech name the Microchip fitter accepts
    kind: str = "cpld"          # "cpld" (ATF15xx), "greenpak" or "gal"
    # GreenPAK logic cells: slot type -> count. A slot type names what a cell
    # can be: "lut3_dff" is a 3-bit LUT or a DFF/latch.
    resources: Dict[str, int] = field(default_factory=dict)
    supply: str = ""            # supply range, for the device list
    note: str = ""

    @property
    def family(self) -> str:    # ATF1502 / ATF1504 / ATF1508, or the GreenPAK part
        return self.name if self.kind in ("greenpak", "gal") else self.name[:7]


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


# ---- GreenPAK ---------------------------------------------------------------
def _gp_package(name: str, pins: Dict[int, str], out_only, no_oe, reserved,
                sides, footprint) -> Package:
    io = sorted(n for n, nm in pins.items() if nm.startswith(("IO", "PIN")))
    power = {n: ("GND" if nm == "GND" else "VCC") for n, nm in pins.items()
             if nm in ("VDD", "VDD2", "GND")}
    inputs = {nm: n for n, nm in pins.items() if nm == "GPI"}
    by_name = {nm: n for n, nm in pins.items()}
    return Package(name, io, inputs, {}, power, len(pins), [],
                   [by_name[x] for x in out_only], [by_name[x] for x in no_oe],
                   {r: by_name[r] for r in reserved}, dict(pins), "qfn", sides, footprint)


_STQFN = "Package_DFN_QFN:Renesas_UQFN-20_2x3mm_P0.4mm_LayoutBorder4x6y"
_TSSOP = "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm"

# SLG46826 (datasheet rev 3.25, section 2): IO6/IO7 are outputs only;
# IO0/IO2/IO3 have no output enable; SCL/SDA are the I2C (and in-system
# programming) pins. Pin numbers differ between the two packages.
_SLG46826_STQFN = {1: "VDD", 2: "IO0", 3: "IO1", 4: "IO2", 5: "IO3", 6: "IO4", 7: "IO5",
                   8: "SCL", 9: "SDA", 10: "IO6", 11: "GND", 12: "IO7", 13: "IO8",
                   14: "VDD2", 15: "IO9", 16: "IO10", 17: "IO11", 18: "IO12",
                   19: "IO13", 20: "IO14"}
_SLG46826_TSSOP = {1: "IO14", 2: "IO13", 3: "IO12", 4: "IO11", 5: "IO10", 6: "IO9",
                   7: "VDD2", 8: "IO8", 9: "IO7", 10: "GND", 11: "IO6", 12: "SDA",
                   13: "SCL", 14: "IO5", 15: "IO4", 16: "IO3", 17: "IO2", 18: "IO1",
                   19: "IO0", 20: "VDD"}
_SLG46826 = dict(out_only=["IO6", "IO7"], no_oe=["IO0", "IO2", "IO3"],
                 reserved=["SCL", "SDA"])

# SLG46620 (datasheet rev 1.22, section 2.1): same numbering in both
# packages; pin 2 is input only; pins without "with OE" can't be 3-state.
_SLG46620_PINS = {1: "VDD", 2: "GPI", 11: "GND",
                  **{n: f"PIN{n}" for n in list(range(3, 11)) + list(range(12, 21))}}
_SLG46620 = dict(out_only=[], no_oe=[f"PIN{n}" for n in (4, 6, 8, 12, 15, 17, 20)],
                 reserved=[])

DEVICES["SLG46826"] = Device(
    "SLG46826", 0, {
        "STQFN20": _gp_package("STQFN20", _SLG46826_STQFN, sides=(6, 4, 6, 4),
                               footprint=_STQFN, **_SLG46826),
        "TSSOP20": _gp_package("TSSOP20", _SLG46826_TSSOP, sides=(10, 0, 10, 0),
                               footprint=_TSSOP, **_SLG46826),
    }, 5.0, kind="greenpak", supply="2.5-5 V (VDD2 1.8-5 V)",
    # 3x 2-bit LUT/DFF, 1x 2-bit LUT (or pattern generator), 6+7 3-bit LUT/DFF
    # (7 of them share a cell with an 8-bit counter), 1x 3-bit LUT (or pipe
    # delay), 1x 4-bit LUT/DFF (shares a cell with a 16-bit counter).
    resources={"lut2_dff": 3, "lut2": 1, "lut3_dff": 13, "lut3": 1, "lut4_dff": 1},
    note="in-system reprogrammable over I2C")
DEVICES["SLG46620"] = Device(
    "SLG46620", 0, {
        "STQFN20": _gp_package("STQFN20", _SLG46620_PINS, sides=(6, 4, 6, 4),
                               footprint=_STQFN, **_SLG46620),
        "TSSOP20": _gp_package("TSSOP20", _SLG46620_PINS, sides=(10, 0, 10, 0),
                               footprint=_TSSOP, **_SLG46620),
    }, 5.0, kind="greenpak", supply="1.8-5 V",
    # 8x 2-bit LUT, 16x 3-bit LUT, 2x 4-bit LUT (one doubles as the pattern
    # generator), 12 dedicated DFF/latches, 2 inverters.
    resources={"lut2": 8, "lut3": 16, "lut4": 2, "dff": 12, "inv": 2},
    note="one-time programmable (emulate on the dev board first)")


# ---- GAL16V8 / GAL22V10 ------------------------------------------------------------
# Pin roles from the Lattice datasheets. The fitter (gal.py) works in DIP pin
# numbers; the PLCC packages map onto them (PLCC20 numbers match the DIP;
# PLCC28 adds a no-connect pin at 1, 8, 15 and 22).
def _gal_package(name: str, dip_pins: int, olmc: List[int], roles: Dict[int, str],
                 plcc28: bool = False, footprint: str = "",
                 reserved: Optional[Dict[str, int]] = None) -> Package:
    to_pkg = (lambda d: d + 1 + (d - 1) // 6) if plcc28 else (lambda d: d)
    gnd, vcc = dip_pins // 2, dip_pins
    io = [to_pkg(p) for p in olmc]
    res = {k: to_pkg(p) for k, p in (reserved or {}).items()}
    inputs = {f"I{to_pkg(p)}": to_pkg(p) for p in range(1, dip_pins)
              if p not in olmc and p != gnd and to_pkg(p) not in res.values()}
    names = {to_pkg(p): roles.get(p, "I/O" if p in olmc else "I")
             for p in range(1, dip_pins + 1)}
    names[to_pkg(gnd)], names[to_pkg(vcc)] = "GND", "VCC"
    nc = [1, 8, 15, 22] if plcc28 else []
    total = 28 if plcc28 else dip_pins
    dip = name.startswith("DIP")
    return Package(name, io, inputs, {}, {to_pkg(gnd): "GND", to_pkg(vcc): "VCC"}, total, nc,
                   reserved=res, pin_names=names, style="" if dip else "plcc",
                   sides=(total // 2, 0, total // 2, 0) if dip else None, footprint=footprint)


def gal_dip_pin(package: str, pin: int) -> int:
    """Package pin -> DIP pin (what the GAL fitter uses)."""
    if package.upper() == "PLCC28":
        return pin - 1 - (pin - 1) // 7
    return pin


def gal_package_pin(package: str, dip: int) -> int:
    if package.upper() == "PLCC28":
        return dip + 1 + (dip - 1) // 6
    return dip


_G16 = list(range(12, 20))
_G16_ROLES = {1: "I/CLK", 11: "I/OE"}
_G22 = list(range(14, 24))
_G22_ROLES = {1: "I/CLK"}
DEVICES["GAL16V8"] = Device(
    "GAL16V8", 8, {
        "DIP20": _gal_package("DIP20", 20, _G16, _G16_ROLES,
                              footprint="Package_DIP:DIP-20_W7.62mm"),
        "PLCC20": _gal_package("PLCC20", 20, _G16, _G16_ROLES,
                               footprint="Package_LCC:PLCC-20"),
    }, 5.0, kind="gal", supply="5 V",
    note="8 output macrocells (8 product terms each); also ATF16V8B")
_G20 = list(range(15, 23))
_G20_ROLES = {1: "I/CLK", 13: "I/OE"}
DEVICES["GAL20V8"] = Device(
    "GAL20V8", 8, {
        "DIP24": _gal_package("DIP24", 24, _G20, _G20_ROLES,
                              footprint="Package_DIP:DIP-24_W7.62mm"),
        "PLCC28": _gal_package("PLCC28", 24, _G20, _G20_ROLES, plcc28=True,
                               footprint="Package_LCC:PLCC-28"),
    }, 5.0, kind="gal", supply="5 V",
    note="8 output macrocells (8 product terms each), 14 dedicated inputs; also ATF20V8B")
_G20RA_ROLES = {1: "/PL", 13: "/OE"}
_G20RA_RES = {"/PL": 1, "/OE": 13}
DEVICES["GAL20RA10"] = Device(
    "GAL20RA10", 10, {
        "DIP24": _gal_package("DIP24", 24, _G22, _G20RA_ROLES, reserved=_G20RA_RES,
                              footprint="Package_DIP:DIP-24_W7.62mm"),
        "PLCC28": _gal_package("PLCC28", 24, _G22, _G20RA_ROLES, plcc28=True,
                               reserved=_G20RA_RES, footprint="Package_LCC:PLCC-28"),
    }, 5.0, kind="gal", supply="5 V",
    note="10 registers, each with its own clock, reset and preset term (4 product terms "
         "per output)")
DEVICES["GAL22V10"] = Device(
    "GAL22V10", 10, {
        "DIP24": _gal_package("DIP24", 24, _G22, _G22_ROLES,
                              footprint="Package_DIP:DIP-24_W7.62mm"),
        "PLCC28": _gal_package("PLCC28", 24, _G22, _G22_ROLES, plcc28=True,
                               footprint="Package_LCC:PLCC-28"),
    }, 5.0, kind="gal", supply="5 V",
    note="10 output macrocells (8-16 product terms); also ATF22V10C")


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


def _needs_oe(direction: str, drive: str) -> bool:
    return direction == "inout" or (direction == "output" and drive == "tri")


def assign_pins(device: str, package: str, signals: List[Tuple],
                locks: Dict[str, int], keep_jtag: bool = True) -> PinResult:
    """signals: (name, 'input'|'output'|'inout'[, drive]) where drive is
    "tri" for a 3-state output. Returns pin numbers.

    Locked signals keep their pins. Remaining inputs go to the dedicated
    input-only pins first, then everything fills the general I/O pins in
    ascending order. JTAG pins are reserved unless keep_jtag is False.
    On packages whose pins differ (GreenPAK: output-only pins, pins without
    an output enable), each signal only goes where it can work: 3-state and
    bidirectional signals need a pin with an output enable, and the more
    limited pins are used up first.
    """
    res = PinResult()
    dev, pkg = get_package(device, package)
    sigs = [(t[0], t[1], t[2] if len(t) > 2 else "") for t in signals]
    in_only = set(pkg.inputs.values())
    usable_io = [p for p in pkg.io if not (keep_jtag and p in pkg.jtag.values())]
    free_io = list(usable_io)
    free_in = sorted(in_only)
    info = {name: (d, drive) for name, d, drive in sigs}
    out_only, no_oe = set(pkg.out_only), set(pkg.no_oe)

    def why_not(pin: int, d: str, drive: str) -> str:
        """Why a signal can't use this I/O pin ('' if it can)."""
        if d != "output" and pin in out_only:
            return f"pin {pin} is output-only"
        if _needs_oe(d, drive) and (pin in no_oe or pin in out_only):
            kind = "bidirectional" if d == "inout" else "3-state"
            return f"pin {pin} has no output enable, so it can't be {kind}"
        return ""

    for sig, pin in locks.items():
        if sig not in info:
            res.errors.append(f"pin lock for unknown signal {sig!r}")
            continue
        d, drive = info[sig]
        pin = int(pin)
        if pin in in_only:
            if d != "input":
                res.errors.append(f"{sig} is an {d} but pin {pin} is input-only")
                continue
            free_in.remove(pin) if pin in free_in else res.errors.append(
                f"pin {pin} locked twice")
        elif pin in free_io:
            reason = why_not(pin, d, drive)
            if reason:
                res.errors.append(f"{sig}: {reason}")
                continue
            free_io.remove(pin)
        elif keep_jtag and pin in pkg.jtag.values():
            res.errors.append(f"pin {pin} is a JTAG pin (use --no-jtag to free it)")
            continue
        else:
            res.errors.append(f"pin {pin} is not a usable I/O pin on "
                              f"{dev.name} {pkg.name} (or is locked twice)")
            continue
        res.pins[sig] = pin

    todo = [(s_, d, drive) for s_, d, drive in sigs if s_ not in res.pins]
    for sig, d, _ in todo:
        if d == "input" and free_in:
            res.pins[sig] = free_in.pop(0)

    def overflow(left: int, what: str = "") -> None:
        res.errors.append(
            f"design needs {len(sigs)} pins; {dev.name} {pkg.name} has "
            f"{len(usable_io) + len(in_only)} usable "
            f"({len(usable_io)} I/O + {len(in_only)} input-only"
            f"{', JTAG reserved' if keep_jtag and pkg.jtag else ''}). "
            f"{left} signal(s) left over{what}.")

    if not pkg.restricted:
        for sig, d, _ in todo:
            if sig in res.pins:
                continue
            if not free_io:
                overflow(sum(1 for s_, _, _ in todo if s_ not in res.pins))
                break
            res.pins[sig] = free_io.pop(0)
    else:
        # Most demanding first, each onto the least capable pin that works.
        def rank(pin: int) -> int:        # lower = less capable, used first
            return 0 if pin in out_only else 1 if pin in no_oe else 2
        groups = [
            [t for t in todo if _needs_oe(t[1], t[2])],
            [t for t in todo if t[1] == "input"],
            [t for t in todo if t[1] == "output" and not _needs_oe(t[1], t[2])],
        ]
        short = []
        for group in groups:
            for sig, d, drive in group:
                if sig in res.pins:
                    continue
                ok = sorted((p for p in free_io if not why_not(p, d, drive)),
                            key=lambda p: (rank(p), p))
                if not ok:
                    short.append((sig, d, drive))
                    continue
                res.pins[sig] = ok[0]
                free_io.remove(ok[0])
        if short:
            n_oe = sum(1 for _, d, dr in short if _needs_oe(d, dr))
            what = (f" ({n_oe} of them 3-state/bidirectional, which need one of the "
                    f"{len(pkg.oe_pins())} pins with an output enable)") if n_oe else ""
            overflow(len(short), what)
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
