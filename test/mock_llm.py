"""Mock OpenAI-compatible server for local end-to-end testing of RSS-GPT.

Responds to POST /v1/chat/completions with a canned chat completion. The
category is parsed from the request's system instruction (so sources with
their own category set, e.g. awwwards-sotd, get a valid value). To exercise
the retry path in gpt_summary, every 6th request returns an invalid category
and every 7th a prefixed one; the next attempt then lands on a valid value.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

DEFAULT_CATS = ["模型发布", "行业动态", "政策法规", "开源项目", "产品应用"]
counter = {"n": 0}


def pick_category(body: bytes) -> tuple[str, str]:
    """Return (category, style) for this request: style is 'normal',
    'invalid' (6th request) or 'prefixed' (7th)."""
    counter["n"] += 1
    cats = DEFAULT_CATS
    try:
        payload = json.loads(body)
        system = next(m["content"] for m in payload["messages"] if m["role"] == "system")
        m = re.search(r"选择一个：([^，]+)", system) or re.search(r"chosen from: ([^,;]+)", system)
        if m:
            cats = [c.strip() for c in re.split(r"[、,]", m.group(1)) if c.strip()]
    except Exception:
        pass
    n = counter["n"]
    if n % 7 == 6:
        return "科技新闻", "invalid"
    if n % 7 == 0:
        return f"分类：{cats[n % len(cats)]}", "prefixed"
    return cats[n % len(cats)], "normal"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        category, _ = pick_category(body)
        content = f"{category}\n<br><br>总结:这是一句话导读，覆盖文章核心看点。"
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
