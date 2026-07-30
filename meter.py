"""meter.py — 全厂 LLM 调用唯一入口。一次调用写一行 logs/llm.jsonl。

    import meter
    resp = meter.chat(ticket="T-003", task="summary",
                      messages=[{"role": "user", "content": "..."}])

环境变量与 RSS-GPT 生产一致：OPENAI_API_KEY（必填）/ OPENAI_BASE_URL / CUSTOM_MODEL。
调用方自己做重试循环，每次调用传 retry=第几次（从 0 计），一次尝试一行账。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).parent / "logs" / "llm.jsonl"

# 元 / 百万 tokens，按生产实际渠道价填；查不到的模型 cost_yuan 记 None，不许编数
PRICES: dict[str, tuple[float, float]] = {
    # "model-name": (input_price, output_price),
}


def chat(ticket: str, task: str, messages: list, model: str | None = None,
         retry: int = 0, timeout: int = 300, **kwargs):
    """发一次 chat completion 并记账。失败也记账（status="error"）后原样抛出。"""
    model = model or os.environ.get("CUSTOM_MODEL", "gpt-4o-mini")
    started = time.time()
    try:
        completion = _client().chat.completions.create(
            model=model, messages=messages, timeout=timeout, **kwargs)
    except Exception:
        _log(ticket, task, model, 0, 0, 0, started, 0, retry, "error")
        raise
    usage = completion.usage
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(details, "reasoning_tokens", None) or 0
    _log(ticket, task, model, prompt_tokens, completion_tokens, reasoning_tokens,
         started, _cost_yuan(model, prompt_tokens, completion_tokens), retry, "ok")
    return completion


def _client():
    from openai import OpenAI
    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


def _cost_yuan(model: str, prompt_tokens: int, completion_tokens: int):
    price = PRICES.get(model)
    if price is None:
        return None
    in_price, out_price = price
    return round((prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000, 6)


def _log(ticket, task, model, prompt_tokens, completion_tokens,
         reasoning_tokens, started, cost_yuan, retry, status):
    record = {
        "ticket": ticket, "task": task, "model": model,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "latency_s": round(time.time() - started, 1),
        "cost_yuan": cost_yuan, "retry": retry, "status": status,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
