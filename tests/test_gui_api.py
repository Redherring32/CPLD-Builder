"""GUI backend: API functions and the HTTP server."""
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import os
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cpldglue import design as dsg, generate                 # noqa: E402
from cpldglue.gui import api                                 # noqa: E402
from cpldglue.gui.server import bind, make_handler           # noqa: E402

EXAMPLE = ROOT / "examples" / "tinytendo.cg"


class TestApi(unittest.TestCase):
    def test_parts_payload_lists_library(self):
        parts = {p["key"]: p for p in api.parts_payload()["parts"]}
        self.assertIn("4021", parts)
        self.assertEqual([p["number"] for p in parts["74x139"]["pins"]],
                         [str(i) for i in range(1, 17)])

    def test_generate_matches_cli_report(self):
        d = dsg.load(EXAMPLE)
        g = api.generate_payload(d)
        self.assertTrue(g["ok"])
        self.assertEqual(g["report"], generate.generate(d).report(d))
        self.assertEqual(len(g["ports"]), 22)
        self.assertEqual(g["capacity"], 32)          # 28 I/O (JTAG kept) + 4 inputs
        self.assertEqual(g["nets"]["CPU-D0"]["port"], "CPU_D0")
        self.assertIsNotNone(g["nets"]["CPU-D0"]["pin"])
        self.assertIsNone(g["nets"]["Net-(U7A-E)"]["port"])

    def test_project_reloads_when_file_changes(self):
        tmp = Path(tempfile.mkdtemp(prefix="cg_proj_")) / "p.cg"
        shutil.copy(EXAMPLE, tmp)
        p = api.Project(tmp)
        self.assertEqual(p.design.name, "tinytendo_glue")
        time.sleep(0.05)
        tmp.write_text(tmp.read_text().replace("design  tinytendo_glue",
                                               "design  renamed"))
        self.assertTrue(p.check_changed())
        self.assertEqual(p.payload()["design"]["name"], "renamed")

    def test_broken_project_reports_error(self):
        tmp = Path(tempfile.mkdtemp(prefix="cg_bad_")) / "bad.cg"
        tmp.write_text("part U1 74x999\n")
        p = api.Project(tmp)
        self.assertIn("unknown part", p.payload()["error"])


def canon(d):
    """Comparable view of a design (ignores dict order)."""
    return (d.name, d.device, d.package, d.keep_jtag, sorted(d.parts.items()),
            sorted((n.name, n.external, n.const, n.named,
                    tuple(sorted((x.ref, x.pin) for x in n.nodes)))
                   for n in d.nets.values()),
            sorted(d.pin_locks.items()),
            sorted((k, v["x"], v["y"]) for k, v in d.layout.items()))


class TestSave(unittest.TestCase):
    def test_text_round_trip(self):
        d = dsg.load(EXAMPLE)
        d.layout = {"U7": {"x": 10, "y": 20.5}, "U8": {"x": -40, "y": 0}}
        d.pin_locks = {"CPU_A13": 33}
        d.keep_jtag = False
        d.nets["TIE"] = dsg.Net("TIE", [dsg.Node("U9", "10")], const=0)
        d.nets["CPU-A13"].named = False
        again = dsg.parse_text(dsg.to_text(d))
        self.assertEqual(canon(again), canon(d))

    def test_awkward_net_names_round_trip(self):
        """KiCad net names can contain spaces, colons, '#' and quotes."""
        d = dsg.parse_text("part U1 74x04\npart U2 74x04\n")
        names = ["Net-(J1-Pad 1)", "A:B", "has#hash", 'say "hi"', "back\\slash", "plain"]
        for i, name in enumerate(names):
            d.nets[name] = dsg.Net(name, [dsg.Node("U1", str([1, 3, 5, 9, 11, 13][i])),
                                          dsg.Node("U2", str([2, 4, 6, 8, 10, 12][i]))],
                                   external=i % 2 == 0)
        text = dsg.to_text(d)
        self.assertIn('net "Net-(J1-Pad 1)" ext: U1.1 U2.2', text)
        self.assertIn("net plain: U1.13 U2.12", text)
        self.assertEqual(canon(dsg.parse_text(text)), canon(d))

    def test_compact_net_syntax_still_parses(self):
        d = dsg.parse_text("part U1 74x04\nnet X: U1.1  # comment\nnet Y ext:U1.2\n")
        self.assertEqual([n.pin for n in d.nets["X"].nodes], ["1"])
        self.assertTrue(d.nets["Y"].external)

    def test_json_round_trip(self):
        d = dsg.load(EXAMPLE)
        d.layout = {"U7": {"x": 1, "y": 2}}
        self.assertEqual(canon(dsg.Design.from_json(d.to_json())), canon(d))

    def test_save_conflict_and_force(self):
        tmp = Path(tempfile.mkdtemp(prefix="cg_save_")) / "p.cg"
        shutil.copy(EXAMPLE, tmp)
        p = api.Project(tmp)
        base = p.mtime
        time.sleep(0.05)
        tmp.write_text(tmp.read_text() + "\n# edited elsewhere\n")
        d = dsg.load(EXAMPLE)
        self.assertTrue(p.save(d, base)["conflict"])
        res = p.save(d, base, force=True)
        self.assertFalse(res["conflict"])
        self.assertEqual(canon(dsg.load(tmp)), canon(d))

    def test_frontend_fixture_matches_example(self):
        """The editor's TypeScript tests use a JSON copy of the example."""
        fx = ROOT / "cpldglue" / "gui" / "frontend" / "src" / "fixtures" / "tinytendo.json"
        self.assertEqual(canon(dsg.load(fx)), canon(dsg.load(EXAMPLE)))

    def test_new_project_starts_empty_and_saves(self):
        tmp = Path(tempfile.mkdtemp(prefix="cg_new_")) / "my board.json"
        p = api.Project(tmp)
        self.assertEqual(p.error, "")
        self.assertEqual(p.design.parts, {})
        self.assertEqual(p.design.name, "my_board")
        d = dsg.load(EXAMPLE)
        self.assertFalse(p.save(d, 0.0)["conflict"])
        self.assertEqual(canon(dsg.load(tmp)), canon(d))


