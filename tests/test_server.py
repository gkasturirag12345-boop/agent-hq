"""Dashboard server tests: in-process server on a free port. Standard library only."""
import http.client
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent_hq"))
import server  # noqa: E402


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples", "demo-workspace"))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def req(self, method, path, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(method, path, skip_host=True)
        c.putheader("Host", host or f"127.0.0.1:{self.port}")
        c.endheaders()
        r = c.getresponse(); body = r.read(); c.close()
        return r.status, dict(r.getheaders()), body

    def test_bind_address_is_loopback_constant(self):
        self.assertEqual(server.HOST, "127.0.0.1")

    def test_pages_and_api(self):
        slug = server.parse.project_slugs(server.ROOT)[0]
        for path in ("/", "/app.js", "/scene.js", "/style.css", "/api/overview", "/api/live", f"/api/project/{slug}", f"/p/{slug}"):
            self.assertEqual(self.req("GET", path)[0], 200, path)

    def test_not_found(self):
        for path in ("/index.html", "/static/app.js", "/../.claude/settings.json", "/%2e%2e/parse.py", "/p/nope", "/api/project/nope", "/server.py"):
            self.assertEqual(self.req("GET", path)[0], 404, path)

    def test_methods_rejected(self):
        for m in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CONNECT"):
            self.assertEqual(self.req(m, "/api/overview")[0], 405, m)

    def test_host_check(self):
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1", f"localhost.evil:{self.port}"):
            self.assertEqual(self.req("GET", "/api/overview", host)[0], 403, host)
        self.assertEqual(self.req("GET", "/", f"localhost:{self.port}")[0], 200)

    def test_head_has_no_body_and_security_headers(self):
        status, headers, body = self.req("HEAD", "/")
        self.assertEqual((status, body), (200, b""))
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertNotIn("Access-Control-Allow-Origin", headers)


if __name__ == "__main__":
    unittest.main()
