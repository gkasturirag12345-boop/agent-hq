"""Dashboard D2 tests: observed activity from transcript metadata. Standard library only.

All transcripts here are synthetic TEST FIXTURES written to a temporary directory.
"""
import json
import os
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent_hq"))
import live  # noqa: E402

SECRET = "TEST-FIXTURE-SECRET-do-not-leak-7f3a"


def rec(kind, ts, tools=(), text=SECRET):
    content = [{"type": "text", "text": text}]
    content += [{"type": "tool_use", "name": n, "input": {"command": SECRET, "file_path": "/Users/x/" + SECRET}} for n in tools]
    return json.dumps({"type": kind, "timestamp": ts, "cwd": "/Users/x/" + SECRET,
                       "message": {"role": kind, "content": content}})


class Live(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.repo = os.path.join(self.home, "Dev", "My_Repo")
        self.base = live.transcripts_dir(self.repo, self.home)
        os.makedirs(self.base)
        self.now = time.time()
        live._cache.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, lines, age_s):
        p = os.path.join(self.base, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        os.utime(p, (self.now - age_s, self.now - age_s))
        return p

    def meta(self, rel, agent_type, finished):
        p = os.path.join(self.base, rel)
        with open(p, "w") as fh:
            json.dump({"agentType": agent_type, "finished": finished, "description": SECRET,
                       "toolUseId": SECRET, "spawnDepth": 1}, fh)

    def test_no_username_or_path_in_output(self):
        self.write("gggggggg-7.jsonl", [rec("assistant", "t", ["Read"])], 1)
        dumped = json.dumps(live.scan(self.repo, self.now, self.home))
        dashed = os.path.basename(self.base)
        self.assertNotIn(dashed, dumped)
        self.assertNotIn(self.home, dumped)
        self.assertNotIn(os.path.basename(self.home), dumped)

    def test_symlinked_transcripts_skipped(self):
        target = os.path.join(self.home, "elsewhere.jsonl")
        with open(target, "w") as fh:
            fh.write(rec("assistant", "t", ["Read"]) + "\n")
        os.symlink(target, os.path.join(self.base, "hhhhhhhh-8.jsonl"))
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"], [])

    def _small_limits(self):
        old = (live.MAX_LINE, live.BLOCK)
        live.MAX_LINE, live.BLOCK = 4096, 1024          # so the skip branch really runs
        self.addCleanup(lambda: setattr(live, "MAX_LINE", old[0]) or setattr(live, "BLOCK", old[1]))

    def test_overlong_line_skipped_and_scanning_continues(self):
        self._small_limits()
        huge = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "HugeTool", "input": "x" * 20000}]}})
        p = self.write("iiiiiiii-9.jsonl", [rec("assistant", "a", ["Before"]), huge], 1)
        s = live.scan(self.repo, self.now, self.home)["sessions"][0]
        self.assertEqual(s["last_tool"], "Before")      # HugeTool is never parsed or reported
        with open(p, "a") as fh:
            fh.write(rec("assistant", "b", ["After"]) + "\n")
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"][0]["last_tool"], "After")

    def test_overlong_line_spanning_two_scans(self):
        self._small_limits()
        p = self.write("iiiiiiii-13.jsonl", [rec("assistant", "a", ["Before"])], 1)
        with open(p, "a") as fh:                        # an unfinished 10 KB line containing a tool name
            fh.write('{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "HugeTool", "input": "' + "x" * 10000)
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"][0]["last_tool"], "Before")
        with open(p, "a") as fh:                        # the long line ends, then a normal one follows
            fh.write("x" * 3000 + '"}]}}\n' + rec("assistant", "b", ["After"]) + "\n")
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"][0]["last_tool"], "After")

    def test_same_size_rewrite_restarts(self):
        p = self.write("mmmmmmmm-14.jsonl", [rec("assistant", "a", ["AAAA"])], 1)
        live.scan(self.repo, self.now, self.home)
        with open(p, "r+") as fh:
            fh.write(rec("assistant", "a", ["BBBB"]) + "\n")   # identical length
        os.utime(p, (self.now, self.now + 5))
        self.assertEqual(live.scan(self.repo, self.now + 5, self.home)["sessions"][0]["last_tool"], "BBBB")

    def test_unparseable_deep_json_is_ignored(self):
        deep = '{"tool_use": ' + "[" * 100000 + "]" * 100000 + "}"
        self.write("nnnnnnnn-15.jsonl", [rec("assistant", "a", ["Good"]), deep], 1)
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"][0]["last_tool"], "Good")

    def test_in_place_rewrite_restarts(self):
        p = self.write("jjjjjjjj-10.jsonl", [rec("assistant", "a", ["First"])], 1)
        live.scan(self.repo, self.now, self.home)
        with open(p, "r+") as fh:                       # same inode, different content, longer file
            fh.write(rec("assistant", "z", ["Rewritten"]) + "\n" + rec("user", "pad", text="y" * 50) + "\n")
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"][0]["last_tool"], "Rewritten")

    def test_old_unfinished_run_is_dormant_not_unknown(self):
        self.write("kkkkkkkk-11.jsonl", [rec("assistant", "t", ["Agent"])], 1)
        self.write("kkkkkkkk-11/subagents/agent-old.jsonl", [rec("assistant", "t", ["Read"])], 7200)
        self.meta("kkkkkkkk-11/subagents/agent-old.meta.json", "coder", False)
        r = live.scan(self.repo, self.now, self.home)["sessions"][0]["subagents"][0]
        self.assertEqual(r["state"], "dormant")

    def test_runs_older_than_window_are_not_read(self):
        self.write("llllllll-12.jsonl", [rec("assistant", "t", ["Agent"])], 1)
        self.write("llllllll-12/subagents/agent-old.jsonl", [rec("assistant", "t", ["Read"])], 3 * 86400)
        self.meta("llllllll-12/subagents/agent-old.meta.json", "coder", True)
        r = live.scan(self.repo, self.now, self.home)["sessions"][0]["subagents"][0]
        self.assertEqual((r["last_tool"], r["tool_read"]), (None, False))

    def test_malformed_meta_files_do_not_break_scan(self):
        self.write("oooooooo-16.jsonl", [rec("assistant", "t", ["Agent"])], 1)
        bad = {"list": "[]", "number": "42", "null": "null", "deep": "[" * 100000 + "]" * 100000, "big": json.dumps({"agentType": "x" * 70000})}
        for name, body in bad.items():
            self.write(f"oooooooo-16/subagents/agent-{name}.jsonl", [rec("assistant", "t", ["Read"])], 2)
            with open(os.path.join(self.base, f"oooooooo-16/subagents/agent-{name}.meta.json"), "w") as fh:
                fh.write(body)
        runs = live.scan(self.repo, self.now, self.home)["sessions"][0]["subagents"]
        self.assertEqual(len(runs), 5)
        self.assertTrue(all(r["agent_type"] is None and r["meta_pending"] for r in runs))

    def test_folder_name_is_derived_from_repo_path(self):
        self.assertTrue(self.base.endswith(os.path.join(".claude", "projects", "-" + self.repo.strip("/").replace("/", "-").replace("_", "-"))))

    def test_states_and_tools(self):
        self.write("aaaaaaaa-1.jsonl", [rec("user", "t0"), rec("assistant", "t1", ["Read"]), rec("assistant", "t2", ["Agent"])], 10)
        sub = "aaaaaaaa-1/subagents/agent-run1.jsonl"
        self.write(sub, [rec("assistant", "t3", ["Grep", "Read"])], 100)
        self.meta("aaaaaaaa-1/subagents/agent-run1.meta.json", "verifier", False)
        self.write("aaaaaaaa-1/subagents/agent-run2.jsonl", [rec("assistant", "t4", ["Write"])], 900)
        self.meta("aaaaaaaa-1/subagents/agent-run2.meta.json", "coder", False)       # stale, not finished
        self.write("aaaaaaaa-1/subagents/agent-run3.jsonl", [rec("assistant", "t5")], 5)
        self.meta("aaaaaaaa-1/subagents/agent-run3.meta.json", "analyst", True)
        out = live.scan(self.repo, self.now, self.home)
        s = out["sessions"][0]
        self.assertEqual((s["id8"], s["state"], s["last_tool"], s["last_tool_ts"]), ("aaaaaaaa", "active", "Agent", "t2"))
        runs = {r["agent_type"]: r for r in s["subagents"]}
        self.assertEqual((runs["verifier"]["state"], runs["verifier"]["last_tool"]), ("recent", "Read"))
        self.assertEqual(runs["coder"]["state"], "unknown")
        self.assertEqual(runs["analyst"]["state"], "ended")
        self.assertIsNone(runs["analyst"]["last_tool"])
        self.assertEqual(set(out["agents"]), {"verifier", "coder", "analyst"})

    def test_no_content_leaks(self):
        self.write("bbbbbbbb-2.jsonl", [rec("assistant", "t1", ["Bash"])], 1)
        self.write("bbbbbbbb-2/subagents/agent-x.jsonl", [rec("assistant", "t2", ["Edit"])], 1)
        self.meta("bbbbbbbb-2/subagents/agent-x.meta.json", "researcher", False)
        dumped = json.dumps(live.scan(self.repo, self.now, self.home))
        for bad in (SECRET, "description", "cwd", "input", "/Users/x"):
            self.assertNotIn(bad, dumped)

    def test_only_workspace_folder_scanned(self):
        other = os.path.join(self.home, ".claude", "projects", "-Users-someone-else")
        os.makedirs(other)
        with open(os.path.join(other, "cccccccc.jsonl"), "w") as fh:
            fh.write(rec("assistant", "t", ["Read"]) + "\n")
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"], [])

    def test_old_sessions_hidden_and_missing_folder(self):
        self.write("dddddddd-4.jsonl", [rec("assistant", "t", ["Read"])], 3 * 86400)
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"], [])
        self.assertFalse(live.scan(os.path.join(self.home, "nope"), self.now, self.home)["available"])

    def test_incremental_read_finds_tools_behind_large_records(self):
        big = [rec("assistant", "early", ["EarlyTool"])] + [rec("attachment", "pad", text="x" * 100000)] * 3
        p = self.write("eeeeeeee-5.jsonl", big, 1)
        self.assertEqual(live.scan(self.repo, self.now, self.home)["sessions"][0]["last_tool"], "EarlyTool")
        with open(p, "a") as fh:
            fh.write(rec("assistant", "late", ["LateTool"]) + "\n" + '{"type": "partial')   # incomplete last line
        s = live.scan(self.repo, self.now, self.home)["sessions"][0]
        self.assertEqual((s["last_tool"], s["last_tool_ts"]), ("LateTool", "late"))

    def test_missing_meta_uses_transcript_writes(self):
        self.write("ffffffff-6.jsonl", [rec("assistant", "t", ["Agent"])], 1)
        self.write("ffffffff-6/subagents/agent-new.jsonl", [rec("assistant", "t", ["Read"])], 2)
        r = live.scan(self.repo, self.now, self.home)["sessions"][0]["subagents"][0]
        self.assertEqual((r["state"], r["agent_type"], r["meta_pending"]), ("active", None, True))
        self.write("ffffffff-6/subagents/agent-old.jsonl", [rec("assistant", "t", ["Read"])], 600)
        runs = live.scan(self.repo, self.now, self.home)["sessions"][0]["subagents"]
        self.assertEqual([x["state"] for x in runs if x["run_id"] == "old"], ["unknown"])


if __name__ == "__main__":
    unittest.main()
