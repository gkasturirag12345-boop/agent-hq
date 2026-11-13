#!/usr/bin/env python3
"""Agent HQ: a read-only, local dashboard for a multi-agent Claude Code workspace.

usage: python3 -B -m agent_hq.server [--root WORKSPACE] [--port 8780]
Binds to 127.0.0.1 only. GET only. Reads the repository's Markdown on every
request; writes nothing, starts no processes, makes no network calls.
"""
import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live  # noqa: E402
import parse  # noqa: E402

ROOT = os.getcwd()                      # replaced by --root in main()
HOST = "127.0.0.1"
STATIC = {  # fixed whitelist: no URL path ever reaches the filesystem
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/scene.js": ("scene.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "agent-dashboard"
    timeout = 15                       # seconds per connection; idle or slow clients are dropped
    sys_version = ""

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "forbidden host\n")
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        try:
            if path in STATIC:
                name, ctype = STATIC[path]
                return self._send(200, parse.read(os.path.join(HERE, "static", name)), ctype)
            m = re.fullmatch(r"/p/([a-z0-9][a-z0-9-]*)", path)
            if m and m.group(1) in parse.project_slugs(ROOT):
                name, ctype = STATIC["/"]
                return self._send(200, parse.read(os.path.join(HERE, "static", name)), ctype)
            if path == "/api/live":
                return self._json(live.scan(ROOT))
            if path == "/api/overview":
                return self._json(parse.overview(ROOT))
            m = re.fullmatch(r"/api/project/([a-z0-9][a-z0-9-]*)", path)
            if m and m.group(1) in parse.project_slugs(ROOT):
                ov = parse.overview(ROOT)
                proj = next(p for p in ov["projects"] if p["slug"] == m.group(1))
                return self._json({"project": proj, "agents": ov["agents"], "statuses": ov["statuses"],
                                   "file_activity": live.project_file_activity(ROOT, m.group(1))})
        except Exception as exc:  # report, never guess
            return self._send(500, f"error reading workspace records: {type(exc).__name__}\n")
        return self._send(404, "not found\n")

    do_HEAD = do_GET

    def _json(self, obj):
        return self._send(200, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _reject(self):
        self._send(405, "read-only dashboard: only GET is allowed\n")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_TRACE = do_CONNECT = _reject

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="workspace folder (contains PROJECTS/); default: current folder")
    ap.add_argument("--port", type=int, default=8780)
    args = ap.parse_args()
    global ROOT
    ROOT = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(ROOT, "PROJECTS")):
        sys.exit(f"{ROOT} has no PROJECTS/ folder; pass --root <workspace>")
    try:
        srv = ThreadingHTTPServer((HOST, args.port), Handler)
    except OSError as exc:
        sys.exit(f"Port {args.port} on {HOST} is not available ({exc.strerror}). "
                 f"Is the dashboard already running? Use another port, e.g. --port {args.port + 1}")
    print(f"Agent HQ (read-only): http://{HOST}:{args.port}/   workspace: {ROOT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
