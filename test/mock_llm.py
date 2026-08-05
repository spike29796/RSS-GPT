"""Mock OpenAI-compatible server for local end-to-end testing of RSS-GPT.

Responds to POST /v1/chat/completions with a canned chat completion. The
category is parsed from the request's system instruction (so sources with
their own category set, e.g. awwwards-sotd, get a valid value).

Response style is a deterministic function of the request BODY (T-017): the
pipeline's backfill pool issues 3 concurrent requests, so a global request
counter made per-entry categories depend on thread arrival order and broke
byte-identical e2e reruns. Now the first attempt for a given body hashes the
body: hash%7==6 -> invalid category, hash%7==0 -> prefixed category (both
exercise the gpt_summary retry path); any retry (2nd+ attempt for the same
body) always lands on a valid value.
"""
import hashlib
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

DEFAULT_CATS = ["模型发布", "行业动态", "政策法规", "开源项目", "产品应用"]
attempts = {}  # body -> attempt count (retries must land on a valid response)


def pick_category(body: bytes) -> tuple[str, str]:
    """Return (category, style) for this request: style is 'normal',
    'invalid' or 'prefixed'. Deterministic per request body."""
    cats = DEFAULT_CATS
    try:
        payload = json.loads(body)
        system = next(m["content"] for m in payload["messages"] if m["role"] == "system")
        m = re.search(r"选择一个：([^，]+)", system) or re.search(r"chosen from: ([^,;]+)", system)
        if m:
            cats = [c.strip() for c in re.split(r"[、,]", m.group(1)) if c.strip()]
    except Exception:
        pass
    n = attempts.get(body, 0) + 1
    attempts[body] = n
    h = int.from_bytes(hashlib.sha256(body).digest()[:8], "big")
    if n >= 2:
        # A retry after an invalid/prefixed first attempt must succeed.
        return cats[h % len(cats)], "normal"
    if h % 7 == 6:
        return "科技新闻", "invalid"
    if h % 7 == 0:
        return f"分类：{cats[h % len(cats)]}", "prefixed"
    return cats[h % len(cats)], "normal"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        category, _ = pick_category(body)
        content = f"{category}\n<br><br>总结:这是一句话导读，覆盖文章核心看点。\n模拟中文标题"
        resp = json.dumps({
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 18123), Handler).serve_forever()
