"""Desktop-app pieces: dependency downloads (checksums), open / save as,
recent projects and the first-run example. No network access."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import deps, design as dsg                 # noqa: E402
from cpldglue.gui import api                             # noqa: E402


class TempHome(unittest.TestCase):
    """Run each test with an empty data folder and home folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cg_app_"))
        self.saved = {k: os.environ.get(k) for k in ("CPLDGLUE_HOME", "HOME", "USERPROFILE")}
        os.environ["CPLDGLUE_HOME"] = str(self.tmp / "data")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.tmp / "home")
        (self.tmp / "home" / "Documents").mkdir(parents=True)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestDownload(TempHome):
    def _file(self, body: bytes) -> str:
        src = self.tmp / "src.bin"
        src.write_bytes(body)
        return src.as_uri()

    def test_good_checksum_is_kept(self):
        body = b"hello" * 1000
        d = deps.Download(self._file(body), hashlib.sha256(body).hexdigest(), len(body), "x.bin")
        seen = []
        out = deps.download(d, self.tmp / "dl", lambda done, total, msg: seen.append(done))
        self.assertEqual(out.read_bytes(), body)
        self.assertEqual(seen[-1], len(body))
        # cached: a second call doesn't re-download
        self.assertEqual(deps.download(d, self.tmp / "dl", lambda *a: self.fail()), out)

    def test_bad_checksum_is_rejected(self):
        d = deps.Download(self._file(b"tampered"), "0" * 64, 8, "y.bin")
        with self.assertRaises(RuntimeError) as cm:
            deps.download(d, self.tmp / "dl", lambda *a: None)
        self.assertIn("checksum mismatch", str(cm.exception))
        self.assertEqual(list((self.tmp / "dl").iterdir()), [])     # nothing left behind

    def test_pinned_downloads_are_complete(self):
        for d in deps.YOSYS_WHEELS + list(deps.WASMTIME.values()) + [deps.PROCHIP, deps.NEXTPNR_WHEEL]:
            self.assertRegex(d.sha256, r"^[0-9a-f]{64}$")
            self.assertTrue(d.url.endswith(d.filename))
        self.assertEqual(set(deps.FLOW_FILES), {"cells.lib", "techmap.v", "README.txt"})

    def test_status_with_nothing_downloaded(self):
        st = {d["id"]: d for d in deps.status()}
        self.assertEqual(list(st), ["yosys", "flow", "fitter", "nextpnr", "quartus", "kicad"])
        self.assertFalse(st["flow"]["found"])
        self.assertIsNone(deps.flow_dir())


class TestProjects(TempHome):
    def test_open_save_as_and_recent(self):
        a = self.tmp / "a.cg"
        p = api.Project(a)                       # new project
        self.assertEqual(p.design.parts, {})
        d = dsg.load(ROOT / "examples" / "tinytendo.cg")
        res = p.save_as(d, self.tmp / "b.json")
        self.assertFalse(res["conflict"])
        self.assertTrue((self.tmp / "b.json").exists())
        p.open(a)
        self.assertEqual(p.path, a.resolve())
        self.assertEqual(deps.recent_projects(), [str((self.tmp / "b.json").resolve())])
        self.assertEqual(p.payload()["recent"], [str((self.tmp / "b.json").resolve())])
        with self.assertRaises(ValueError):
            p.open(self.tmp / "notes.txt")
        with self.assertRaises(ValueError):
            p.open(self.tmp / "missing-folder" / "x.cg")

    def test_starts_with_an_empty_project(self):
        from cpldglue import app
        folder = self.tmp / "home" / "Documents" / "CPLD-Builder"
        first = app.default_project()
        self.assertEqual(first, folder / "untitled.cg")
        self.assertFalse(first.exists())                    # nothing written until saved
        self.assertEqual(api.Project(first).design.parts, {})
        # recent projects don't change that; a saved untitled.cg isn't reused
        deps.remember_project(self.tmp / "other.cg")
        (self.tmp / "other.cg").write_text("design other\n")
        first.write_text("design untitled\n")
        self.assertEqual(app.default_project(), folder / "untitled-2.cg")
        self.assertFalse((folder / "tinytendo.cg").exists())   # no example copied

    def test_example_is_copied_when_opened(self):
        from cpldglue import app
        p = app.example_copy("tinytendo")
        self.assertEqual(p, self.tmp / "home" / "Documents" / "CPLD-Builder" / "examples" / "tinytendo.cg")
        self.assertIn("74HC139", p.read_text())
        p.write_text("design edited\n")                    # the user's edits are kept
        self.assertEqual(app.example_copy("tinytendo").read_text(), "design edited\n")
        with self.assertRaises(ValueError):
            app.example_copy("nope")

    def test_saving_a_new_project_makes_it_recent(self):
        p = api.Project(self.tmp / "fresh.cg")
        self.assertEqual(deps.recent_projects(), [])
        p.save(p.design, None)
        self.assertEqual([Path(r).resolve() for r in deps.recent_projects()], [p.path.resolve()])

    def test_app_passes_cli_commands_through(self):
        import contextlib
        import io
        from cpldglue import app
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(app.main(["parts"]), 0)
        self.assertIn("74x139", out.getvalue())


if __name__ == "__main__":
    unittest.main()