class TestPinLocks(unittest.TestCase):
    def test_locks_round_trip_through_pin_file(self):
        from cpldglue import devices
        d = dsg.load(EXAMPLE)
        d.pin_locks = {"CPU_A13": 33, "OE1_n": 43, "CPU_D0": 4}
        r = generate.generate(d)
        self.assertTrue(r.ok, r.errors)
        parsed = devices.parse_pin_file(r.pin_file(d))
        for sig, pin in d.pin_locks.items():
            self.assertEqual(parsed[sig], pin)
        self.assertEqual(parsed, r.pins)
        # Freezing the whole assignment and regenerating changes nothing.
        d.pin_locks = parsed
        r2 = generate.generate(d)
        self.assertEqual(r2.pins, r.pins)
        self.assertEqual(devices.parse_pin_file(r.verilog), r.pins)   # //PIN: comments

    def test_lock_rules(self):
        d = dsg.load(EXAMPLE)
        d.pin_locks = {"CPU_D0": 43}            # output on an input-only pin
        self.assertIn("input-only", " ".join(generate.generate(d).errors))
        d.pin_locks = {"CPU_A13": 7}            # TDI with JTAG kept
        self.assertIn("JTAG", " ".join(generate.generate(d).errors))
        d.keep_jtag = False
        self.assertTrue(generate.generate(d).ok)
        d.pin_locks = {"CPU_A13": 10}           # GND pin
        self.assertFalse(generate.generate(d).ok)

    def test_devices_payload_has_power(self):
        dev = api.devices_payload()["devices"][0]
        self.assertEqual(dev["pin_count"], 44)
        self.assertEqual(len(dev["power"]), 8)


