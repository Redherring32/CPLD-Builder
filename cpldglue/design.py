"""Design model plus loaders (KiCad netlist, text netlist, JSON project).

A Design is the set of chips that go into the CPLD and the nets that
connect their pins. A net is `external` when it also reaches something
outside the CPLD (it then needs a pin). Power nets carry a constant.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import chips

GND_NAMES = re.compile(r"^/?(GND|VSS|DGND|AGND|0)$", re.I)
VCC_NAMES = re.compile(r"^/?(VCC|VDD|\+5V|\+3V3|\+3\.3V|5V|1)$", re.I)
AUTO_NET = re.compile(r"^(Net-\(|unconnected-\()")


@dataclass
class Node:
    ref: str
    pin: str


@dataclass
class Net:
    name: str
    nodes: List[Node] = field(default_factory=list)
    external: bool = False         # also connects to something outside the CPLD
    const: Optional[int] = None    # 0 or 1 for power nets
    named: bool = True             # user-named (False for KiCad auto names)


@dataclass
class Design:
    name: str = "glue"
    parts: Dict[str, str] = field(default_factory=dict)    # ref -> library key
    nets: Dict[str, Net] = field(default_factory=dict)
    device: str = "ATF1502AS"
    package: str = "PLCC44"
    pin_locks: Dict[str, int] = field(default_factory=dict)
    keep_jtag: bool = True
    # Free-form data for the GUI (positions etc.); ignored by the generator.
    layout: Dict[str, dict] = field(default_factory=dict)
    # Variants: boards with "fit one of" chips. Each variant names the
    # optional chips fitted in it; chips in no variant are always fitted.
    #   variant_mode "build": one design per variant (one .jed each, same pins)
    #   variant_mode "pins":  all variants in one CPLD, chosen by VAR_SEL pins
    variants: Dict[str, List[str]] = field(default_factory=dict)
    variant_mode: str = "build"
    variant: str = ""               # the variant shown / simulated in build mode
    variant_of: str = ""            # set on a design reduced to one variant

    # ---------------- variants ----------------
    def optional_refs(self) -> Dict[str, List[str]]:
        """Optional chip -> the variants it is fitted in."""
        out: Dict[str, List[str]] = {}
        for v, refs in self.variants.items():
            for ref in refs:
                out.setdefault(ref, []).append(v)
        return out

    def active_variant(self) -> str:
        if self.variant in self.variants:
            return self.variant
        return next(iter(self.variants), "")

    def for_variant(self, name: str) -> "Design":
        """This design as fitted in one variant: other optional chips removed."""
        if name not in self.variants:
            raise ValueError(f"no variant {name!r}; variants: {', '.join(self.variants)}")
        drop = set(self.optional_refs()) - set(self.variants[name])
        d = Design.from_json(self.to_json())
        d.parts = {r: k for r, k in d.parts.items() if r not in drop}
        for net in d.nets.values():
            net.nodes = [n for n in net.nodes if n.ref not in drop]
        d.variants, d.variant, d.variant_of = {}, "", name
        return d

    # ---------------- JSON project files ----------------
    def to_json(self) -> str:
        d = asdict(self)
        d["format"] = "cpldglue-project-1"
        return json.dumps(d, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Design":
        d = json.loads(text)
        d.pop("format", None)
        nets = {k: Net(name=v["name"], nodes=[Node(**n) for n in v["nodes"]],
                       external=v.get("external", False), const=v.get("const"),
                       named=v.get("named", True))
                for k, v in d.pop("nets", {}).items()}
        return cls(nets=nets, **d)

    def save(self, path) -> None:
        Path(path).write_text(self.to_json(), encoding="utf-8")


def load(path) -> Design:
    """Load a .json project or a .cg text netlist."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        return Design.from_json(text)
    return parse_text(text, default_name=p.stem)


# ---------------------------------------------------------------------------
# Text netlist (.cg)
# ---------------------------------------------------------------------------
#   design  NAME
#   device  ATF1502AS PLCC44
#   jtag    off                    (free the JTAG pins for I/O)
#   part    U7 74HC139
#   net     CPU_A13 ext: U7.2      ("ext" = also goes off-chip)
#   net     GND: U7.8 U7.15        (GND/VCC names become constants)
#   pin     CPU_A13 12             (lock a signal to a pin)
#   layout  U7 120 40              (GUI position of a chip)
#   variant AxROM: U4A             (a variant and the optional chips it fits)
#   variant-select pins            ("build": one .jed per variant; "pins": VAR_SEL pins)
#   variant-active AxROM           (the variant shown in build mode)
# Extra net flags: "auto" (unlabelled net), "const=0" / "const=1".
# '#' starts a comment.
def _strip_comment(raw: str) -> str:
    """Drop a trailing '# comment', ignoring '#' inside "quoted" names."""
    quoted = False
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and quoted:
            i += 2
            continue
        if c == '"':
            quoted = not quoted
        elif c == "#" and not quoted:
            return raw[:i]
        i += 1
    return raw


