CPLD-Builder
============

Merge 74-series and CD4000 glue logic into one Microchip ATF15xx CPLD.

Start
-----
Windows: run CPLD-Builder.exe. (Keep it in this folder: it needs _internal.)
Linux:   run ./install.sh once (adds a menu entry and the `cpld-builder` and
         `cpldglue` commands), or just run ./CPLD-Builder from here.

The first time, it opens a copy of the TinyTendo example from
Documents/CPLD-Builder. Use Open... to open or start other projects (.cg or
.json); it reopens the last one next time.

Optional tools
--------------
Click Setup... in the toolbar. Editing and pin assignment need nothing else.

  Yosys          for Simulate and Build. One click: about 25 MB from PyPI.
  Flow files     for Build. One click: about 30 KB from GitHub.
  Microchip fitter  for Build (the .jed). One click downloads Microchip's
                 ProChip package (224 MB) and opens its installer; install it
                 with the default folder. Linux needs Wine for this.
  KiCad          for Import KiCad... Install KiCad 7 or newer yourself.

Downloads are checked against fixed SHA-256 checksums and kept in
  Windows: %LOCALAPPDATA%\cpldglue
  Linux:   ~/.local/share/cpldglue
Delete that folder to remove them.

KiCad
-----
Pinout view -> Copy for KiCad copies the CPLD as a KiCad symbol wired up
with net labels. Paste it into your schematic with Ctrl+V.

Command line
------------
cpldglue (cpldglue.exe on Windows) next to the app is the command-line tool:
  cpldglue setup                 show which optional tools are installed
  cpldglue setup yosys flow      download them
  cpldglue gen project.cg -o out --check
  cpldglue build project.cg -o out
  cpldglue kicad-symbol project.cg -o kicad --copy
