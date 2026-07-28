"""Mock OpenAI-compatible server for local end-to-end testing of RSS-GPT.

Responds to POST /v1/chat/completions with a canned chat completion whose
first line cycles through the 5 valid categories plus one invalid value, to
exercise both the happy path and the fallback in parse_category_and_summary.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

RESPONSES = [
    "模型发布\n<br><br>总结:这是一篇关于新模型发布的文章，介绍了模型能力和应用场景。",
    "行业动态\n<br><br>总结:这是一篇行业动态文章，报道了公司融资与市场变化。",
    "政策法规\n<br><br>总结:这是一篇政策法规文章，解读了最新监管要求。",
    "开源项目\n<br><br>总结:这是一篇开源项目文章，介绍了项目功能与社区进展。",
    "产品应用\n<br><br>总结:这是一篇产品应用文章，展示了产品落地案例。",
    "科技新闻\n<br><br>总结:这是一个非法分类，应被兜底为行业动态。",  # invalid category on purpose
    "分类：模型发布\n<br><br>总结:这是一个带前缀的合法分类，应被正确剥离前缀。",  # prefix variant
]
counter = {"n": 0}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)  # drain request body
        content = RESPONSES[counter["n"] % len(RESPONSES)]
        counter["n"] += 1
        body = json.dumps({
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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 18123), Handler).serve_forever()
