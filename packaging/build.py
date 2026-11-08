"""Build the desktop app for the platform this runs on.

    pip install -r packaging/requirements-build.txt
    python packaging/build.py

Output: dist/CPLD-Builder/ (the app folder) and an archive next to it:
  Windows: dist/CPLD-Builder-<version>-windows-x64.zip
  Linux:   dist/CPLD-Builder-<version>-linux-<arch>.tar.gz (with install.sh)
"""
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cpldglue import __version__          # noqa: E402

DIST = ROOT / "dist"


def main() -> None:
    if not (ROOT / "packaging" / "icon.ico").exists():
        subprocess.check_call([sys.executable, str(ROOT / "packaging" / "make_icon.py")])
    if not (ROOT / "cpldglue" / "gui" / "static" / "index.html").exists():
        sys.exit("cpldglue/gui/static is missing: run `npm ci && npm run build` in "
                 "cpldglue/gui/frontend first")
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm",
                           "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "pyinstaller"),
                           str(ROOT / "packaging" / "CPLD-Builder.spec")])
    app = DIST / "CPLD-Builder"
    shutil.copyfile(ROOT / "packaging" / "README-app.txt", app / "README.txt")
    arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(
        platform.machine().lower(), platform.machine().lower())
    if sys.platform == "win32":
        out = DIST / f"CPLD-Builder-{__version__}-windows-{arch}"
        shutil.make_archive(str(out), "zip", DIST, "CPLD-Builder")
        print(f"\nBuilt {app}\nArchive {out}.zip")
    else:
        for f in ("install.sh", "cpld-builder.desktop"):
            shutil.copyfile(ROOT / "packaging" / "linux" / f, app / f)
        (app / "install.sh").chmod(0o755)
        out = DIST / f"CPLD-Builder-{__version__}-linux-{arch}.tar.gz"
        with tarfile.open(out, "w:gz") as t:
            t.add(app, arcname="CPLD-Builder")
        print(f"\nBuilt {app}\nArchive {out}")


if __name__ == "__main__":
    main()