class TestSimSession(unittest.TestCase):
    def test_tinytendo_decode_and_controller_reads(self):
        s = api.SimSession()
        d = dsg.load(EXAMPLE)
        b = s.build(d)
        self.assertTrue(b["ok"], b.get("error"))
        idle = {"OE1_n": 1, "OE2_n": 1, "M2": 0, "CPU_A13": 0, "CPU_A14": 0,
                "CPU_A15": 0, "PPU_A13": 0, "s4016_D0": 0, "s4016_D3": 0,
                "s4016_D4": 0, "s4017_D0": 0, "s4017_D3": 0, "s4017_D4": 0}
        st = s.step([idle])
        self.assertEqual(st["values"]["WRAM_CE_n"], 1)           # M2 low: nothing selected
        self.assertIsNone(st["values"]["CPU_D0"])                 # bus released (Z)
        st = s.step([{"M2": 1}])                                  # $0000: work RAM
        self.assertEqual((st["values"]["WRAM_CE_n"], st["values"]["PPU_CE_n"],
                          st["values"]["ROMSEL_n"]), (0, 1, 1))
        self.assertEqual(st["nets"]["Net-(U7A-E)"], 0)            # internal net visible
        st = s.step([{"CPU_A13": 1}])                             # $2000: PPU
        self.assertEqual((st["values"]["WRAM_CE_n"], st["values"]["PPU_CE_n"]), (1, 0))
        st = s.step([{"CPU_A15": 1}])                             # $8000+: ROM
        self.assertEqual(st["values"]["ROMSEL_n"], 0)
        st = s.step([{"OE1_n": 0, "s4016_D0": 0}])                # read $4016, button down
        self.assertEqual((st["values"]["CPU_D0"], st["values"]["CPU_D1"]), (1, 0))
        self.assertIsNone(st["values"]["CPU_D2"])                 # D2 not driven by port 1
        st = s.step([{"OE1_n": 1, "OE2_n": 0, "s4017_D0": 1}])    # read $4017
        self.assertEqual((st["values"]["CPU_D0"], st["values"]["CPU_D2"]), (0, 0))

    def test_clocked_design_and_rebuild_keeps_state(self):
        d = dsg.parse_text("""
            design cnt
            part U1 74x161
            net CLK ext: U1.2
            net LD ext: U1.9
            net Q0 ext: U1.14
            net Q1 ext: U1.13
            net VCC: U1.1 U1.7 U1.10
            net GND: U1.3 U1.4 U1.5 U1.6
        """)
        s = api.SimSession()
        self.assertTrue(s.build(d)["ok"])
        st = s.step([{"CLK": 0, "LD": 1}])
        self.assertIsNone(st["values"]["Q0"])                     # power-up state unknown
        st = s.step([{"LD": 0}, {"CLK": 1}, {"CLK": 0}, {"LD": 1}])   # load 0
        self.assertEqual((st["values"]["Q0"], st["values"]["Q1"]), (0, 0))
        st = s.step([{"CLK": 1}, {"CLK": 0}, {"CLK": 1}, {"CLK": 0}, {"CLK": 1}])
        self.assertEqual((st["values"]["Q0"], st["values"]["Q1"]), (1, 1))   # counted to 3
        self.assertEqual([x["Q0"] for x in st["trace"]], [1, 1, 0, 0, 1])    # per-step trace
        self.assertEqual([x["CLK"] for x in st["trace"]], [1, 0, 1, 0, 1])
        d.layout = {"U1": {"x": 500, "y": 9}}                     # not a logic change
        b = s.build(d)
        self.assertEqual((b["values"]["Q0"], b["values"]["Q1"]), (1, 1))     # state kept
        b = s.build(d, fresh=True)                                # explicit reset
        self.assertIsNone(b["values"]["Q0"])

    def test_missing_yosys_is_reported(self):
        import os
        old = os.environ.get("CPLDGLUE_YOSYS")
        os.environ["CPLDGLUE_YOSYS"] = str(ROOT / "no-such-yosys.exe")
        try:
            b = api.SimSession().build(dsg.load(EXAMPLE))
        finally:
            if old is None:
                del os.environ["CPLDGLUE_YOSYS"]
            else:
                os.environ["CPLDGLUE_YOSYS"] = old
        self.assertFalse(b["ok"])
        self.assertTrue(b["error"])


SCH = ROOT.parent / "Hardware" / "Motherboard" / "TinyTendo-schematic.kicad_sch"


@unittest.skipUnless(SCH.exists() and dsg.find_kicad_cli(), "needs KiCad + schematic")
class TestKiCadImport(unittest.TestCase):
    importer = api.KiCadImporter()

    def test_components_and_preview(self):
        comps = {c["ref"]: c for c in self.importer.components(SCH)["components"]}
        self.assertEqual(comps["U7"]["part"], "74x139")
        self.assertEqual(comps["U8"]["part"], "74x368")
        self.assertEqual(comps["U5"]["part"], "74x373")
        self.assertIsNone(comps["C1"]["part"])                       # capacitors: no model
        p = self.importer.preview(SCH, ["U5", "U7", "U8", "U9"])
        self.assertEqual((p["pins"], p["capacity"]), (39, 32))       # too many for 44 pins
        self.assertTrue(p["errors"])
        p = self.importer.preview(SCH, ["U7", "U8", "U9"])
        self.assertEqual((p["pins"], p["errors"]), (22, []))

    def test_import_matches_cli_and_keeps_project_settings(self):
        base = dsg.Design(name="mine", device="ATF1504AS", package="TQFP44")
        d = self.importer.design(SCH, ["U7", "U8", "U9"], base=base)
        self.assertEqual((d.name, d.device, d.package), ("mine", "ATF1504AS", "TQFP44"))
        cli = dsg.from_kicad(SCH, ["U7", "U8", "U9"], name="mine")
        cli.device, cli.package = "ATF1504AS", "TQFP44"
        self.assertEqual(canon(d), canon(cli))

    def test_find_schematics(self):
        files = api.find_schematics(ROOT)
        self.assertTrue(any(f.endswith("TinyTendo-schematic.kicad_sch") for f in files))


