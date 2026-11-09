# cpldglue

Merge 74-series and CD4000-series glue logic into one Microchip ATF15xx
CPLD. You pick the chips; cpldglue reads how they are wired (from a
KiCad schematic or a small text netlist) and generates:

- one self-contained Verilog file (top level plus the chip models it uses),
- a pin assignment (`.pin` file and `//PIN:` comments),
- a report: pins used, internal nets, warnings,
- optionally an EDIF netlist and a `.jed` via the Yosys + Microchip fitter flow.

Nets that only join chips together become internal wires and use no pins.
Tied-high/low inputs become constants. Unused gates are left out: a gate
whose output goes nowhere costs no logic, and its inputs get no CPLD pins.

## Desktop app

Download `CPLD-Builder-<version>-windows-x64.zip` or
`CPLD-Builder-<version>-linux-x64.tar.gz` from the GitHub release (or the
Actions run's artifacts), unpack it and run `CPLD-Builder` (Linux: run
`./install.sh` once for a menu entry). No Python needed. It opens the editor
below in its own window; **Open…**, **Recent** and **Save as…** pick projects,
and it reopens the last one.

**Setup…** in the toolbar lists the optional tools and downloads them on
request, each checked against a fixed SHA-256 checksum and kept in your user
folder (`%LOCALAPPDATA%\cpldglue` or `~/.local/share/cpldglue`):

| Tool | For | Download |
|---|---|---|
| Yosys (yowasp-yosys, WebAssembly) | Simulate, synthesis check, Build | ~25 MB from PyPI |
| atf15xx_yosys flow files | Build | ~30 KB from GitHub (pinned commit) |
| Microchip fitters | Build (the `.jed`) | ProChip 5.0.1, 224 MB from microchip.com; the app opens Microchip's installer, which you run (and accept its licence). Linux needs Wine. |
| KiCad | Import KiCad… | not downloaded; install KiCad 7+ |

The same from the command line: `cpldglue setup` shows the status,
`cpldglue setup yosys flow fitter` downloads.

