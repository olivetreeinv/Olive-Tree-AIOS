#!/usr/bin/env python3
"""Static file server with HTTP Range support. python -m http.server has none,
and Chrome cannot seek/scrub <video> without it (plays fine, currentTime stuck
at 0 on any seek). Usage: python3 scripts/serve_range.py <dir> [port=8090]"""
import os
import re
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if not m:
            return super().send_head()  # malformed Range: serve whole file, not a 500
        start = int(m.group(1) or 0)
        end = min(int(m.group(2) or size - 1), size - 1)
        if start > end:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range_len = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        n = getattr(self, "_range_len", None)
        if n is None:
            return super().copyfile(source, outputfile)
        self._range_len = None
        while n > 0:
            buf = source.read(min(65536, n))
            if not buf:
                break
            outputfile.write(buf)
            n -= len(buf)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    directory = os.path.abspath(sys.argv[1])
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8090
    handler = partial(RangeHandler, directory=directory)
    print(f"serving {directory} on http://localhost:{port}")
    ThreadingHTTPServer(("localhost", port), handler).serve_forever()  # localhost only — no LAN exposure
