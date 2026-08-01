#!/usr/bin/env python3
"""Lesson scheduler server. Run: python3 homeschool/app.py -> http://localhost:4750

Serves index.html and persists the whole schedule document as JSON.
ponytail: whole-document POST, no patching -- one family, tiny file, atomic rename.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "schedule.json")
PORT = 4750


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(ROOT, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/data":
            with open(DATA, "rb") as f:
                self._send(200, f.read(), "application/json")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        if self.path != "/data":
            return self._send(404, b"not found")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            doc = json.loads(body)
            assert isinstance(doc.get("weeks"), list) and len(doc["weeks"]) == 34
        except (ValueError, AssertionError):
            return self._send(400, b"bad document")
        tmp = DATA + ".tmp"
        with open(tmp, "w") as f:
            json.dump(doc, f, indent=1)
        os.replace(tmp, DATA)
        self._send(200, b"ok")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not os.path.exists(DATA):
        raise SystemExit("No data/schedule.json yet. Run: python3 homeschool/seed.py")
    print(f"Lesson scheduler running: http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
