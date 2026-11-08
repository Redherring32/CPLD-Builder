# PyInstaller spec: builds dist/CPLD-Builder/ with two programs sharing
# one folder:
#   CPLD-Builder(.exe)  the desktop app (no console window)
#   cpldglue(.exe)      the command-line tool (also used by the app to run
#                       the downloaded Yosys in the background)
#
#   pyinstaller --noconfirm packaging/CPLD-Builder.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "cpldglue" / "gui" / "static"), "cpldglue/gui/static"),
    (str(ROOT / "cpldglue" / "hdl"), "cpldglue/hdl"),
    (str(ROOT / "examples"), "examples"),
    (str(ROOT / "packaging" / "icon.png"), "."),
]
ICON = str(ROOT / "packaging" / ("icon.ico" if sys.platform == "win32" else "icon.png"))

# The downloaded Yosys (yowasp + wasmtime) is imported from the user's data
# folder at run time, so PyInstaller can't see what standard-library modules
# it needs. List them here.
hidden = [
    "ctypes", "ctypes.util", "tempfile", "signal", "hashlib", "importlib.resources",
    "importlib.metadata", "importlib.abc", "typing", "weakref", "enum", "abc",
    "struct", "platform", "sysconfig", "configparser", "dataclasses", "functools",
    "contextlib", "zipfile", "shutil", "threading", "pathlib", "warnings", "io",
    "codecs", "encodings.idna",
]
if sys.platform == "win32":
    hidden += ["ctypes.wintypes"]

common = dict(pathex=[str(ROOT)], datas=datas, hiddenimports=hidden,
              excludes=["tkinter", "unittest", "pydoc", "test"])

app = Analysis([str(ROOT / "packaging" / "launch_app.py")], **common)
cli = Analysis([str(ROOT / "packaging" / "launch_cli.py")], **common)

app_pyz = PYZ(app.pure)
cli_pyz = PYZ(cli.pure)

app_exe = EXE(app_pyz, app.scripts, [], exclude_binaries=True, name="CPLD-Builder",
              console=False, upx=False, icon=ICON)
cli_exe = EXE(cli_pyz, cli.scripts, [], exclude_binaries=True, name="cpldglue",
              console=True, upx=False, icon=ICON)

coll = COLLECT(app_exe, app.binaries, app.datas, cli_exe, cli.binaries, cli.datas,
               name="CPLD-Builder", upx=False)
