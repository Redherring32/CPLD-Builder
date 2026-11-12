"""Target devices, their packages, and pin assignment.

ATF15xx CPLDs: pin tables generated from Atmel's BSDL files (pintables.py,
tools/bsdl_to_pins.py), so they include every package's VCC/GND pins.

GreenPAK (Renesas SLG466xx): pin tables and logic resources typed in from
the Renesas datasheets (SLG46826 rev 3.25, SLG46620 rev 1.22). These are
design-and-check targets: there is no open flow to program them, so the
tool sizes the design in LUTs/DFFs and prints a sheet for Go Configure.
"""
from __future__ import annotations

import re
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
    kind: str = "cpld"          # "cpld" (ATF15xx), "max7000", "greenpak", "gal", "ice40", "gowin"
    # GreenPAK logic cells: slot type -> count. A slot type names what a cell
    # can be: "lut3_dff" is a 3-bit LUT or a DFF/latch.
    resources: Dict[str, int] = field(default_factory=dict)
    supply: str = ""            # supply range, for the device list
    note: str = ""

    @property
    def family(self) -> str:    # ATF1502 / ATF1504 / ATF1508, or the GreenPAK part
        return self.name if self.kind in ("greenpak", "gal", "ice40", "gowin", "max7000") \
            else self.name[:7]


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
                sides, footprint, input_only=()) -> Package:
    """input_only: I/O names used only as inputs here (e.g. I2C pins whose
    outputs are open-drain only)."""
    io = sorted(n for n, nm in pins.items()
                if nm.startswith(("IO", "PIN")) and nm not in input_only)
    power = {n: ("GND" if nm == "GND" else "VCC") for n, nm in pins.items()
             if nm in ("VDD", "VDD2", "GND")}
    inputs = {nm: n for n, nm in pins.items() if nm == "GPI" or nm in input_only}
    nc = sorted(n for n, nm in pins.items() if nm == "NC")
    by_name = {nm: n for n, nm in pins.items()}
    return Package(name, io, inputs, {}, power, len(pins), nc,
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

# ---- more GreenPAKs (pin tables and macrocells from the Renesas datasheets) -------
# SLG46824 (rev 3.20): the SLG46826 die without the EEPROM emulation; same
# pins in both packages, same logic cells.
DEVICES["SLG46824"] = Device(
    "SLG46824", 0, {
        "STQFN20": _gp_package("STQFN20", _SLG46826_STQFN, sides=(6, 4, 6, 4),
                               footprint=_STQFN, **_SLG46826),
        "TSSOP20": _gp_package("TSSOP20", _SLG46826_TSSOP, sides=(10, 0, 10, 0),
                               footprint=_TSSOP, **_SLG46826),
    }, 5.0, kind="greenpak", supply="2.5-5 V (VDD2 1.8-5 V)",
    resources={"lut2_dff": 3, "lut2": 1, "lut3_dff": 13, "lut3": 1, "lut4_dff": 1},
    note="in-system reprogrammable over I2C")

# SLG46621 (rev 1.42): the SLG46620 with a second supply on pin 14 (for pins
# 12-20), so one GPIO fewer.
_SLG46621_PINS = {**_SLG46620_PINS, 14: "VDD2"}
DEVICES["SLG46621"] = Device(
    "SLG46621", 0, {
        "STQFN20": _gp_package("STQFN20", _SLG46621_PINS, sides=(6, 4, 6, 4),
                               footprint=_STQFN, **_SLG46620),
    }, 5.0, kind="greenpak", supply="1.8-5 V (VDD2 1.8-5 V, at most VDD)",
    resources={"lut2": 8, "lut3": 16, "lut4": 2, "dff": 12, "inv": 2},
    note="one-time programmable; dual supply (pins 12-20 on VDD2)")

# SLG46140 (14-pin STQFN, 1.6 x 2.0 mm): pin 2 input only; pins 6, 10, 11
# have no output enable. 4x 2-bit + 4x 3-bit LUT, 2x 2-bit LUT/DFF,
# 2x 3-bit LUT/DFF, 2x 3-bit LUT (pipe delay / counter), 2x 4-bit LUT
# (counter / pattern generator).
DEVICES["SLG46140"] = Device(
    "SLG46140", 0, {
        "STQFN14": _gp_package("STQFN14", {1: "VDD", 2: "GPI", 8: "GND",
                                           **{n: f"PIN{n}" for n in (3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14)}},
                               out_only=[], no_oe=["PIN6", "PIN10", "PIN11"], reserved=[],
                               sides=(5, 2, 5, 2), footprint=""),
    }, 5.0, kind="greenpak", supply="1.8-5 V",
    resources={"lut2": 4, "lut3": 6, "lut4": 2, "lut2_dff": 2, "lut3_dff": 2},
    note="one-time programmable (emulate on the dev board first)")

# SLG46108 (8-pin STQFN, 1.0 x 1.2 mm) and SLG46110 (12-pin STQFN): the same
# logic: 2x 2-bit + 2x 3-bit LUT, 2x 2-bit LUT/DFF, 2x 3-bit LUT/DFF, a 3-bit
# LUT (pipe delay) and a 4-bit LUT (counter). Only some pins have an output enable.
_SMALL = {"lut2": 2, "lut3": 3, "lut4": 1, "lut2_dff": 2, "lut3_dff": 2}
DEVICES["SLG46108"] = Device(
    "SLG46108", 0, {
        "STQFN8": _gp_package("STQFN8", {1: "VDD", 2: "GPI", 3: "PIN3", 4: "PIN4", 5: "GND",
                                         6: "PIN6", 7: "PIN7", 8: "PIN8"},
                              out_only=[], no_oe=["PIN3", "PIN6", "PIN7"], reserved=[],
                              sides=(3, 1, 3, 1), footprint=""),
    }, 5.0, kind="greenpak", supply="1.8-5 V", resources=dict(_SMALL),
    note="one-time programmable; 5 I/O + 1 input")
DEVICES["SLG46110"] = Device(
    "SLG46110", 0, {
        "STQFN12": _gp_package("STQFN12", {1: "VDD", 2: "GPI", 3: "PIN3", 4: "PIN4", 5: "NC",
                                           6: "PIN6", 7: "GND", 8: "PIN8", 9: "PIN9", 10: "PIN10",
                                           11: "NC", 12: "PIN12"},
                               out_only=[], no_oe=["PIN3", "PIN4", "PIN8", "PIN9", "PIN12"],
                               reserved=[], sides=(4, 2, 4, 2), footprint=""),
    }, 5.0, kind="greenpak", supply="1.8-5 V", resources=dict(_SMALL),
    note="one-time programmable; 7 I/O + 1 input")

# SLG4653x family (STQFN-20, 7-3-7-3 pins per side): pin 2 input only; the
# I2C pins (8 SCL, 9 SDA) have open-drain-only outputs, so they're used as
# inputs here. The MSTQFN-22 package (with centre pads) isn't drawn.
def _slg4653x(vdd2: bool = False) -> Dict[int, str]:
    pins = {1: "VDD", 2: "GPI", 11: "GND",
            **{n: f"PIN{n}" for n in list(range(3, 11)) + list(range(12, 21))}}
    pins[8], pins[9] = "PIN8/SCL", "PIN9/SDA"
    if vdd2:
        pins[14] = "VDD2"
    return pins


_SLG4653X_OPTS = dict(out_only=[], reserved=[], input_only=["PIN8/SCL", "PIN9/SDA"],
                      sides=(7, 3, 7, 3), footprint=_STQFN)
_SLG4653X = {"lut2_dff": 3, "lut3_dff": 5, "lut3": 6, "lut2": 1, "lut4": 2}
# SLG46531 (pin list from the datasheet's I/O chapter): OE on 3, 5, 7, 10,
# 13, 14, 16, 18, 19.
DEVICES["SLG46531"] = Device(
    "SLG46531", 0, {"STQFN20": _gp_package(
        "STQFN20", _slg4653x(), no_oe=[f"PIN{n}" for n in (4, 6, 12, 15, 17, 20)],
        **_SLG4653X_OPTS)},
    5.0, kind="greenpak", supply="1.8-5 V", resources=dict(_SLG4653X),
    note="in-system programmable over I2C; asynchronous state machine")
# SLG46533 / SLG46537 / SLG46538 (STQFN-20 tables): OE on IO1, 3, 5, 8, 10,
# 11, 13, 15, 16 = pins 3, 5, 7, 10, 13, 14, 16, 18, 19.
_NO_OE_653X = [f"PIN{n}" for n in (4, 6, 12, 15, 17, 20)]
DEVICES["SLG46533"] = Device(
    "SLG46533", 0, {"STQFN20": _gp_package("STQFN20", _slg4653x(), no_oe=_NO_OE_653X,
                                           **_SLG4653X_OPTS)},
    5.0, kind="greenpak", supply="1.8-5 V",
    resources={"lut2_dff": 3, "lut3_dff": 12, "lut3": 6, "lut2": 1, "lut4": 3},
    note="one-time programmable; the most DFFs of these (15)")
DEVICES["SLG46537"] = Device(
    "SLG46537", 0, {"STQFN20": _gp_package("STQFN20", _slg4653x(), no_oe=_NO_OE_653X,
                                           **_SLG4653X_OPTS)},
    5.0, kind="greenpak", supply="1.8-5 V", resources=dict(_SLG4653X),
    note="one-time programmable; asynchronous state machine")
DEVICES["SLG46538"] = Device(
    "SLG46538", 0, {"STQFN20": _gp_package("STQFN20", _slg4653x(vdd2=True), no_oe=_NO_OE_653X,
                                           **_SLG4653X_OPTS)},
    5.0, kind="greenpak", supply="1.8-5 V (VDD2 1.8-5 V, at most VDD)",
    resources=dict(_SLG4653X),
    note="one-time programmable; dual supply; asynchronous state machine")


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


# ---- Altera/Intel MAX 7000S ------------------------------------------------------------
# Pin-compatible with the ATF1502AS/1504AS/1508AS (checked against the pin-out
# diagrams in Altera's MAX 7000 data sheet), so they use the same tables.
for _name, _mc, _fam, _pkgs in (("EPM7032S", 32, "ATF1502", ["PLCC44", "TQFP44"]),
                                ("EPM7064S", 64, "ATF1504", ["PLCC44", "TQFP44", "PLCC84"]),
                                ("EPM7128S", 128, "ATF1508", ["PLCC84"])):
    DEVICES[_name] = Device(_name, _mc, {p: _package(_fam, p) for p in _pkgs}, 5.0,
                            kind="max7000", supply="5 V",
                            note=f"pin-compatible with the {_fam}AS; builds with Quartus II 13.0 SP1")


# ---- Lattice iCE40 (pins from KiCad's FPGA_Lattice library, checked against
# Project IceStorm's I/O list; see ice40pins.py) ---------------------------------------
def _ice40_package(key: str, name: str, sides, footprint: str) -> Package:
    from .ice40pins import ICE40_PINS
    t = ICE40_PINS[key]
    names = {n: v.replace("~{", "").replace("}", "") for n, v in t["names"].items()}
    io = list(t["io"])
    power = {n: ("GND" if v.startswith("GND") else "VCC") for n, v in names.items()
             if n not in io and v.startswith(("GND", "VCC", "VPP", "SPI_VCC"))}
    nc = [n for n, v in names.items() if v == "NC" and n not in io]
    reserved = {v: n for n, v in names.items()
                if n not in io and n not in power and n not in nc}
    out_only = [n for n in io if names[n].startswith("RGB")]    # UP5K LED drivers
    return Package(name, io, {}, {}, power, len(names), nc, out_only=out_only,
                   reserved=reserved, pin_names=names, style="qfn", sides=sides,
                   footprint=footprint)


_TQ144 = "Package_QFP:LQFP-144_20x20mm_P0.5mm"
DEVICES["ICE40HX1K"] = Device(
    "iCE40HX1K", 0, {"TQ144": _ice40_package("iCE40HX1K-TQ144", "TQ144", (36, 36, 36, 36), _TQ144)},
    3.3, kind="ice40", resources={"lut": 1280}, supply="1.2 V core, 3.3 V I/O",
    note="FPGA: 1280 LUTs; I/O is 3.3 V, not 5 V tolerant; loads from SPI flash")
DEVICES["ICE40HX4K"] = Device(
    "iCE40HX4K", 0, {"TQ144": _ice40_package("iCE40HX4K-TQ144", "TQ144", (36, 36, 36, 36), _TQ144)},
    3.3, kind="ice40", resources={"lut": 3520}, supply="1.2 V core, 3.3 V I/O",
    note="FPGA: 3520 LUTs; I/O is 3.3 V, not 5 V tolerant; loads from SPI flash")
DEVICES["ICE40UP5K"] = Device(
    "iCE40UP5K", 0, {"SG48": _ice40_package(
        "iCE40UP5K-SG48", "SG48", (12, 12, 12, 12),
        "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm")},
    3.3, kind="ice40", resources={"lut": 5280}, supply="1.2 V core, 3.3 V I/O",
    note="FPGA: 5280 LUTs; I/O is 3.3 V, not 5 V tolerant; RGB pins 39-41 are LED "
         "drivers (outputs only)")


# ---- Gowin LittleBee (I/O pins from Apicula, names from a KiCad library; see
# gowinpins.py) ------------------------------------------------------------------------
# Pins that configure or program the chip stay out of the I/O list: JTAG (it
# programs the chip), RECONFIG_N, JTAGSEL_N, MODE, DONE and READY.
GOWIN_RESERVED = ("TMS", "TCK", "TDI", "TDO", "JTAGSEL_N", "RECONFIG_N", "MODE0", "MODE1",
                  "MODE2", "DONE", "READY")
# Configuration-port pins that work as ordinary I/O after a gowin_pack switch
GOWIN_CONFIG_PINS = {"SSPI_CS_N", "SO", "SI", "SCLK", "MCLK", "MCS_N", "MO", "MI", "FASTRD_N",
                     "DIN", "DOUT", "CLKHOLD_N", "WE_N", "SDA", "SCL",
                     *(f"D{i}" for i in range(8))}


def _gowin_package(key: str, name: str, sides, footprint: str = "") -> Package:
    from .gowinpins import GOWIN_PINS
    t = GOWIN_PINS[key]
    names = dict(t["names"])
    # Only the A/B pads of each I/O tile: the GW1N-4's extra pads in row 10
    # (IOL10C-J, IOR10C-J) read back from the bitstream as unused inputs even
    # when a design drives them, so they aren't offered until that's understood.
    io = [n for n in t["io"]
          if not set(names[n].split("/")[1:]) & set(GOWIN_RESERVED)
          and re.match(r"IO[LRTB]\d+[AB](/|$)", names[n])]
    # automatic pin assignment takes pins in this order: plain I/O first, then
    # the configuration-port pins (they need a gowin_pack switch; see gowin.py)
    io.sort(key=lambda n: (bool(set(names[n].split("/")[1:]) & GOWIN_CONFIG_PINS), n))
    power = {n: ("GND" if v == "VSS" else "VCC") for n, v in names.items()
             if n not in t["io"] and v.startswith(("VCC", "VSS"))}
    nc = [n for n, v in names.items() if v == "NC"]
    reserved = {v: n for n, v in names.items()
                if n not in io and n not in power and n not in nc}
    return Package(name, io, {}, {}, power, len(names), nc, reserved=reserved,
                   pin_names=names, style="qfn", sides=sides, footprint=footprint)


_LQ144 = "Package_QFP:LQFP-144_20x20mm_P0.5mm"
_GW_NOTE = ("FPGA with on-chip flash: {luts} LUTs; I/O is 3.3 V, not 5 V tolerant; "
            "JTAG pins are kept for programming")
for _name, _luts, _pkgs in (
        ("GW1NZ-1", 1152, {"FN32": ("GW1NZ-1-QN32", (8, 8, 8, 8), "")}),
        ("GW1N-4", 4608, {"QN48": ("GW1N-4-QN48", (12, 12, 12, 12), ""),
                          "QN88": ("GW1N-4-QN88", (22, 22, 22, 22), ""),
                          "LQ144": ("GW1N-4-LQ144", (36, 36, 36, 36), _LQ144)}),
        ("GW1N-9", 8640, {"QN48": ("GW1N-9-QN48", (12, 12, 12, 12), ""),
                          "QN88": ("GW1N-9-QN88", (22, 22, 22, 22), ""),
                          "LQ144": ("GW1N-9-LQ144", (36, 36, 36, 36), _LQ144)}),
        ("GW1NR-9", 8640, {"QN88P": ("GW1NR-9-QN88P", (22, 22, 22, 22), "")})):
    DEVICES[_name] = Device(
        _name, 0, {p: _gowin_package(k, p, s, fp) for p, (k, s, fp) in _pkgs.items()},
        3.3, kind="gowin", resources={"lut": _luts},
        supply="LV: 1.2 V core; UV: one 2.5/3.3 V supply; 3.3 V I/O",
        note=_GW_NOTE.format(luts=_luts))


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
