#!/usr/bin/env python3
"""Serve the public/ directory without ever calling os.getcwd() (avoids a sandbox permission issue)."""

import functools
import http.server
import os
import socketserver
from pathlib import Path

DIRECTORY = str(Path(__file__).resolve().parent.parent / "public")
PORT = int(os.environ.get("PORT", 8743))


def main():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIRECTORY)
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"Serving {DIRECTORY} on port {PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
