#!/usr/bin/env python3
"""本地跑 RSS-GPT 管线（本地 LLM 用）。

用法（在 RSS-GPT/ 目录）：
    python run_local.py            # 跑管线 + 提交 docs/，不推送
    python run_local.py --push     # 跑管线 + 提交 + 推送 origin main

前置：
    1. cp .env.example .env（Windows: copy .env.example .env），填 OPENAI_BASE_URL /
       CUSTOM_MODEL / OPENAI_API_KEY / U_NAME
    2. pip install -r requirements.txt
    3. 本地 LLM 已在跑（Ollama `ollama serve` 或 LM Studio）
"""
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env")


def load_env():
    if not os.path.exists(ENV_FILE):
        sys.exit(
            "缺少 .env：请先复制 .env.example 为 .env 并填写 "
            "（OPENAI_BASE_URL / CUSTOM_MODEL / OPENAI_API_KEY / U_NAME）。"
        )
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                os.environ.setdefault(k, v)


def run(cmd, check=False):
    print(f">>> {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, cwd=HERE)
    if check and r.returncode != 0:
        sys.exit(f"步骤失败：{cmd}（exit={r.returncode}）")
    return r.returncode


def main():
    load_env()
    missing = [k for k in ("OPENAI_BASE_URL", "CUSTOM_MODEL", "U_NAME") if not os.environ.get(k)]
    if missing:
        sys.exit(f".env 缺必填项：{', '.join(missing)}（OPENAI_API_KEY 本地可留空）")

    run("python main.py")
    run("python bilibili_collect.py")

    run("git add docs/", check=False)
    msg = datetime.datetime.now().strftime("Auto Build at %Y-%m-%d %H:%M")
    rc = run(f'git commit -m "{msg}"', check=False)
    if rc != 0:
        print("（无变更可提交，跳过）")

    if "--push" in sys.argv:
        run("git push origin main", check=False)
    else:
        print("\ndocs/ 已提交（未推送）。确认后手动 `git push origin main`，或加 --push 自动推。")


if __name__ == "__main__":
    main()
