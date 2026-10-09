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
import time

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

    # 2026-09-30：用当前解释器（sys.executable）而不是裸 `python` ——
    # 有些 Windows 机器上 PATH 里的 `python` 是 Microsoft Store 的占位符
    # （跑起来只弹商店、`--version` 返回空），管线会整条挂掉。
    py = f'"{sys.executable}"'
    run(f"{py} main.py")
    run(f"{py} bilibili_collect.py")
    # 2026-10-10：接上论文双语阅读页的译文预生成。不加 --force，
    # 已翻的条目整条跳过 → 天然增量（不留存量回填）。--limit 卡单轮时长，
    # 07:00 翻译服务停之前跑多少算多少；跑不完下次续，段级缓存不白跑。
    run(f"{py} paper_translate.py --limit 20")

    run("git add docs/", check=False)
    msg = datetime.datetime.now().strftime("Auto Build at %Y-%m-%d %H:%M")
    rc = run(f'git commit -m "{msg}"', check=False)
    if rc != 0:
        print("（无变更可提交，跳过）")

    if "--push" in sys.argv:
        # 2026-10-03 修：原来这一句是 `run("git push origin main", check=False)` ——
        # 推送失败被静默吞掉，任务照样 exit 0，commit 只留在本地、站点不更新
        # （10-03 就发生了：本地 afe8d14 领先远端 1 个，Pages 没动）。
        # 现在：自动重试 3 次（网络抽风可自愈），最终失败以非 0 退出，
        # 让计划任务的 LastTaskResult 留下失败痕迹。
        pushed = False
        for attempt in range(1, 4):
            rc = run("git push origin main", check=False)
            if rc == 0:
                print(f"[push] 成功（第 {attempt} 次）")
                pushed = True
                break
            print(f"[push] 失败 exit={rc}（第 {attempt}/3 次）")
            if attempt < 3:
                time.sleep(30)
        if not pushed:
            sys.exit(
                "[push] 连续 3 次失败：检查网络/代理。"
                "本地 commit 已保留，可手动 `git push origin main` 补推。"
            )
    else:
        print("\ndocs/ 已提交（未推送）。确认后手动 `git push origin main`，或加 --push 自动推。")


if __name__ == "__main__":
    main()
