"""Observed live activity for the dashboard. Read-only, standard library only.

Reads only the workspace's own Claude Code transcript folder and keeps only
file metadata, the `agentType`/`finished` fields of sub-agent meta files, and
the names and timestamps of tool calls. Transcripts are read incrementally in
1 MiB blocks (only bytes added since the previous scan, and only for files
written within the live window); lines containing a "tool_use" marker are
parsed in memory and only the tool name and record timestamp are kept.
Message text, tool inputs and results, prompts and descriptions are never
kept or returned. Symlinks are skipped.
"""
import glob
import json
import os
import re
import threading
import time
from datetime import datetime, timezone

WINDOW_S = 24 * 3600          # sessions shown in the live panel
ACTIVE_S, RECENT_S, IDLE_S = 30, 300, 3600
BLOCK = 1 << 20               # read size
MAX_LINE = 8 << 20            # longer lines are skipped, never buffered further
_cache = {}                   # path -> (offset, inode, size, mtime_ns, (last_tool, last_tool_ts), skipping); in memory only
_lock = threading.Lock()      # one scan of a file at a time (several tabs may poll together)


def transcripts_dir(repo_root, home=None):
    name = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(repo_root))
    return os.path.join(home or os.path.expanduser("~"), ".claude", "projects", name)


def state_for(age_s):
    if age_s is None:
        return "unknown"
    if age_s < ACTIVE_S:
        return "active"
    if age_s < RECENT_S:
        return "recent"
    if age_s < IDLE_S:
        return "idle"
    return "dormant"


def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _tool_from_line(raw, found):
    if b'"tool_use"' not in raw:
        return found
    try:
        rec = json.loads(raw)
    except (ValueError, RecursionError):
        return found
    msg = rec.get("message") if isinstance(rec, dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, list):
        return found
    names = [b.get("name") for b in content
             if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("name"), str)]
    if not names:
        return found
    ts = rec.get("timestamp")
    return names[-1], ts if isinstance(ts, str) else None


def last_tool(path):
    """(tool_name, timestamp) of the newest tool call in the file, or (None, None)."""
    with _lock:
        return _last_tool(path)


def _last_tool(path):
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    offset, inode, size, mtime_ns, found, skipping = _cache.get(path, (0, None, None, None, (None, None), False))
    try:
        with open(path, "rb") as fh:
            if (inode != st.st_ino or (size is not None and st.st_size < size)  # new, replaced or truncated
                    or st.st_size < offset
                    or (st.st_size == size and st.st_mtime_ns != mtime_ns)):   # rewritten in place at the same size
                offset, found, skipping = 0, (None, None), False
            elif offset and not skipping:                      # rewritten in place? the byte before must end a line
                fh.seek(offset - 1)
                if fh.read(1) != b"\n":
                    offset, found = 0, (None, None)
            fh.seek(offset)
            pending = b""
            while offset + len(pending) < st.st_size:
                block = fh.read(min(BLOCK, st.st_size - offset - len(pending)))
                if not block:
                    break
                pending += block
                *lines, pending = pending.split(b"\n")
                for raw in lines:
                    offset += len(raw) + 1
                    if skipping:                               # tail of an over-long line
                        skipping = False
                        continue
                    found = _tool_from_line(raw, found)
                if len(pending) > MAX_LINE:                    # drop an over-long line without parsing it
                    offset += len(pending)
                    pending, skipping = b"", True
    except OSError:
        return found
    _cache[path] = (offset, st.st_ino, st.st_size, st.st_mtime_ns, found, skipping)   # skipping persists across scans
    return found


def _meta(path):
    """Only agentType and finished are taken from a sub-agent meta file."""
    try:
        if os.path.getsize(path) > 64 * 1024:          # meta files are tiny; refuse anything else
            return None, None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, RecursionError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    agent_type = data.get("agentType") if isinstance(data.get("agentType"), str) else None
    finished = data.get("finished") if isinstance(data.get("finished"), bool) else None
    return agent_type, finished