Building the app yourself: `pip install -r packaging/requirements-build.txt`,
then `python packaging/build.py` (on the platform you're building for). The
GitHub workflow `.github/workflows/build.yml` does this for Windows
and Linux on every push, and attaches both to a release when you push a tag
like `v0.2.0`.

## Install (from source)

Python 3.9 or newer. For simulation and builds, either let **Setup…** /
`cpldglue setup yosys` download Yosys, or install it yourself:

```bash
pip install yowasp-yosys
```

A native `yosys` on your PATH works too. To import KiCad schematics directly,
KiCad 7+ must be installed (`kicad-cli` is found automatically on Windows).

## Editor (GUI)

```bash
python -m cpldglue gui examples/tinytendo.cg
```

This opens a local editor in your browser. The project file can be a `.cg`
netlist or a `.json` project, and it may not exist yet: `gui myboard.cg`
starts empty and Save creates it. Only Python is needed. The page is
pre-built into `cpldglue/gui/static/` and served from 127.0.0.1.

- **Chips view.** Each chip shows the gates inside it: gate symbols wired
  to their pins for simple logic and buffers, labelled blocks for
  flip-flops, decoders, counters and shift registers. Single-gate parts
  (74x1G...) are drawn as just their logic symbol, with bubbles for
  inverted outputs and active-low enables. Gates the design
  doesn't use are faded; they are left out of the CPLD. Drag parts in
  from the library, then drag from pin to pin
  to wire them. Click a net label to rename it, mark it as going off-chip
  (needs a CPLD pin), or make it a constant. Right-click a pin to tie it
  high/low or make it a CPLD pin. Pins with problems in the report are
  underlined. Undo/redo, Tidy (re-grid), optional wire drawing, Ctrl+S to
  save. Press `?` for all shortcuts.
- **Pinout view.** A drawing of the package with JTAG, power and
  input-only pins marked. Drag a signal onto a pin (or select it and click
  a free pin) to lock it. *Lock all* freezes the current assignment before
  PCB layout. Locks are saved in the project and round-trip through `.pin`
  files.
- **Copy for KiCad** (pinout view). Copies the CPLD to the clipboard as a
  KiCad symbol already wired up, in the style of the TinyTendo schematic:
  a short wire on each pin with a local net label naming its net, VCC/GND
  labels on the power pins (+3V3 for ASV parts), TDI/TMS/TCK/TDO labels for
  the programming header, unused dedicated inputs tied to GND, and
  no-connect flags on unused I/O. Paste it into a schematic with Ctrl+V; the
  labels join the nets of the same name. The symbol uses the package's
  standard KiCad footprint. If the clipboard is blocked, a box shows the
  text to copy by hand.
- **Macrocell bar** (top of the report panel). How much of the device the
  design uses, split by chip, with a list of what each chip costs: one
  macrocell per output pin it drives (bus pins shared between chips are split)
  plus one per flip-flop or latch that doesn't sit at its own pin. Each chip
  in the chip view shows its share too. It's an estimate; the fitter report has
  the real figure.
- **Report / Verilog / Pin file tabs.** The same output as the command
  line, updated on every edit.
- **Simulate tab.** Switches for inputs, lights for outputs (Z = released
  or unknown), pulse buttons, a free-running clock, and a waveform of the
  last 64 steps. Net values also show on the chip view. Needs Yosys.
- **Import KiCad…** Lists schematics near the project. Tick chips and
  watch the pin count before importing. Undo restores the previous chips.
- **Build…** Runs the same flow as `cpldglue build` and writes to `build/`
  next to the project. It uses the tools from **Setup…** (or `--flow-dir` /
  `--fitter-dir` given to `cpldglue gui`) and says what's missing.

If the project file changes on disk while the editor is open, the editor
reloads it, or asks first when you have unsaved edits.

To work on the editor itself: `cd cpldglue/gui/frontend`, `npm install`,
then `npm run dev` (with `python -m cpldglue gui PROJECT --no-browser`
running), `npm test`, and `npm run build` to refresh `static/`.

## Command line

List the supported parts and devices:

```bash
python -m cpldglue parts
```

```bash
python -m cpldglue devices
```

Import chips straight from a KiCad schematic:

```bash
python -m cpldglue kicad path/to/TinyTendo-schematic.kicad_sch --refs U7 U8 U9 --name tinytendo_glue --device ATF1502AS --package PLCC44 -o build/tinytendo --check
```

Or describe the wiring by hand (see [examples/tinytendo.cg](examples/tinytendo.cg)):

```bash
python -m cpldglue gen examples/tinytendo.cg -o build/tinytendo
```

Either way, `build/tinytendo/tinytendo_glue.json` is a project file you can
edit and feed back to `gen`. Useful options:

| Option | Meaning |
|---|---|
| `--lock SIGNAL=PIN` | pin a signal to a pin (repeatable) |
| `--pins FILE` | lock pins from a `.pin` file, or a generated `.v` (its `//PIN:` lines) |
| `--device`, `--package` | target part, e.g. `--device ATF1504AS --package PLCC84` |
| `--no-jtag` | use the 4 JTAG pins as I/O (loses in-circuit programming) |
| `--part U8=74x368` | override a schematic value cpldglue can't recognise |
| `--check` | run a generic Yosys synthesis as a sanity check |

### KiCad symbol

```bash
python -m cpldglue kicad-symbol build/tinytendo/tinytendo_glue.json -o kicad --copy
```

Writes `NAME.kicad_sym` (a one-symbol library to add to your project) and
`NAME-paste.txt` (the wired-up snippet that **Copy for KiCad** puts on the
clipboard); `--copy` also copies the snippet. Nets KiCad named
automatically (`Net-(U7-Pad2)`) get a note: label them in the schematic so
the pasted label joins them.

### Building a .jed

```bash
python -m cpldglue build build/tinytendo/tinytendo_glue.json -o build/tinytendo
```

It uses the flow files and fitters from `cpldglue setup flow fitter`. To use
your own copies instead, pass `--flow-dir` (a checkout of
<https://github.com/hoglet67/atf15xx_yosys>: cells.lib, techmap.v) and
`--fitter-dir` (the folder with `fit1502.exe` … and `aprim.lib` from
Microchip's ProChip or WinCUPL).

Every build checks its result:
- **Pins:** the fitter's placement (`NAME.fit`) is compared with the pins
  cpldglue assigned; a moved pin stops the build, since the board would not
  match.
- **Logic** (combinational designs): the fitter's final equations
  (`NAME.tt3`) are evaluated on random inputs and compared with the
  simulator, which checks the whole chain: cpldglue's Verilog, Yosys and the
  fitter. Designs with flip-flops are not checked this way yet.

Tested with Microchip's fitters (`fit1502/1504/1508.exe`, ProChip 5.0.1) on
the TinyTendo glue (ATF1502AS, ATF1504AS, ATF1508AS) and a discrete-mapper
cartridge in every variant. Two things the reference flow gets wrong are
handled: the fitter needs its `atmel.std` in the folder it runs in (else
"Checking Extra wiring failed"), and 3-state output pins must use the
bidirectional pad (`bibuf`), not `TRI` (else "INTERNAL ERROR").

cpldglue passes the AS or ASV name (an ASL/ASVL part builds as AS/ASV, as
the fitter's own help lists only those) and the package name, e.g.
`-tech ATF1504AS -device PLCC84`.

## Variants: "fit one of" boards

Some boards take one of several chips in the same place, chosen by the
build (the MouseBite Labs discrete-mapper cartridge fits a 74x377 *or* one
of two 74x161s, depending on the mapper). The import dialog spots these
(their outputs drive the same nets) and offers **Keep all as variants**;
**Variants…** in the toolbar edits them: name each variant and tick the
chips it fits (chips in no variant are always fitted). Two ways to use them:

- **One build per variant.** Build makes one `.jed` per variant, each in its
  own folder, with every signal on the same pin in all of them (one board,
  one socket: program the file for the mapper you want). The toolbar picks
  the variant shown, simulated and reported.
- **Select pins.** Every variant goes into the CPLD; `VAR_SEL0`,
  `VAR_SEL1`... input pins choose one (wire them to jumpers or solder pads to
  GND/VCC; the report lists each variant's code). An optional chip's outputs
  only drive while its variant is selected. Uses more of the chip: the
  mapper above needs 26 pins on an ATF1504AS rather than 16-24.

In a `.cg` file:

```
variant AxROM: U4A
variant UxROM: U4B
variant CNROM: U4C
variant-select build        # or: pins
variant-active UxROM        # the variant shown in build mode
```

On the command line, `build` makes every variant (or `--variant NAME`), and
`--variant-select pins|build` overrides the project's choice.

## GreenPAK (design and check)

The Renesas SLG46826 and SLG46620 (TSSOP-20 and STQFN-20) are supported as
design-and-check targets: pin assignment knows each pin's limits (output-only
pins, pins without an output enable, the SLG46826's I2C pins), and the report
panel maps the logic onto the part's LUTs and DFFs with Yosys and shows
whether it fits. There is no open tool chain that programs GreenPAKs, so
**LUT sheet…** prints every LUT's truth table, the DFFs and the pins, to
enter in Renesas Go Configure. `cpldglue greenpak project.cg -o out` does the
same from the command line.

## GAL16V8 / GAL22V10

Small glue (a decoder, a few gates and buffers, a counter) also fits a
GAL16V8 (DIP20 / PLCC20) or GAL22V10 (DIP24 / PLCC28), or the pin-compatible
Microchip ATF16V8B / ATF22V10C. cpldglue fits the design and writes the
`.jed` itself; only Yosys is needed, no vendor tools.

- **GAL panel** (report panel): one tile per output macrocell (OLMC) with
  its product terms used of the ones it has, the GAL16V8 mode, and a check that
  the fuse map behaves like the design. **Use the fitted pins** locks the pins
  the GAL needs (clock on pin 1, /OE on pin 11, big outputs on the 22V10's
  larger OLMCs). **Equations…** shows them as a galette/GALasm `.pld`.
- **Build** (or `cpldglue build project.cg -o out`) writes `NAME.jed` (for any
  GAL programmer: TL866, T48, ...), `NAME.pld` and `NAME.pin`.

How it works: every output, register input and output enable becomes a
minimal sum of products of the input pins and the register/latch outputs, in
whichever polarity needs fewer terms (an output's value doesn't matter while
its enable is off, which often saves terms). The fitter picks the GAL16V8 mode
(simple, complex or registered), places the outputs and inputs, and the fuse
map is read back and simulated against the design, with clock pulses.
The JEDEC writer follows galette's fuse layout and is tested bit for bit
against galette's own test files.

What fits, and what doesn't:

| | GAL16V8 | GAL22V10 |
|---|---|---|
| Output macrocells | 8 (7-8 product terms each) | 10 (8, 10, 12, 14, 16, 16, 14, 12, 10, 8) |
| Inputs | 10 dedicated (8 in registered mode) + spare OLMC pins | 12 dedicated + spare OLMC pins |
| Clock | one, pin 1, rising edge | one, pin 1, rising edge |
| Async reset | none | one product term that resets every register |
| Output enable | one product term per output; registered outputs share pin 11 | one product term per output |

- Every output and every flip-flop takes an OLMC; a register that isn't an
  output still uses one (and its pin, which you leave unconnected).
- Latches ('373, '573) are built from feedback: Q = LE·D + /LE·Q + D·Q, with
  the last term keeping Q glitch-free while LE falls.
- Gets an error, with the reason: two clocks ('595: SRCLK and RCLK), a
  falling-edge or gated clock, async set/reset on a 16V8, registers with
  different async resets on a 22V10 (it resets all of them together), async
  parallel loads ('165), an output enable that needs more than one product term.
- A '374 is a classic 16R8: eight registers with OE on pin 11. A '161 counter
  with its async clear fits a 22V10 (the clear becomes AR).

## Devices

The whole ATF15xx family, in every package Microchip lists:

| Device | Macrocells | Packages | Supply |
|---|---|---|---|
| ATF1502AS / ASL | 32 | PLCC44, TQFP44 | 5 V |
| ATF1502ASV | 32 | PLCC44, TQFP44 | 3.3 V |
| ATF1504AS / ASL | 64 | PLCC44, TQFP44, PLCC68, PLCC84, TQFP100, PQFP100 | 5 V |
| ATF1504ASV / ASVL | 64 | same as AS | 3.3 V |
| ATF1508AS / ASL | 128 | PLCC84, TQFP100, PQFP100, PQFP160 | 5 V |
| ATF1508ASV / ASVL | 128 | same as AS | 3.3 V |

Also the GAL16V8 (DIP20, PLCC20) and GAL22V10 (DIP24, PLCC28), see above,
and the GreenPAK SLG46826 / SLG46620.

`python -m cpldglue devices` lists the I/O count of each. The pin tables
(I/O, JTAG, the four dedicated inputs, VCC/GND and no-connects) are
generated from Atmel's BSDL files by `tools/bsdl_to_pins.py` into
`cpldglue/pintables.py`; the AS and ASV parts share pinouts. Some packages
(PLCC68, PQFP100/160) may be hard to find now; check stock before designing
one in.

The report also gives a rough macrocell count: one per output pin plus one
per flip-flop/latch bit in the chips you merged. It's an upper estimate
(a register that drives a pin shares that pin's macrocell); the fitter
report is the real figure. ASV/ASVL parts get a note that they run from
3.3 V. Check 5 V input tolerance in the datasheet before using one on a 5 V board.

## Text netlist format (.cg)

```
design  NAME
device  ATF1502AS PLCC44
jtag    off                  # optional: free the JTAG pins
part    U7 74HC139           # any recognisable value: 74LS139, SN74HC139N, 139
net     CPU_A13 ext: U7.2    # "ext" = the net also goes off-chip, so it needs a pin
net     X: U7.1 U7.11        # internal net
net     GND: U7.8 U7.15      # GND/VCC/VSS/VDD names become constants
net     "Net-(J1-Pad 1)": U7.3   # quote names with spaces, ':' or '#'
net     N4 auto: U7.6 U7.10  # "auto" = unlabelled net; "const=0"/"const=1" force a constant
pin     CPU_A13 12           # lock a pin
layout  U7 120 40            # editor position (written by the GUI)
variant AxROM: U4A           # variants: see "Variants" above
```

## How nets are resolved

| Situation | Result |
|---|---|
| Power net | constant 0/1 |
| No driver, goes off-chip | input pin |
| No driver, internal, labelled | input pin (with a note) |
| No driver, internal, unlabelled | tied low (with a warning) |
| Only goes to unused gates | dropped; no pin (with a note) |
| One totem-pole output | wire; output pin if it goes off-chip |
| Several 3-state / open-collector outputs | priority mux (CPLDs have no internal 3-state); off-chip: 3-state pin, or inout if the CPLD also reads it |
| Totem-pole output plus any other driver | error: contention |

## Supported parts

74x00 02 04 05 06 07 08 10 11 14 20 32 74 86 125 126 138 139 153 157 161
163 164 165 166 174 175 194 240 244 245 273 367 368 373 374 377 540 541 573
574 594 595 597, and CD4014, CD4015, CD4021, CD4094 (also 74HC4094 / HEF4094).
Any logic family prefix works (LS, HC, HCT, ALS, F...).

Single gates (SOT-23-5 / SOT-23-6, pinouts from the TI SN74LVC1G datasheets):
74x1G00 02 08 32 86 (2-input), 1G10 11 27 (3-input), 1G04 14 34 17
(inverters / buffers, '14 and '17 Schmitt), 1G06 07 (open drain), 1G125 126
240 (3-state), 1G79 80 (D flip-flop). Names like SN74LVC1G00DBVR,
74AHC1GU04, 74HC1G125 and onsemi's NC7SZ00 / NC7S04 are recognised.

Shift registers:

| Type | Parts |
|---|---|
| Serial in, parallel out (SIPO) | '164, '594, '595, CD4015 (dual 4-bit), CD4094 / '4094 |
| Parallel in, serial out (PISO) | '165, '166 (sync load), '597 (input register), CD4014 (sync load), CD4021 |
| Universal (left / right / load) | '194 |

Parts that can't be put in a CPLD at all: one-shots ('121, '123), anything
that relies on external RC timing, analog parts. The tool warns about
partial fits: Schmitt-trigger hysteresis ('14) is lost, open-collector parts
need their pull-ups kept, and high-voltage open-collector parts ('06, '07)
can't be pulled above VCC.

Adding a part: add its pinout to `_DEFS` in [cpldglue/chips.py](cpldglue/chips.py)
its model to [cpldglue/hdl/chips.v](cpldglue/hdl/chips.v), and its gates to
[cpldglue/units.py](cpldglue/units.py) (used for leaving out unused gates and
for the drawing), then add a reference check to `tests/test_chips.py`. The
tests check that the units cover every pin and that the frontend drawing has
no crossing wires (`cpldglue/gui/frontend/src/fixtures/parts.json` holds a
copy of `/api/parts` for that test; refresh it when you add a part).

## Tests

```bash
python -m unittest discover -s tests
```

```bash
cd cpldglue/gui/frontend && npm test
```

- Every chip model is checked against an independent Python description of
  its datasheet behaviour, using Yosys and the built-in gate simulator
  (`cpldglue/sim.py`).
- The TinyTendo merge (U7 + U8 + U9) is compared vector by vector with a
  hand-written reference, both from the `.cg` example and straight from the
  KiCad schematic.
- Generator rules are tested: internal 3-state → mux, wired-AND
  open-collector, contention errors, running out of pins.
- Devices: every package's pins are each I/O, input-only, power or NC
  exactly once; spot checks against the BSDL files; pin assignment fills
  every package exactly; the macrocell counts match the chip models.
- Desktop app: download checksum handling, open / save as / recent
  projects, the first-run example copy (`tests/test_app.py`); the server
  refuses writes without its header and requests for other host names.
- GUI backend: API, saving and conflict detection, `.cg`/`.json` round trips,
  pin-lock round trips through `.pin` files, the simulator session (TinyTendo
  decode and controller reads, a clocked counter), KiCad import, and the
  build button's error paths.
- Editor model (TypeScript): every editing operation, undo/redo, and
  rebuilding the TinyTendo example using only editor operations.
- GAL target (`tests/test_gal.py`): the JEDEC writer against galette's own
  `.pld` → `.jed` test files bit for bit (`tests/reference/galette`, MIT); the
  fuse-map simulator against the equations; the minimal covers; real fits
  (decoder, '244, '161 with async clear, '374, '245, '573) checked by
  simulation; a wrong fuse is caught; the written `.pld` assembles to the
  same fuses; the CLI and Build button.

## Things to keep in mind

- Timing: a CPLD is faster than LS/HC parts. Designs that accidentally depend
  on slow gates (pulse stretching, races) can behave differently.
- Drive: ATF15xx pins sink about 8 mA. Fine for HC/HCT loads; check before
  replacing LS parts that drive heavy buses.
- Floating internal 3-state nets read 1, as if pulled up.
