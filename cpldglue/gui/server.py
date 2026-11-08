"""Local web server for the GUI. Standard library only.

    python -m cpldglue gui examples/tinytendo.cg

Serves the built frontend from gui/static and a JSON API under /api.
The project file may not exist yet; saving creates it (.json or .cg,
chosen by the extension).
Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import api
from .. import deps
from .. import generate
from ..design import Design

STATIC = Path(__file__).parent / "static"


def make_handler(project: api.Project, builder: "api.Builder | None" = None):
    sim = api.SimSession()
    jobs = deps.Jobs()
    kicad = api.KiCadImporter()
    builder = builder or api.Builder(None, None)

    def design_of(body):
        return (Design.from_json(json.dumps(body["design"]))
                if body.get("design") else project.design)

    class Handler(BaseHTTPRequestHandler):
        server_version = "cpldglue"

        def log_message(self, fmt, *args):      # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def _allowed(self, write: bool) -> bool:
            """Only answer requests addressed to this machine (blocks DNS
            rebinding), and only accept writes from our own page: the
            X-Cpldglue header can't be sent cross-site without a CORS
            preflight, which this server never approves."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if host not in ("127.0.0.1", "localhost", "::1"):
                self._json({"error": "forbidden host"}, 403)
                return False
            if write and self.headers.get("X-Cpldglue") != "1":
                self._json({"error": "missing X-Cpldglue header"}, 403)
                return False
            return True

        def do_GET(self):
            if not self._allowed(write=False):
                return
            path = urlparse(self.path).path
            if path == "/api/deps":
                return self._json({"deps": deps.status(), "jobs": jobs.snapshot()})
            if path == "/api/parts":
                return self._json(api.parts_payload())
            if path == "/api/devices":
                return self._json(api.devices_payload())
            if path == "/api/project":
                return self._json(project.payload())
            if path == "/api/kicad/find":
                return self._json({"files": api.find_schematics(project.path.parent.resolve())})
            if path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            return self._static(path)

        def do_POST(self):
            if not self._allowed(write=True):
                return
            path = urlparse(self.path).path
            if path in ("/api/project/open", "/api/project/saveas"):
                try:
                    body = self._body()
                    if path.endswith("open"):
                        project.open(body["path"])
                    else:
                        if Path(body["path"]).suffix.lower() not in (".cg", ".json"):
                            raise ValueError("projects are .cg or .json files")
                        project.save_as(Design.from_json(json.dumps(body["design"])),
                                        body["path"])
                    return self._json(project.payload())
                except (ValueError, KeyError, OSError) as e:
                    return self._json({"error": str(e)}, 400)
            if path == "/api/deps/fetch":
                try:
                    return self._json(jobs.start(self._body()["id"]))
                except (ValueError, KeyError) as e:
                    return self._json({"error": str(e)}, 400)
            if path == "/api/deps/installer":
                setup = deps.prochip_setup()
                if setup is None:
                    return self._json({"error": "ProChip hasn't been downloaded yet"}, 400)
                deps.open_installer(setup)
                return self._json({"ok": True})
            if path.startswith("/api/kicad/") or path.startswith("/api/build"):
                try:
                    body = self._body()
                    if path == "/api/kicad/components":
                        return self._json(kicad.components(body["path"]))
                    if path == "/api/kicad/preview":
                        return self._json(kicad.preview(body["path"], body.get("refs", []),
                                                        body.get("overrides"), design_of(body)))
                    if path == "/api/build/config":
                        return self._json(builder.config(design_of(body)))
                    if path == "/api/build":
                        d = design_of(body)
                        out = project.path.resolve().parent / "build" / generate.sanitize(d.name)
                        return self._json(builder.build(d, out))
                except (ValueError, RuntimeError, KeyError, OSError) as e:
                    return self._json({"error": str(e)}, 400)
            if path == "/api/sim/build":
                try:
                    body = self._body()
                    design = Design.from_json(json.dumps(body["design"]))
                    return self._json(sim.build(design, bool(body.get("fresh"))))
                except Exception as e:
                    return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 400)
            if path == "/api/sim/step":
                try:
                    return self._json(sim.step(self._body().get("steps", [{}])))
                except Exception as e:
                    return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 400)
            if path == "/api/generate":
                try:
                    body = self._body()
                    design = (Design.from_json(json.dumps(body["design"]))
                              if "design" in body else project.design)
                    return self._json(api.generate_payload(design))
                except Exception as e:                       # report, don't crash
                    return self._json({"error": f"{type(e).__name__}: {e}"}, 400)
            return self._json({"error": "not found"}, 404)

        def do_PUT(self):
            if not self._allowed(write=True):
                return
            path = urlparse(self.path).path
            if path != "/api/project":
                return self._json({"error": "not found"}, 404)
            try:
                body = self._body()
                design = Design.from_json(json.dumps(body["design"]))
                res = project.save(design, body.get("base_mtime"),
                                   bool(body.get("force")))
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 400)
            return self._json(res, 409 if res["conflict"] else 200)

        def _static(self, path: str):
            rel = path.lstrip("/") or "index.html"
            f = (STATIC / rel).resolve()
            if not str(f).startswith(str(STATIC.resolve())) or not f.is_file():
                f = STATIC / "index.html"
                if not f.is_file():
                    return self._send(500, b"GUI not built: run npm run build in "
                                           b"cpldglue/gui/frontend", "text/plain")
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            return self._send(200, f.read_bytes(), ctype)

    return Handler


class _Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind a port that is
    # already in use, so two editors would silently share one port. Without
    # it the bind fails and serve() moves on to the next port.
    allow_reuse_address = sys.platform != "win32"


def bind(handler, port: int, tries: int = 20) -> ThreadingHTTPServer:
    """Bind 127.0.0.1:port, or the next free port above it."""
    for p in range(port, port + tries):
        try:
            return _Server(("127.0.0.1", p), handler)
        except OSError:
            if p == port + tries - 1:
                raise
    raise OSError("no free port")


def serve(project_path, port: int = 8765, open_browser: bool = True,
          flow_dir=None, fitter_dir=None) -> None:
    project = api.Project(project_path)
    builder = api.Builder(flow_dir, fitter_dir)
    httpd = bind(make_handler(project, builder), port)
    if httpd.server_address[1] != port:
        print(f"Port {port} is in use (another editor?); using {httpd.server_address[1]}.")
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"cpldglue GUI: {url}  (project {project.path}). Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
