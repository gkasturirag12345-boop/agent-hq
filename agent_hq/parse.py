"""Read-only parsers for the workspace's Markdown records.

Everything here only opens files for reading. Nothing is inferred: a value
that is missing or cannot be parsed is returned as None and shown as
"not recorded" by the dashboard. Standard library only.
"""
import glob
import os
import re
import sys

sys.dont_write_bytecode = True  # never create __pycache__ inside a workspace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_handoff  # noqa: E402  (the handoff checker, also usable on its own)

STATUSES = ["TODO", "IN_PROGRESS", "NEEDS_CONTEXT", "IN_REVIEW",
            "REVISION_REQUIRED", "BLOCKED", "APPROVED", "DONE"]
HANDOFF_RE = re.compile(r"HANDOFFS/([\w.\-]+\.md)")
ARROW_RE = re.compile(r"(?:→|->)\s*([A-Z_]+)")


def inside(root, path):
    """True for regular, non-symlinked paths that resolve inside root (symlinks are never followed)."""
    if os.path.islink(path):
        return False
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base + os.sep)


def safe_glob(root, *parts):
    return [p for p in sorted(glob.glob(os.path.join(root, *parts))) if inside(root, p)]


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def read_or_none(path):
    """Text of a record, or None if it vanished or is not UTF-8 (the page reports it instead of failing)."""
    try:
        return read(path)
    except (OSError, UnicodeDecodeError):
        return None


def front_matter(text):
    """Return (dict, end_offset) of a leading '---' YAML block; ({}, 0) if none."""
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}, 0
    fields = {}
    for key, value in re.findall(r"^([A-Za-z_]+):\s*(.*?)\s*$", m.group(1), re.M):
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key] = value
    return fields, m.end()


