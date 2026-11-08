"""CPLD-Builder desktop app: the editor in its own window.

    CPLD-Builder [PROJECT] [--browser] [--port N]

Starts the same local server as `cpldglue gui` and shows it in a native
window (pywebview: Edge WebView2 on Windows, Qt or GTK on Linux). Without
pywebview, or with --browser, it opens the system browser instead.

With no PROJECT it reopens the last project, or on first run copies the
TinyTendo example to Documents/CPLD-Builder and opens that.

The packaged app also answers the command-line tool's subcommands
(`CPLD-Builder gen …`, `CPLD-Builder setup yosys` …) and the internal
`_yosys` used to run the downloaded Yosys.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

from . import deps

CLI_COMMANDS = {"parts", "devices", "kicad", "gen", "build", "gui", "setup", "_yosys"}


def resource_dir() -> Path:
    """Where bundled files (examples) live: the PyInstaller bundle or the repo."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent.parent


def default_project() -> Path:
    recent = deps.recent_projects()
    if recent:
        return Path(recent[0])
    docs = Path.home() / "Documents"
    folder = (docs if docs.is_dir() else Path.home()) / "CPLD-Builder"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "tinytendo.cg"
    example = resource_dir() / "examples" / "tinytendo.cg"
    if not target.exists() and example.exists():
        shutil.copyfile(example, target)
    return target if target.exists() else folder / "untitled.cg"


class Bridge:
    """Functions the page can call as window.pywebview.api.*"""

    def __init__(self):
        self._window = None     # private: pywebview exposes public attributes to JS

    def pick(self, mode: str, current: str = "") -> Optional[str]:
        import webview
        cur = Path(current) if current else None
        folder = str(cur.parent) if cur and cur.parent.is_dir() else str(Path.home())
        types = ("CPLD-Builder projects (*.cg;*.json)", "All files (*.*)")
        dialog = getattr(webview, "FileDialog", None)
        if mode == "save":
            kind = dialog.SAVE if dialog else webview.SAVE_DIALOG
            r = self._window.create_file_dialog(kind, directory=folder, file_types=types,
                                               save_filename=cur.name if cur else "project.cg")
        else:
            kind = dialog.OPEN if dialog else webview.OPEN_DIALOG
            r = self._window.create_file_dialog(kind, directory=folder, file_types=types)
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

    def title(self, text: str) -> None:
        if self._window is not None:
            self._window.set_title(text)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in CLI_COMMANDS:
        from .cli import main as cli_main
        return cli_main(argv)

    ap = argparse.ArgumentParser(prog="CPLD-Builder", description=__doc__.split("\n\n")[0])
    ap.add_argument("project", nargs="?", type=Path, help=".cg or .json project")
    ap.add_argument("--browser", action="store_true", help="use the system browser")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)

    from .gui import api
    from .gui.server import bind, make_handler

    project = api.Project(a.project or default_project())
    deps.remember_project(project.path)
    httpd = bind(make_handler(project, api.Builder(None, None)), a.port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    webview = None
    if not a.browser:
        try:
            import webview                      # noqa: F811
        except ImportError:
            webview = None
    try:
        if webview is not None:
            try:
                return _window(webview, url)
            except Exception as e:              # e.g. missing Qt/WebView2 libraries
                _say(f"Could not open the app window ({type(e).__name__}: {e}); "
                     f"using the browser instead.")
        webbrowser.open(url)
        _say(f"CPLD-Builder: {url}  (project {project.path}). Close this window "
             f"or press Ctrl+C to stop.")
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        httpd.server_close()
    return 0


def _window(webview, url: str) -> int:
    bridge = Bridge()
    bridge._window = webview.create_window(
        "CPLD-Builder", url, js_api=bridge, width=1440, height=900,
        min_size=(900, 600), text_select=True)
    icon = resource_dir() / ("icon.png" if getattr(sys, "_MEIPASS", None)
                             else "packaging/icon.png")
    webview.start(private_mode=False,    # returns when the window closes
                  icon=str(icon) if icon.exists() else None,
                  gui="qt" if sys.platform.startswith("linux") else None)
    return 0


def _say(msg: str) -> None:
    if sys.stdout is not None:                  # None in the windowed app
        print(msg, flush=True)


if __name__ == "__main__":
    sys.exit(main())
