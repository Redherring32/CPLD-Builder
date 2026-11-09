"""cpldglue command line.

  python -m cpldglue parts
  python -m cpldglue kicad SCHEMATIC --refs U7 U8 U9 -o build/glue [options]
  python -m cpldglue gen   PROJECT(.json|.cg) -o build/glue [options]
  python -m cpldglue build PROJECT -o build/glue --flow-dir PATH [--fitter-dir PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import chips, design as dsg, devices, generate, yosys


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-o", "--out", required=True, type=Path, help="output folder")
    p.add_argument("--device", help="e.g. ATF1502AS, ATF1504ASV, ATF1508AS (see `devices`)")
    p.add_argument("--package", help="e.g. PLCC44, TQFP44, PLCC84, TQFP100 (see `devices`)")
    p.add_argument("--name", help="design / top module name")
    p.add_argument("--lock", action="append", default=[], metavar="SIGNAL=PIN",
                   help="lock a signal to a pin (repeatable)")
    p.add_argument("--pins", type=Path, metavar="FILE",
                   help="lock pins from a .pin file (e.g. one saved earlier)")
    p.add_argument("--no-jtag", action="store_true",
                   help="use the 4 JTAG pins as I/O (no in-circuit reprogramming)")
    p.add_argument("--variant", help="variant to generate / build (default: build "
                                      "every variant; see `variant` lines in .cg files)")
    p.add_argument("--variant-select", choices=["build", "pins"],
                   help="variants: one design per variant, or all in one chosen by VAR_SEL pins")
    p.add_argument("--check", action="store_true",
                   help="also run a generic Yosys synthesis as a sanity check")


def _apply(d: dsg.Design, a) -> None:
    if a.device:
        d.device = a.device.upper()
    if a.package:
        d.package = a.package.upper()
    if a.name:
        d.name = a.name
    if a.no_jtag:
        d.keep_jtag = False
    if a.pins:
        d.pin_locks.update(devices.parse_pin_file(a.pins.read_text(encoding="utf-8")))
    for item in a.lock:
        sig, _, pin = item.partition("=")
        d.pin_locks[sig] = int(pin)


def _apply_variant(d: dsg.Design, a) -> None:
    if getattr(a, "variant_select", None):
        d.variant_mode = a.variant_select
    if getattr(a, "variant", None):
        if a.variant not in d.variants:
            raise ValueError(f"no variant {a.variant!r}; variants: {', '.join(d.variants) or 'none'}")
        d.variant = a.variant


def _emit(d: dsg.Design, a) -> int:
    a.out.mkdir(parents=True, exist_ok=True)
    r = generate.generate(d)
    top = generate.sanitize(d.name)
    report = r.report(d)
    (a.out / "report.txt").write_text(report, encoding="utf-8")
    print(report, end="")
    if not r.verilog:
        return 1
    (a.out / f"{top}.v").write_text(r.verilog, encoding="utf-8")
    (a.out / f"{top}.pin").write_text(r.pin_file(d), encoding="utf-8")
    d.save(a.out / f"{top}.json")
    print(f"Wrote {a.out / (top + '.v')}, {top}.pin, {top}.json, report.txt")
    if a.check:
        print(yosys.check_synth(a.out / f"{top}.v", top, a.out / "check"))
    return 0 if r.ok else 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (["_nextpnr-ice40"], ["_icepack"]):   # internal: downloaded iCE40 tools
        from . import deps
        return deps.run_ice40_tool(argv[0][1:], argv[1:])
    if argv[:1] == ["_yosys"]:                # internal: run the downloaded Yosys
        from . import deps
        return deps.run_yosys(argv[1:])
    ap = argparse.ArgumentParser(prog="cpldglue",
                                 description="Merge 74xx/4000 chips into an ATF15xx CPLD.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("parts", help="list library parts")

    devp = sub.add_parser("devices", help="list devices and packages")

    k = sub.add_parser("kicad", help="import chips from a KiCad schematic or netlist")
    k.add_argument("source", type=Path, help=".kicad_sch or kicadsexpr .net file")
    k.add_argument("--refs", nargs="+", required=True, help="references to merge")
    k.add_argument("--part", action="append", default=[], metavar="REF=PART",
                   help="override a part value, e.g. U8=74x368")
    _common(k)

    g = sub.add_parser("gen", help="generate from a .json project or .cg netlist")
    g.add_argument("project", type=Path)
    _common(g)

    b = sub.add_parser("build", help="generate, then Yosys -> EDIF -> fitter -> .jed")
    b.add_argument("project", type=Path)
    b.add_argument("--flow-dir", type=Path,
                   help="checkout of github.com/hoglet67/atf15xx_yosys "
                        "(default: the copy from `cpldglue setup flow`)")
    b.add_argument("--fitter-dir", type=Path, help="folder with fit1502.exe etc.")
    b.add_argument("--speed", type=int, default=15, help="tpd grade (default 15)")
    _common(b)

    gu = sub.add_parser("gui", help="open the browser editor on a project")
    gu.add_argument("project", type=Path, help=".json project or .cg netlist")
    gu.add_argument("--port", type=int, default=8765)
    gu.add_argument("--no-browser", action="store_true")
    gu.add_argument("--flow-dir", type=Path,
                    help="atf15xx_yosys checkout (default: the downloaded copy)")
    gu.add_argument("--fitter-dir", type=Path, help="folder with fit1502.exe etc.")

    ks = sub.add_parser("kicad-symbol", help="KiCad symbol of the CPLD, wired with net labels")
    ks.add_argument("project", type=Path)
    ks.add_argument("-o", "--out", type=Path, default=Path("."),
                    help="folder for NAME.kicad_sym and NAME-paste.txt (default: here)")
    ks.add_argument("--copy", action="store_true",
                    help="also put the schematic snippet on the clipboard")

    gp = sub.add_parser("greenpak", help="GreenPAK: check the LUT/DFF fit and write the "
                                          "sheet for Go Configure")
    gp.add_argument("project", type=Path)
    _common(gp)

    st = sub.add_parser("setup", help="show optional tools, or download them")
    st.add_argument("what", nargs="*", metavar="{yosys,flow,fitter,nextpnr}",
                    help="what to download (nothing = just show status)")

    a = ap.parse_args(argv)
    if a.cmd == "setup":
        from . import deps
        bad = [w for w in a.what if w not in deps.FETCHERS]
        if bad:                       # (argparse choices + nargs="*" breaks on 3.9)
            ap.error(f"setup: unknown {', '.join(bad)}; choose from yosys, flow, fitter, "
                     f"nextpnr")
        for name in a.what:
            def progress(done, total, msg, _last=[0]):
                pct = f"{100 * done // total}%" if total else f"{done // 1024} KB"
                if done - _last[0] > (1 << 20) or done == total:
                    _last[0] = done
                    print(f"\r{msg}: {pct}   ", end="", flush=True)
            try:
                print("\n" + deps.FETCHERS[name](progress))
            except Exception as e:
                print(f"\n{name}: {e}")
                return 1
        for d in deps.status():
            mark = "found" if d["found"] else "missing"
            print(f"{d['title']:<40} {mark:<8} {d['where'] or d['download']}")
        return 0
    if a.cmd == "greenpak":
        from . import greenpak
        d = dsg.load(a.project)
        _apply(d, a)
        _apply_variant(d, a)
        try:
            r = generate.generate(d)
            m = greenpak.map_design(d, r, a.out / "greenpak-work")
        except (ValueError, KeyError, RuntimeError) as err:
            print(f"error: {err}", file=sys.stderr)
            return 2
        for t, n in m.fit.total.items():
            print(f"{greenpak.SLOT_TITLES[t]:<24} {m.fit.used[t]:>3} / {n}")
        print(("Fits." if m.fit.ok else "Does NOT fit:") + "".join(f"\n  no room for {u}" for u in m.fit.unplaced))
        for n in m.notes:
            print(f"note: {n}")
        out = a.out / f"{generate.sanitize(d.name)}-greenpak.html"
        out.write_text(greenpak.sheet_html(d, r, m), encoding="utf-8")
        print(f"Wrote {out}")
        return 0 if m.fit.ok else 1
    if a.cmd == "kicad-symbol":
        from . import kicad_symbol
        try:
            e = kicad_symbol.build(dsg.load(a.project))
        except (ValueError, KeyError) as err:
            print(f"error: {err}", file=sys.stderr)
            return 2
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / f"{e.name}.kicad_sym").write_text(e.library, encoding="utf-8")
        (a.out / f"{e.name}-paste.txt").write_text(e.clipboard, encoding="utf-8")
        print(f"Wrote {a.out / (e.name + '.kicad_sym')} (symbol library) and "
              f"{e.name}-paste.txt (paste into a schematic: {e.labels} labels)")
        for w in e.warnings:
            print(f"note: {w}")
        if a.copy:
            from .app import copy_to_clipboard
            print("Copied to the clipboard." if copy_to_clipboard(e.clipboard)
                  else "Could not reach the clipboard; use the -paste.txt file.")
        return 0
    if a.cmd == "gui":
        from .gui.server import serve
        serve(a.project, a.port, not a.no_browser, a.flow_dir, a.fitter_dir)
        return 0
    try:
        if a.cmd == "parts":
            for p in chips.LIBRARY.values():
                print(f"{p.key:<8} {p.package:<7} {p.title}")
            return 0
        if a.cmd == "devices":
            for dev in devices.DEVICES.values():
                if dev.kind == "ice40":
                    print(f"{dev.name:<12} iCE40 FPGA, {dev.resources.get('lut')} LUTs, {dev.supply}")
                elif dev.kind == "gal":
                    print(f"{dev.name:<12} GAL, {dev.macrocells} output macrocells, {dev.supply}")
                elif dev.kind == "greenpak":
                    cells = ", ".join(f"{n} {t}" for t, n in dev.resources.items())
                    print(f"{dev.name:<12} GreenPAK ({cells}), {dev.supply}")
                else:
                    print(f"{dev.name:<12} {dev.macrocells:>3} macrocells, {dev.vcc:g} V")
                for pkg in dev.packages.values():
                    extra = []
                    if pkg.jtag:
                        extra.append("4 are JTAG")
                    if pkg.out_only:
                        extra.append(f"{len(pkg.out_only)} output-only")
                    if pkg.no_oe:
                        extra.append(f"{len(pkg.no_oe)} without output enable")
                    print(f"    {pkg.name:<8} {len(pkg.io):>2} I/O"
                          + (f" ({', '.join(extra)})" if extra else "")
                          + f" + {len(pkg.inputs)} input-only")
            return 0
        if a.cmd == "kicad":
            overrides = dict(x.split("=", 1) for x in a.part)
            d = dsg.from_kicad(a.source, a.refs, name=a.name or "glue",
                               part_overrides=overrides)
        else:
            d = dsg.load(a.project)
        _apply(d, a)
        _apply_variant(d, a)
        every = (a.cmd == "build" and d.variants and d.variant_mode != "pins"
                 and not a.variant)
        if every:                      # one build per variant, same pins in each
            from .gui import api
            from . import deps
            res = api.Builder(a.flow_dir or deps.flow_dir(), a.fitter_dir).build(d, a.out)
            print(res["log"])
            return 0 if res["ok"] else 1
        rc = _emit(d, a)
        dev = devices.DEVICES.get(d.device.upper())
        if a.cmd == "build" and rc == 0 and dev is not None and dev.kind in ("ice40", "max7000"):
            from .gui import api
            res = api.Builder(None, None).build(d, a.out)
            print(res["log"])
            return 0 if res["ok"] else 1
        if a.cmd == "build" and rc == 0 and dev is not None and dev.kind == "gal":
            from . import gal
            top = generate.sanitize(d.name)
            b = gal.build(d, generate.generate(d), a.out / "gal-work")
            for line in gal.report_lines(b, d.device):
                print(line)
            if not b.fit.ok:
                return 1
            files = gal.write_files(b, d, a.out, top)
            print("Wrote " + ", ".join(f.name for f in files) + f" in {a.out}")
            return 0 if b.ok else 1
        if a.cmd == "build" and rc == 0:
            from . import deps
            flow = a.flow_dir or deps.flow_dir()
            if flow is None:
                raise RuntimeError("no atf15xx_yosys files: pass --flow-dir or run "
                                   "`cpldglue setup flow`")
            top = generate.sanitize(d.name)
            print(yosys.run_atf_flow(top, a.out, d.device, d.package,
                                     flow, a.fitter_dir, a.speed))
        return rc
    except (ValueError, RuntimeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