def md_table(text, first_header):
    """Rows of the first Markdown table whose first header cell is `first_header`.

    Returns (headers, [(line_number, {header: cell})]).
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = _cells(line)
        if cells and cells[0] == first_header:
            headers, rows = cells, []
            for j in range(i + 2, len(lines)):  # skip the |---| separator
                if not lines[j].lstrip().startswith("|"):
                    break
                row = _cells(lines[j])
                rows.append((j + 1, dict(zip(headers, row + [""] * (len(headers) - len(row))))))
            return headers, rows
    return [], []


def _cells(line):
    line = line.strip()
    if not line.startswith("|"):
        return []
    return [c.strip() for c in line.strip("|").split("|")]


def agents(root):
    """Agent definitions from .claude/agents/*.md front matter."""
    out = []
    for path in safe_glob(root, ".claude", "agents", "*.md"):
        try:
            fm, _ = front_matter(read(path))
        except (OSError, UnicodeDecodeError):
            fm = {}
        out.append({
            "name": fm.get("name") or os.path.splitext(os.path.basename(path))[0],   # fall back to the file name
            "model": fm.get("model") or None,
            "tools": [t.strip() for t in fm.get("tools", "").split(",") if t.strip()],
            "source": os.path.relpath(path, root),
        })
    return out


def registry(root):
    path = os.path.join(root, "GLOBAL", "PROJECT_REGISTRY.md")
    if not os.path.exists(path) or not inside(root, path):
        return {}
    text = read_or_none(path)
    if text is None:
        return {}
    _, rows = md_table(text, "Slug")
    return {r["Slug"]: dict(r, source_line=n) for n, r in rows if r.get("Slug")}


def project_slugs(root):
    return sorted(os.path.basename(os.path.dirname(p)) for p in safe_glob(root, "PROJECTS", "*", "PROJECT.md")
                  if inside(root, os.path.dirname(p)))


def handoffs(root, slug):
    out = []
    for path in safe_glob(root, "PROJECTS", slug, "HANDOFFS", "*.md"):
        try:
            fm, _ = front_matter(read(path))
            problems = check_handoff.check(path)
        except (OSError, UnicodeDecodeError) as exc:   # deleted mid-scan or not UTF-8: report, don't fail the page
            fm, problems = {}, [f"could not read file ({type(exc).__name__})"]
        update = fm.get("task_board_update") or None
        tid = fm.get("task_id") or ""
        m = (re.search(rf"(?<![\w-]){re.escape(tid)}\s*(?:→|->)\s*([A-Z_]+)", update or "") if tid else None) or ARROW_RE.search(update or "")
        out.append({
            "file": os.path.basename(path),
            "source": os.path.relpath(path, root),
            "project": fm.get("project") or None,
            "task_id": fm.get("task_id") or None,
            "agent": fm.get("agent") or None,
            "date": fm.get("date") or None,
            "status": fm.get("status") or None,           # agent-reported, not task completion
            "next_agent": fm.get("next_agent") or None,
            "task_board_update": update,
            "proposed_status": m.group(1) if m else None,
            "checker": "PASS" if not problems else "INCOMPLETE",
            "checker_problems": problems,
        })
    return out


def task_board(root, slug):
    rel = os.path.join("PROJECTS", slug, "TASK_BOARD.md")
    path = os.path.join(root, rel)
    if not os.path.exists(path) or not inside(root, path):
        return {"source": rel, "updated": None, "tasks": [], "missing": True}
    text = read_or_none(path)
    if text is None:
        return {"source": rel, "updated": None, "tasks": [], "missing": True}
    fm, _ = front_matter(text)
    _, rows = md_table(text, "ID")
    tasks = []
    for line_no, r in rows:
        status = r.get("Status", "").strip() or None
        tasks.append({
            "id": r.get("ID") or None,
            "title": r.get("Task") or None,
            "owner": r.get("Owner") or None,
            "status": status,
            "status_known": status in STATUSES,
            "depends_on": r.get("Depends on") or None,
            "latest_handoff_text": r.get("Latest handoff") or None,
            "linked_handoffs": HANDOFF_RE.findall(r.get("Latest handoff", "")),
            "source": f"{rel}:{line_no}",
        })
    return {"source": rel, "updated": fm.get("updated") or None, "tasks": tasks, "missing": False}


def project(root, slug, agent_names=None):
    """Everything D1 shows for one project, plus consistency warnings (never corrections)."""
    reg = registry(root).get(slug)
    board = task_board(root, slug)
    hos = handoffs(root, slug)
    state_fm = {}
    state_path = os.path.join(root, "PROJECTS", slug, "CURRENT_STATE.md")
    if os.path.exists(state_path) and inside(root, state_path):
        state_fm, _ = front_matter(read_or_none(state_path) or "")

    warnings = []
    if reg is None:
        warnings.append({"kind": "registry", "text": f"'{slug}' has a PROJECT.md but no row in GLOBAL/PROJECT_REGISTRY.md"})
    if board["missing"]:
        warnings.append({"kind": "board", "text": f"{board['source']} not found or not readable as UTF-8"})
    files = {h["file"] for h in hos}
    task_ids = {t["id"] for t in board["tasks"]}
    for t in board["tasks"]:
        if not t["status_known"]:
            warnings.append({"kind": "status", "source": t["source"],
                             "text": f"{t['id']}: status '{t['status']}' is not one of the defined statuses"})
        for f in t["linked_handoffs"]:
            if f not in files:
                warnings.append({"kind": "link", "source": t["source"],
                                 "text": f"{t['id']}: linked handoff HANDOFFS/{f} does not exist"})
        mine = [h for h in hos if h["task_id"] == t["id"]]
        if mine:
            latest = mine[-1]  # handoff files sort by their YYYYMMDD-HHMM prefix
            if latest["proposed_status"] and latest["proposed_status"] != t["status"]:
                warnings.append({"kind": "mismatch", "source": t["source"],
                                 "text": (f"{t['id']}: board says {t['status']}, but the latest handoff by filename "
                                          f"({latest['file']}) proposed {latest['proposed_status']}")})
    for h in hos:
        if h["project"] and h["project"] != slug:
            warnings.append({"kind": "project", "source": h["source"],
                             "text": f"{h['file']}: front matter project '{h['project']}' differs from folder '{slug}'"})
        if h["task_id"] and h["task_id"] not in task_ids:
            warnings.append({"kind": "task", "source": h["source"],
                             "text": f"{h['file']}: task {h['task_id']} is not on the task board"})
        if h["checker"] != "PASS":
            warnings.append({"kind": "checker", "source": h["source"],
                             "text": f"{h['file']}: handoff checker INCOMPLETE ({'; '.join(h['checker_problems'])})"})
        if agent_names is not None and h["agent"] and h["agent"] not in agent_names:
            warnings.append({"kind": "agent", "source": h["source"],
                             "text": f"{h['file']}: agent '{h['agent']}' is not a defined agent"})

    return {
        "slug": slug,
        "registry": reg,
        "board_updated": board["updated"],
        "state_updated": state_fm.get("updated") or None,
        "board": board,
        "handoffs": hos,
        "warnings": warnings,
    }


def owners_mention(owner_text, name):
    return bool(owner_text) and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", owner_text) is not None


def overview(root):
    defined = agents(root)
    names = {a["name"] for a in defined if a["name"]}
    reg = registry(root)
    slugs = project_slugs(root)
    projects = [project(root, s, names) for s in slugs]
    warnings = [{"kind": "registry", "text": f"registry row '{s}' has no PROJECTS/{s}/PROJECT.md"}
                for s in reg if s not in slugs]
    agent_cards = []
    for a in defined:
        last, tasks = None, []
        for p in projects:
            for h in p["handoffs"]:
                if h["agent"] == a["name"] and (last is None or h["file"][:13] > last["file"][:13]):
                    last = dict(h, slug=p["slug"])
            tasks += [{"slug": p["slug"], "id": t["id"], "status": t["status"]}
                      for t in p["board"]["tasks"] if owners_mention(t["owner"], a["name"])]
        n = sum(h["agent"] == a["name"] for p in projects for h in p["handoffs"])
        agent_cards.append(dict(a, last_handoff=last, handoff_count=n, owned_tasks=tasks))
    return {"agents": agent_cards, "projects": projects, "warnings": warnings, "statuses": STATUSES}