class TestBuilder(unittest.TestCase):
    def setUp(self):
        # Pretend nothing has been downloaded.
        self._home = os.environ.get("CPLDGLUE_HOME")
        os.environ["CPLDGLUE_HOME"] = tempfile.mkdtemp(prefix="cg_home_")

    def tearDown(self):
        if self._home is None:
            os.environ.pop("CPLDGLUE_HOME", None)
        else:
            os.environ["CPLDGLUE_HOME"] = self._home

    def test_missing_flow_files_point_to_setup(self):
        b = api.Builder(None, None)
        self.assertIsNone(b.config()["flow_dir"])
        out = Path(tempfile.mkdtemp(prefix="cg_build_"))
        res = b.build(dsg.load(EXAMPLE), out)
        self.assertFalse(res["ok"])
        self.assertIn("download them from Setup", res["log"])
        self.assertTrue((out / "tinytendo_glue.v").exists())       # sources still written
        self.assertTrue((out / "tinytendo_glue.pin").exists())

    def test_bad_flow_dir_is_explained(self):
        b = api.Builder(Path(tempfile.mkdtemp(prefix="cg_noflow_")), None)
        cfg = b.config(dsg.load(EXAMPLE))
        self.assertTrue(cfg["enabled"])
        self.assertFalse(cfg["flow_ok"])
        res = b.build(dsg.load(EXAMPLE), Path(tempfile.mkdtemp(prefix="cg_build_")))
        self.assertFalse(res["ok"])
        self.assertIn("cells.lib", res["log"])

    def test_report_errors_block_the_build(self):
        d = dsg.load(EXAMPLE)
        d.pin_locks = {"CPU_D0": 43}
        res = api.Builder(None, None).build(d, Path(tempfile.mkdtemp(prefix="cg_build_")))
        self.assertIn("Fix the report errors", res["log"])


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = api.Project(EXAMPLE)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.project))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.status, r.headers.get("Content-Type"), r.read()

    def post(self, path, obj):
        req = urllib.request.Request(self.base + path, json.dumps(obj).encode(),
                                     {"Content-Type": "application/json", "X-Cpldglue": "1"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_writes_need_our_header(self):
        req = urllib.request.Request(self.base + "/api/generate", b"{}",
                                     {"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)

    def test_foreign_host_is_refused(self):
        req = urllib.request.Request(self.base + "/api/project", headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)

    def test_examples_are_listed(self):
        _, _, body = self.get("/api/examples")
        ex = json.loads(body)["examples"]
        self.assertEqual([x["id"] for x in ex], ["tinytendo"])
        self.assertTrue((ROOT / "examples" / "tinytendo.cg").exists())

    def test_file_browser_lists_kicad_files(self):
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="fbtest_"))
        (root / "sub").mkdir()
        (root / ".hidden").mkdir()
        (root / "board-backups").mkdir()
        for n in ("b.kicad_sch", "A.kicad_sch", "nets.net", "board.kicad_pcb", "notes.txt"):
            (root / n).write_text("")
        r = self.post("/api/fs/list", {"path": str(root)})
        self.assertEqual(Path(r["path"]), root.resolve())
        self.assertEqual(r["dirs"], ["sub"])                        # no hidden / backup folders
        self.assertEqual(r["files"], ["A.kicad_sch", "b.kicad_sch", "nets.net"])
        self.assertEqual(Path(r["parent"]), root.resolve().parent)
        # a file path opens its folder; a missing one, the nearest real folder
        self.assertEqual(Path(self.post("/api/fs/list", {"path": str(root / "A.kicad_sch")})["path"]),
                         root.resolve())
        self.assertEqual(Path(self.post("/api/fs/list", {"path": str(root / "no" / "x")})["path"]),
                         root.resolve())
        self.assertTrue(r["roots"])
        # listing goes through the write check (our header), like other POSTs
        req = urllib.request.Request(self.base + "/api/fs/list", b'{"path": ""}',
                                     {"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(req)

    def test_deps_status(self):
        _, _, body = self.get("/api/deps")
        ids = [d["id"] for d in json.loads(body)["deps"]]
        self.assertEqual(ids, ["yosys", "flow", "fitter", "nextpnr", "gowin", "quartus", "kicad"])
        with self.assertRaises(urllib.error.HTTPError):
            self.post("/api/deps/fetch", {"id": "nonsense"})

    def test_project_and_generate(self):
        _, _, body = self.get("/api/project")
        proj = json.loads(body)
        self.assertEqual(proj["design"]["name"], "tinytendo_glue")
        g = self.post("/api/generate", {"design": proj["design"]})
        self.assertEqual(len(g["ports"]), 22)
        self.assertEqual(g["errors"], [])

    def test_bad_generate_request_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post("/api/generate", {"design": {"parts": 5}})
        self.assertEqual(cm.exception.code, 400)

    @unittest.skipUnless((ROOT / "cpldglue" / "gui" / "static" / "index.html").exists(),
                         "frontend not built")
    def test_serves_frontend(self):
        status, ctype, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"<div id=\"root\">", body)

    def test_put_saves_and_detects_conflicts(self):
        tmp = Path(tempfile.mkdtemp(prefix="cg_put_")) / "p.json"
        proj = api.Project(tmp)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(proj))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            design = json.loads(dsg.load(EXAMPLE).to_json())

            def put(obj):
                req = urllib.request.Request(base + "/api/project",
                                             json.dumps(obj).encode(),
                                             {"Content-Type": "application/json", "X-Cpldglue": "1"},
                                             method="PUT")
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())

            res = put({"design": design, "base_mtime": 0.0})
            self.assertFalse(res["conflict"])
            self.assertTrue(tmp.exists())
            with self.assertRaises(urllib.error.HTTPError) as cm:
                put({"design": design, "base_mtime": 1.0})
            self.assertEqual(cm.exception.code, 409)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_no_path_traversal(self):
        status, ctype, body = self.get("/..%2f..%2fcli.py")
        self.assertNotIn(b"argparse", body)


class TestFixtures(unittest.TestCase):
    def test_frontend_parts_fixture_is_current(self):
        # The gate-drawing test in the frontend reads this copy of /api/parts.
        f = ROOT / "cpldglue" / "gui" / "frontend" / "src" / "fixtures" / "parts.json"
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), api.parts_payload(),
                         "refresh it: save GET /api/parts to that file")