def _take_name(rest: str):
    """Split a possibly "quoted" net name off the front of rest."""
    if not rest.startswith('"'):
        name, _, tail = rest.partition(" ")
        if ":" in name:                       # "net X:" written without a space
            name, _, more = name.partition(":")
            tail = ":" + more + (" " + tail if tail else "")
        return name, tail
    out, i = [], 1
    while i < len(rest):
        c = rest[i]
        if c == "\\" and i + 1 < len(rest):
            out.append(rest[i + 1])
            i += 2
            continue
        if c == '"':
            return "".join(out), rest[i + 1:]
        out.append(c)
        i += 1
    raise ValueError("unterminated quoted net name")


def _quote_name(name: str) -> str:
    if name and not re.search(r'[\s:#"\\]', name):
        return name
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_text(text: str, default_name: str = "glue") -> Design:
    d = Design(name=default_name)
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        word, _, rest = line.partition(" ")
        rest = rest.strip()
        try:
            if word == "design":
                d.name = rest
            elif word == "device":
                d.device, d.package = rest.split()
            elif word == "jtag":
                d.keep_jtag = rest.lower() not in ("off", "no", "false", "0")
            elif word == "part":
                ref, value = rest.split(None, 1)
                part = chips.lookup(value)
                if part is None:
                    raise ValueError(f"unknown part {value!r}")
                d.parts[ref] = part.key
            elif word == "net":
                name, tail = _take_name(rest)
                if not name:
                    raise ValueError("net needs a name")
                head, sep, nodes = tail.partition(":")
                if not sep:
                    raise ValueError("expected ':' before the pin list")
                flags = set(head.split())
                unknown = flags - {"ext", "auto", "const=0", "const=1"}
                if unknown:
                    raise ValueError(f"unknown net flag(s) {', '.join(sorted(unknown))}")
                net = d.nets.setdefault(name, Net(name))
                net.external |= "ext" in flags
                net.named = "auto" not in flags
                for tok in nodes.split():
                    ref, _, pin = tok.partition(".")
                    net.nodes.append(Node(ref, pin))
                _classify_power(net)
                if "const=0" in flags:
                    net.const = 0
                elif "const=1" in flags:
                    net.const = 1
            elif word == "pin":
                sig, pin = rest.split()
                d.pin_locks[sig] = int(pin)
            elif word == "layout":
                ref, x, y = rest.split()[:3]
                d.layout[ref] = {"x": float(x), "y": float(y)}
            elif word == "variant":
                name, tail = _take_name(rest)
                head, sep, refs = tail.partition(":")
                if not name or not sep:
                    raise ValueError("expected: variant NAME: REF REF ...")
                d.variants[name] = refs.split()
            elif word == "variant-select":
                if rest not in ("build", "pins"):
                    raise ValueError("variant-select is 'build' or 'pins'")
                d.variant_mode = rest
            elif word == "variant-active":
                d.variant = _take_name(rest)[0]
            else:
                raise ValueError(f"unknown keyword {word!r}")
        except ValueError as e:
            raise ValueError(f"line {lineno}: {e}") from None
    return d


def to_text(d: Design) -> str:
    """Write a Design as a .cg text netlist (round-trips with parse_text)."""
    out = ["# cpldglue netlist", f"design  {d.name}", f"device  {d.device} {d.package}"]
    if not d.keep_jtag:
        out.append("jtag    off")
    out.append("")
    for ref, key in d.parts.items():
        out.append(f"part {ref} {key}")
    out.append("")
    for net in d.nets.values():
        if not net.name:
            raise ValueError("a net has an empty name")
        flags = []
        if net.external:
            flags.append("ext")
        if not net.named:
            flags.append("auto")
        probe = Net(net.name)
        _classify_power(probe)
        if net.const is not None and probe.const != net.const:
            flags.append(f"const={net.const}")
        nodes = " ".join(f"{n.ref}.{n.pin}" for n in net.nodes)
        out.append(f"net {' '.join([_quote_name(net.name)] + flags)}: {nodes}")
    if d.variants:
        out.append("")
        out += [f"variant {_quote_name(v)}: {' '.join(refs)}" for v, refs in d.variants.items()]
        out.append(f"variant-select {d.variant_mode}")
        if d.variant:
            out.append(f"variant-active {_quote_name(d.variant)}")
    if d.pin_locks:
        out.append("")
        out += [f"pin {sig} {pin}" for sig, pin in d.pin_locks.items()]
    if d.layout:
        out.append("")
        for ref, pos in d.layout.items():
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                out.append(f"layout {ref} {pos['x']:g} {pos['y']:g}")
    return "\n".join(out) + "\n"


