#!/usr/bin/env python3
"""Check that handoff files contain the six mandatory parts (CLAUDE.md §6).

usage: python3 GLOBAL/tools/check_handoff.py <handoff.md> [...]
       python3 GLOBAL/tools/check_handoff.py --project <slug>   # every handoff of a project
Exit code 0 = all complete, 1 = at least one incomplete. Standard library only.
"""
import re, sys, glob, os

FRONT = ["project", "task_id", "agent", "status", "next_agent", "task_board_update"]
SECTIONS = ["Completed", "Evidence", "Unresolved questions", "Next agent must"]
STATUSES = {"COMPLETE", "PARTIAL", "BLOCKED", "NEEDS_CONTEXT", "REVISION_REQUIRED"}

def check(path):
    text = open(path, encoding="utf-8").read()
    problems = []
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        return ["missing YAML front matter"]
    front = dict(re.findall(r"^([a-z_]+):\s*(.*?)\s*$", m.group(1), re.M))
    for key in FRONT:
        value = front.get(key, "").strip('"')
        if not value or "<" in value or "|" in value:
            problems.append(f"front matter '{key}' missing or still a placeholder")
    status = front.get("status", "").strip('"').split()[0] if front.get("status") else ""
    if status and status not in STATUSES:
        problems.append(f"status '{status}' is not one of {sorted(STATUSES)}")
    body = text[m.end():]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    for name in SECTIONS:
        sm = re.search(rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
        if not sm:
            problems.append(f"section '## {name}' missing")
        elif not sm.group(1).strip() or re.fullmatch(r"(\s*[-|].*<[^>]+>.*\n?)+", sm.group(1)):
            problems.append(f"section '## {name}' empty or still a placeholder")
    return problems

def main(argv):
    if len(argv) == 3 and argv[1] == "--project":
        files = sorted(glob.glob(os.path.join("PROJECTS", argv[2], "HANDOFFS", "*.md")))
    else:
        files = argv[1:]
    if not files:
        print("no handoff files given/found"); return 0
    bad = 0
    for f in files:
        p = check(f)
        print(("OK        " if not p else "INCOMPLETE") + f"  {f}")
        for x in p:
            print(f"          - {x}")
        bad += bool(p)
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
