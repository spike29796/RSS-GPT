"""Mock feed server for e2e snapshot mode (T-017): serves frozen feed bodies.

Routes (all GET):
  /s/<name>  -> 200 with test/feed_snapshots/<name>.body using the Content-Type
                recorded in <name>.json at capture time. When the source has no
                snapshot (e.g. region-blocked at capture time), responds 500 —
                deterministically "unreachable", mirroring the capture network.
  anything else -> 500 (e.g. collector sub-page fetches: deterministic empty
                body upstream, no flakiness).

Snapshots are read from THIS file's directory, so the server runs against the
real test/feed_snapshots while e2e exercises a temp copy of the repo.

Usage: python test/mock_feeds.py   (listens on 127.0.0.1:18124)
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SNAPSHOTS = Path(__file__).parent.resolve() / "feed_snapshots"
PORT = 18124


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name = None
        if self.path.startswith("/s/"):
            name = self.path[3:].strip("/")
        # Path traversal guard: only plain names resolve inside SNAPSHOTS.
        if name and "/" not in name and ".." not in name:
            body_path = SNAPSHOTS / f"{name}.body"
            meta_path = SNAPSHOTS / f"{name}.json"
            if body_path.is_file():
                content_type = "application/octet-stream"
                if meta_path.is_file():
                    try:
                        content_type = json.loads(meta_path.read_text(encoding="utf-8")).get("content_type") or content_type
                    except ValueError:
                        pass
                body = body_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        body = b"mock_feeds: no snapshot for this source/path"
        self.send_response(500)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
