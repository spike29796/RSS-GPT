"""Simulate GitHub Pages locally: serve RSS-GPT/docs under the /RSS-GPT/ prefix.

The app is built with base=/RSS-GPT/ and fetches <base><name>.jsonl, so a plain
`python -m http.server` inside docs/ 404s every asset. This handler strips the
prefix instead. Do NOT use `vite preview` for this check — it applies the dev
proxy and 500s (see PROGRESS.md).

Usage: python test/serve_pages.py [port]   then open http://127.0.0.1:8321/RSS-GPT/
"""
import http.server
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "RSS-GPT" / "docs"
PREFIX = "/RSS-GPT"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def do_GET(self):
        if self.path.startswith(PREFIX):
            self.path = self.path[len(PREFIX):] or "/"
        super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8321
    print(f"serving {DOCS} at http://127.0.0.1:{port}{PREFIX}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
