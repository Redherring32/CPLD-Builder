# GUI editor plan

A visual editor for cpldglue projects: place chips, wire their pins, see
what the CPLD pinout looks like, and try the logic live, all without
writing a netlist by hand.

## Status (2026-11-08)

All six milestones are built and self-tested; see "Milestones" below for
what each covers. Differences from the original plan:

- Drag-and-drop works for the library and the pinout. The pinout also
  supports *select a signal, click a free pin*, which is quicker and
  works without a mouse drag.
- The Simulate tab sits in the right-hand panel, not in a separate dock.
  Inputs named `…_n` start at 1 (inactive) so active-low enables don't
  begin "on".
- KiCad import replaces the project's chips rather than merging, and
  keeps the name, device, package and pin locks. Undo restores the old
  chips.
- The `.cg` format gained quoted net names, `auto`/`const=` flags and
  `layout` lines, so GUI projects can be saved as readable text.

Not yet verified:
- **The Build button with real tools.** The atf15xx_yosys files and
  Microchip's fitter weren't available, so only its error paths have run.
- **Frontend end-to-end tests.** The Playwright suite hasn't been
  written. The UI was tested by driving the real page in a browser, plus
  unit tests on the editing model.

## Goals

1. Wire chips by dragging between pins, using the real pin numbers.
2. See at once what each edit costs: pins used, internal nets, errors.
3. Assign and lock CPLD pins on a drawing of the actual package.
4. Toggle inputs and watch outputs (live simulation) before building.
5. Import from KiCad, and produce the same files the command line does.

Non-goals for now: a full schematic editor, timing analysis, and writing
changes back into KiCad. KiCad import stays one-way.

## Architecture

```
 browser (single-page app)  <--JSON over HTTP-->  python -m cpldglue gui
   canvas, pinout, report,                          existing cpldglue modules:
   simulator panel                                  design, generate, devices,
                                                    yosys, sim
```

- **Backend:** a small local server added to the existing package
  (`cpldglue/gui/server.py`, Python standard library `http.server` only).
  It opens the browser on `localhost`. All logic stays in the modules we
  already have and test. The GUI is only a front end, so the command line
  and the GUI can never disagree.
- **Frontend:** React with [React Flow](https://reactflow.dev) for the
  canvas (pan, zoom, drag, pin-to-pin connections) plus plain SVG for the
  package drawing. It's built once with Vite, and the built files are
  committed under `cpldglue/gui/static/`, so you only need Python to run
  it. Node is only needed to change the GUI.
- **Project file:** the existing `cpldglue-project-1` JSON. The `layout`
  field, already in `Design` and ignored by the generator, holds positions:
  `{"U7": {"x": 120, "y": 40, "rot": 0}, "_nets": {...}}`.

Alternative considered: a native Qt desktop app (PySide6). It's one
language, but drawing a node editor from scratch is much more work than
React Flow, and it adds a large dependency. The browser approach also works
unchanged on Linux and macOS.

## Backend API

| Endpoint | Purpose |
|---|---|
| `GET /api/parts` | library: keys, titles, pinouts (number, name, kind), package |
| `GET /api/devices` | devices, packages, I/O / input-only / JTAG pin lists |
| `GET /api/project` · `PUT /api/project` | load / save the project JSON |
| `POST /api/generate` | project → report (pins, errors, warnings, notes) + Verilog text |
| `POST /api/import/kicad` | schematic path → component list; then refs → project |
| `POST /api/sim/build` | synthesize the current design for simulation (cached by content hash) |
| `POST /api/sim/step` | input values → output values (and internal nets) |
| `POST /api/build` | run the ATF flow; stream the log |

`generate` is fast (pure Python), so it runs on every edit. Simulation needs
a Yosys run (a few seconds with yowasp), so it rebuilds in the background
and the panel shows "updating…" until it's done.

## Screens

**1. Chip canvas (main view)**
- Library sidebar with search ("139", "decoder"). Drag a part onto the canvas.
- Each chip is drawn as a DIP outline with pin numbers in the real places
  and port names inside (`1  /G1`, `2  1A`…). Pin colour shows kind: input,
  output, 3-state, bidirectional, open-collector, power.
- Drag from pin to pin to make a net. Click a wire to rename the net or
  mark it **external** (it then shows as a flag at the canvas edge and will
  need a CPLD pin).
- Power pins are connected implicitly. Tie an input high or low from the
  pin's right-click menu.
- Option to show nets as labels instead of wires, for crowded designs.
- Problem highlighting from the report: contention in red, undriven inputs
  in amber, unused gates greyed out.

**2. Pinout view**
- Top-down drawing of the selected package (PLCC44 / TQFP44 first).
- Pins coloured as free I/O, input-only, JTAG, used, or locked.
- Drag a signal from the side list onto a pin to lock it. Drag it off to
  unlock. A JTAG on/off toggle.
- Running pin count, e.g. "22 / 32 used". Over budget turns red, with a
  suggestion such as "a bigger package" or "keep U5 discrete".

**3. Report and output panel** (bottom dock)
- Live errors, warnings and notes; clicking one selects the chip or net.
- Tabs for the generated Verilog and `.pin` file (read-only, copyable).
- Build button (only shown when the flow and fitter folders are set),
  streaming log, and links to the `.jed` and `.fit` files.

**4. Simulator panel**
- One switch per input pin and an LED per output pin (Z shown as hollow).
- Clock inputs get "pulse" and "run at N Hz" buttons.
- Hovering an internal net shows its current value on the canvas.
- Later: record a sequence and show a waveform, and save it as a test vector.

**5. KiCad import dialog**
- Pick a `.kicad_sch` → table of components with values. Supported parts
  are ticked automatically by family, and you choose which to merge.
- Shows the predicted pin count as you tick and untick, which answers
  "which chips should go in?" before committing.
- Imported chips are laid out automatically (grid by reference), and the
  layout is then yours to arrange.

## Milestones

| # | Deliverable | Done when |
|---|---|---|
| M1 | Server + read-only viewer: open a project, chips drawn with pinouts, nets as labels, live report | The TinyTendo project opens and shows the same report as the command line |
| M2 | Editing: add/remove chips, draw/delete wires, rename nets, external flag, tie-offs, save; undo/redo | Rebuilding the TinyTendo example from scratch in the GUI gives an identical project |
| M3 | Pinout view with drag-to-lock and JTAG toggle | Locks round-trip through the `.pin` file |
| M4 | Simulator panel | TinyTendo decode and controller reads can be exercised by hand |
| M5 | KiCad import dialog and Build button | U7/U8/U9 import from the schematic in a few clicks |
| M6 | Polish: keyboard shortcuts, auto-layout, net-label mode, waveforms | — |

M1–M2 are most of the work. M3 and M4 reuse the existing backend almost
entirely.

## Testing

- Backend endpoints get unit tests on top of the existing suite (same
  fixtures: the TinyTendo example and the hand-written reference).
- Frontend: a small set of Playwright end-to-end tests (open project, draw a
  wire, check the report updates), run against the built bundle.

## Open questions

1. **Gate symbols vs whole packages.** This plan draws whole DIP packages
   because pin numbers are what you wire on a real board. Per-gate symbols
   like KiCad's are tidier for logic but hide the pinout. They could be a
   later view option.
2. **Bigger devices.** Done: every ATF15xx device and package, with pin
   tables generated from Atmel's BSDL files. Packages over 44 pins are drawn
   at full size in a scrollable view (*Fit* shrinks them to the panel).
3. **Running without Yosys.** Generation and pinout work without it. Only
   simulation and builds need it, so the GUI should degrade gracefully when
   it's missing.
