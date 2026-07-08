#!/usr/bin/env python3
"""Shim: serve this site with Range support. Canonical server lives in
scripts/serve_range.py. Usage: python3 serve.py [port]"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
port = sys.argv[1] if len(sys.argv) > 1 else "8090"
sys.exit(subprocess.call([sys.executable,
                          os.path.join(here, "..", "scripts", "serve_range.py"),
                          here, port]))
