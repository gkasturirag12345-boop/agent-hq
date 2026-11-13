"""Dashboard D1 tests. Standard library only.

run: python3 -B -m unittest discover tests
Fixtures under tests/fixtures/ and the demo under examples/ are synthetic example data.
"""
import os
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "agent_hq"))
import parse  # noqa: E402

PKG = os.path.abspath(os.path.join(HERE, "..", "agent_hq"))
DEMO = os.path.abspath(os.path.join(HERE, "..", "examples", "demo-workspace"))
FIX = os.path.join(HERE, "fixtures", "ws")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.ov = parse.overview(FIX)
        self.p = self.ov["projects"][0]
        self.texts = [w["text"] for w in self.p["warnings"]]

    def test_discovery(self):
        self.assertEqual([p["slug"] for p in self.ov["projects"]], ["demo-fixture"])
        self.assertEqual(sorted(a["name"] for a in self.ov["agents"]), ["alpha", "beta"])
        self.assertTrue(any("ghost-project" in w["text"] for w in self.ov["warnings"]))

    def test_board_rows_and_lines(self):
        tasks = {t["id"]: t for t in self.p["board"]["tasks"]}
        self.assertEqual(tasks["X-001"]["status"], "DONE")
        self.assertEqual(tasks["X-001"]["source"], "PROJECTS/demo-fixture/TASK_BOARD.md:9")
        self.assertFalse(tasks["X-003"]["status_known"])

    def test_warnings_are_reported_not_corrected(self):
        self.assertTrue(any("X-002: board says IN_REVIEW" in t and "BLOCKED" in t for t in self.texts))
        self.assertTrue(any("20260101-1200-alpha-X-003.md does not exist" in t for t in self.texts))
        self.assertTrue(any("WAITING" in t for t in self.texts))
        self.assertTrue(any("checker INCOMPLETE" in t and "Evidence" in t for t in self.texts))
        board = {t["id"]: t["status"] for t in self.p["board"]["tasks"]}
        self.assertEqual(board["X-002"], "IN_REVIEW")  # unchanged

    def test_symlinked_records_are_skipped(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "ws"); shutil.copytree(FIX, ws)
            outside = os.path.join(tmp, "outside.md")
            with open(outside, "w") as fh:
                fh.write("---\nproject: demo-fixture\ntask_id: X-001\nagent: alpha\nstatus: COMPLETE\n---\nOUTSIDE-SECRET\n")
            os.symlink(outside, os.path.join(ws, "PROJECTS", "demo-fixture", "HANDOFFS", "20990101-0000-alpha-X-001.md"))
            os.symlink(tmp, os.path.join(ws, "PROJECTS", "linked-out"))
            ov = parse.overview(ws)
            self.assertEqual([p["slug"] for p in ov["projects"]], ["demo-fixture"])
            self.assertNotIn("20990101-0000-alpha-X-001.md", [h["file"] for h in ov["projects"][0]["handoffs"]])

    def test_arrow_uses_own_task_id(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "ws"); shutil.copytree(FIX, ws)
            hf = os.path.join(ws, "PROJECTS", "demo-fixture", "HANDOFFS", "20260101-1100-beta-X-002.md")
            with open(hf, encoding="utf-8") as fh:
                text = fh.read().replace('task_board_update: "X-002 → BLOCKED (alpha)"', 'task_board_update: "X-009 → DONE; X-002 → IN_REVIEW"')
            with open(hf, "w", encoding="utf-8") as fh:
                fh.write(text)
            h = next(x for x in parse.handoffs(ws, "demo-fixture") if x["task_id"] == "X-002")
            self.assertEqual(h["proposed_status"], "IN_REVIEW")      # not the first arrow (DONE)

    def test_unreadable_handoff_becomes_warning(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "ws"); shutil.copytree(FIX, ws)
            with open(os.path.join(ws, "PROJECTS", "demo-fixture", "HANDOFFS", "20260101-1300-alpha-X-001.md"), "wb") as fh:
                fh.write(b"---\n\xff\xfe not utf-8\n---\n")
            p = parse.overview(ws)["projects"][0]
            self.assertTrue(any("could not read file (UnicodeDecodeError)" in w["text"] for w in p["warnings"]))

    def test_agent_without_name_or_unreadable(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "ws"); shutil.copytree(FIX, ws)
            with open(os.path.join(ws, ".claude", "agents", "noname.md"), "w") as fh:
                fh.write("---\nmodel: haiku\n---\nTEST FIXTURE\n")
            with open(os.path.join(ws, ".claude", "agents", "binary.md"), "wb") as fh:
                fh.write(b"---\nname: \xff\xfe\n---\n")
            with open(os.path.join(ws, "PROJECTS", "demo-fixture", "TASK_BOARD.md"), "wb") as fh:
                fh.write(b"| ID | Task |\n|---|---|\n| \xff | x |\n")
            ov = parse.overview(ws)
            names = sorted(a["name"] for a in ov["agents"])
            self.assertEqual(names, ["alpha", "beta", "binary", "noname"])     # never None
            self.assertTrue(any("not readable as UTF-8" in w["text"] for w in ov["projects"][0]["warnings"]))

    def test_task_id_match_needs_boundary(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ws = os.path.join(tmp, "ws"); shutil.copytree(FIX, ws)
            hf = os.path.join(ws, "PROJECTS", "demo-fixture", "HANDOFFS", "20260101-1100-beta-X-002.md")
            text = open(hf, encoding="utf-8").read().replace('task_board_update: "X-002 → BLOCKED (alpha)"', 'task_board_update: "XX-002 → DONE; X-002 → IN_REVIEW"')
            open(hf, "w", encoding="utf-8").write(text)
            h = next(x for x in parse.handoffs(ws, "demo-fixture") if x["task_id"] == "X-002")
            self.assertEqual(h["proposed_status"], "IN_REVIEW")

    def test_owner_match_is_whole_name(self):
        alpha = next(a for a in self.ov["agents"] if a["name"] == "alpha")
        self.assertEqual([t["id"] for t in alpha["owned_tasks"]], ["X-001"])  # not 'alpha-beta'


class DemoWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ov = parse.overview(DEMO)

    def test_agents_match_definitions(self):
        files = [f for f in os.listdir(os.path.join(DEMO, ".claude", "agents")) if f.endswith(".md")]
        self.assertEqual(len(self.ov["agents"]), len(files))
        self.assertTrue(all(a["name"] and a["model"] for a in self.ov["agents"]))

    def test_task_boards_match_files(self):
        for p in self.ov["projects"]:
            with open(os.path.join(DEMO, "PROJECTS", p["slug"], "TASK_BOARD.md"), encoding="utf-8") as fh:
                lines = [l.strip() for l in fh if l.strip().startswith("|")]
            header = [c.strip() for c in lines[0].strip("|").split("|")]
            rows = [[c.strip() for c in l.strip("|").split("|")] for l in lines[2:]]
            self.assertEqual(len(p["board"]["tasks"]), len(rows))
            for t, cells in zip(p["board"]["tasks"], rows):
                self.assertEqual((t["id"], t["status"]), (cells[header.index("ID")], cells[header.index("Status")]))

    def test_checker_matches_cli(self):
        for p in self.ov["projects"]:
            out = subprocess.run([sys.executable, "-B", os.path.join(PKG, "check_handoff.py"), "--project", p["slug"]],
                                 cwd=DEMO, capture_output=True, text=True).stdout
            cli = {os.path.basename(l.split()[1]): l.split()[0] for l in out.splitlines() if l.startswith(("OK", "INCOMPLETE"))}
            mine = {h["file"]: ("OK" if h["checker"] == "PASS" else "INCOMPLETE") for h in p["handoffs"]}
            self.assertEqual(cli, mine)

    def test_demo_shows_its_deliberate_warnings(self):
        texts = [w["text"] for p in self.ov["projects"] for w in p["warnings"]]
        self.assertTrue(any("W-003: board says IN_PROGRESS" in t for t in texts))
        self.assertTrue(any("checker INCOMPLETE" in t for t in texts))

    def test_no_bytecode_written(self):
        for d, _, _ in os.walk(os.path.dirname(PKG)):
            self.assertNotEqual(os.path.basename(d), "__pycache__", d)


if __name__ == "__main__":
    unittest.main()