class TestAlternatives(unittest.TestCase):
    """Boards with "populate one of" chips (e.g. a 74x377 or two 74x161s in
    the MouseBite Labs discrete-mapper cartridge) have several chips driving
    the same nets; the import dialog should treat them as alternatives."""

    def test_chips_driving_the_same_nets_are_grouped(self):
        N = dsg.Node
        comps = {"U4A": "74LS377", "U4B": "74LS161", "U4C": "74LS161", "U5": "74LS32",
                 "U9": "74HC125", "U10": "74HC125"}
        nets = {
            "/Q_{0}": [N("U4A", "6"), N("U4B", "14"), N("U4C", "14"), N("U5", "13")],
            "/Q_{3}": [N("U4A", "16"), N("U4B", "11")],
            "/OUT": [N("U5", "3")],
            # two 3-state buffers sharing a bus are normal, not alternatives
            "/BUS": [N("U9", "3"), N("U10", "3")],
        }
        groups = api.alternatives(comps, nets)
        self.assertEqual(groups, [{"refs": ["U4A", "U4B", "U4C"], "nets": ["Q_{0}", "Q_{3}"]}])

    def test_kicad_escapes_in_names(self):
        self.assertEqual(generate.sanitize("/R{slash}~{W}"), "R_W_n")
        self.assertEqual(generate.sanitize("/Q_{0U}"), "Q_0U")


class TestBind(unittest.TestCase):
    def test_busy_port_moves_to_next(self):
        from http.server import BaseHTTPRequestHandler
        a = bind(BaseHTTPRequestHandler, 0)          # any free port
        try:
            port = a.server_address[1]
            b = bind(BaseHTTPRequestHandler, port)
            try:
                self.assertNotEqual(b.server_address[1], port)
            finally:
                b.server_close()
        finally:
            a.server_close()


if __name__ == "__main__":
    unittest.main()