def save(d: Design, path) -> None:
    """Save in the format given by the file extension (.json or .cg)."""
    p = Path(path)
    text = d.to_json() if p.suffix.lower() == ".json" else to_text(d)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def _classify_power(net: Net) -> None:
    if GND_NAMES.match(net.name):
        net.const = 0
    elif VCC_NAMES.match(net.name):
        net.const = 1


# ---------------------------------------------------------------------------
# KiCad
# ---------------------------------------------------------------------------
def find_kicad_cli() -> Optional[str]:
    exe = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
    if exe:
        return exe
    for base in (Path("C:/Program Files/KiCad"), Path("/Applications/KiCad")):
        if base.is_dir():
            hits = sorted(base.glob("*/bin/kicad-cli*"), reverse=True)
            if hits:
                return str(hits[0])
    return None


def export_kicad_netlist(sch: Path, out: Path) -> None:
    exe = find_kicad_cli()
    if exe is None:
        raise RuntimeError("kicad-cli not found; set KICAD_CLI or pass a .net file")
    r = subprocess.run([exe, "sch", "export", "netlist", "--format", "kicadsexpr",
                        "-o", str(out), str(sch)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"kicad-cli failed:\n{r.stdout}{r.stderr}")


def _sexpr(text: str):
    tok = re.findall(r'[()]|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    stack: list = [[]]
    for t in tok:
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return stack[0][0]


def _get(lst, key):
    return [x for x in lst if isinstance(x, list) and x and x[0] == key]


def _val(lst, key):
    g = _get(lst, key)
    return g[0][1] if g and len(g[0]) > 1 else None


def read_kicad_netlist(path: Path) -> Tuple[Dict[str, str], Dict[str, List[Node]]]:
    """Return ({ref: value}, {net name: [nodes]}) from a kicadsexpr netlist."""
    root = _sexpr(path.read_text(encoding="utf-8"))
    comps = {_val(c, "ref"): _val(c, "value") or ""
             for c in _get(_get(root, "components")[0], "comp")}
    nets = {}
    for n in _get(_get(root, "nets")[0], "net"):
        nets[_val(n, "name")] = [Node(_val(x, "ref"), _val(x, "pin"))
                                 for x in _get(n, "node")]
    return comps, nets


def from_kicad(source, refs: List[str], name: str = "glue",
               part_overrides: Optional[Dict[str, str]] = None) -> Design:
    """Build a Design from a KiCad schematic (.kicad_sch) or netlist (.net)
    using only the listed component references."""
    source = Path(source)
    if source.suffix == ".kicad_sch":
        with tempfile.TemporaryDirectory() as tmp:
            net = Path(tmp) / "export.net"
            export_kicad_netlist(source, net)
            comps, knets = read_kicad_netlist(net)
    else:
        comps, knets = read_kicad_netlist(source)

    return design_from_netlist(comps, knets, refs, name, part_overrides)


def design_from_netlist(comps: Dict[str, str], knets: Dict[str, List[Node]],
                        refs: List[str], name: str = "glue",
                        part_overrides: Optional[Dict[str, str]] = None) -> Design:
    """Build a Design from a read KiCad netlist, using only the listed refs."""
    d = Design(name=name)
    overrides = part_overrides or {}
    for ref in refs:
        if ref not in comps:
            raise ValueError(f"{ref} is not in the schematic")
        value = overrides.get(ref) or comps[ref]
        part = chips.lookup(value)
        if part is None:
            raise ValueError(f"{ref}: no library model for {value!r} "
                             f"(use --part {ref}=74xNNN to override)")
        d.parts[ref] = part.key

    sel = set(refs)
    for nname, nodes in knets.items():
        inside = [n for n in nodes if n.ref in sel]
        if not inside:
            continue
        outside = [n for n in nodes if n.ref not in sel]
        net = Net(nname, inside, external=bool(outside),
                  named=not AUTO_NET.match(nname))
        _classify_power(net)
        if net.const is None:
            # A net touching a chip power pin is a power net.
            for n in inside:
                pin = chips.LIBRARY[d.parts[n.ref]].pins.get(n.pin)
                if pin is not None and pin.kind in ("gnd", "vcc"):
                    net.const = 0 if pin.kind == "gnd" else 1
                    break
        d.nets[nname] = net
    return d