def _subagent(jsonl, now):
    mtime = _mtime(jsonl)
    if mtime is None:
        return None
    age = max(0, int(now - mtime))
    meta = jsonl[:-len(".jsonl")] + ".meta.json"
    agent_type, finished = (None, None) if os.path.islink(meta) else _meta(meta)
    if finished is True:
        state = "ended"
    elif age < RECENT_S:
        # running: `finished` is only set when the run ends (observed in real runs),
        # so the run's own transcript writes are the evidence
        state = state_for(age)
    elif age < IDLE_S:
        state = "unknown"          # not marked finished and no writes for 5 min
    else:
        state = "dormant"          # not marked finished, no writes for over 1 h
    tool, tool_ts = last_tool(jsonl) if age < WINDOW_S else (None, None)
    return {"run_id": os.path.basename(jsonl)[len("agent-"):-len(".jsonl")][:8],
            "agent_type": agent_type, "finished": finished, "state": state,
            "age_s": age, "modified": iso(mtime), "last_tool": tool, "last_tool_ts": tool_ts,
            "meta_pending": finished is None, "tool_read": age < WINDOW_S}


def scan(repo_root, now=None, home=None):
    now = time.time() if now is None else now
    base = transcripts_dir(repo_root, home)
    out = {"source": "~/.claude/projects/<this workspace>", "available": os.path.isdir(base),
           "generated": iso(now), "sessions": [], "agents": {}, "window_h": WINDOW_S // 3600}
    if not out["available"] or os.path.islink(base):
        out["available"] = False
        return out
    all_runs = []
    for jsonl in sorted(glob.glob(os.path.join(base, "*.jsonl"))):
        mtime = _mtime(jsonl)
        if mtime is None or os.path.islink(jsonl):
            continue
        sid = os.path.basename(jsonl)[:-len(".jsonl")]
        subdir = os.path.join(base, sid, "subagents")
        paths = [] if os.path.islink(os.path.join(base, sid)) or os.path.islink(subdir) else \
            sorted(glob.glob(os.path.join(subdir, "agent-*.jsonl")))
        subs = [r for r in (_subagent(p, now) for p in paths if not os.path.islink(p)) if r]
        all_runs += subs
        newest = max([mtime] + [now - s["age_s"] for s in subs])
        if now - newest > WINDOW_S:
            continue
        age = max(0, int(now - mtime))
        tool, tool_ts = last_tool(jsonl) if age < WINDOW_S else (None, None)
        subs.sort(key=lambda s: s["age_s"])
        out["sessions"].append({"id8": sid[:8], "state": state_for(age), "age_s": age, "modified": iso(mtime),
                                "last_tool": tool, "last_tool_ts": tool_ts, "tool_read": age < WINDOW_S, "subagents": subs})
    out["sessions"].sort(key=lambda s: min([s["age_s"]] + [x["age_s"] for x in s["subagents"]]))
    # latest observed run per agent type, from all history; runs outside the window are labelled
    # (in_window false, tool not read) rather than hidden, so a desk shows when the agent last ran
    for run in sorted(all_runs, key=lambda s: s["age_s"]):
        if run["agent_type"] and run["agent_type"] not in out["agents"]:
            out["agents"][run["agent_type"]] = dict(run, in_window=run["age_s"] < WINDOW_S)
    return out


def project_file_activity(root, slug, now=None, limit=10):
    """Most recently modified files of a project (mtime only); LOCAL/ scratch is skipped."""
    now = time.time() if now is None else now
    base = os.path.join(root, "PROJECTS", slug)
    files, logs = [], {}
    for d, dirs, names in os.walk(base):
        dirs[:] = [x for x in dirs if x != "LOCAL" and not x.startswith(".")]
        for n in names:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, base)
            m = None if os.path.islink(p) else _mtime(p)
            if m is None:
                continue
            files.append((m, rel))
            parts = rel.split(os.sep)
            if len(parts) == 3 and parts[0] == "LOGS" and parts[2] == "log.md":
                logs[parts[1]] = {"modified": iso(m), "age_s": max(0, int(now - m))}
    files.sort(reverse=True)
    return {"recent_files": [{"path": rel, "modified": iso(m), "age_s": max(0, int(now - m))}
                             for m, rel in files[:limit]],
            "agent_logs": logs}
