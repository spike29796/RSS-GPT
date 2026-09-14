#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T-043 本地打分器 —— 用你的意图标注当 few-shot，给新条目打分。

用法：
    python score_local.py                     # 自动找最新的 intent-marks*.jsonl
    python score_local.py --marks <路径>       # 指定标注文件
    python score_local.py --limit 60          # 最多打多少条（默认 60）
    python score_local.py --min-score 2       # 进推荐区的最低分（默认 2）
    python score_local.py --dry               # 只打印，不写文件

流程：
    标注文件(你的浏览器导出) → few-shot 示例池
    docs/*.jsonl(抓取数据)   → 候选条目(排除已标注的)
    → GLM-4-Flash 打分 → docs/recommended.jsonl(推荐区数据源)

隐私：标注文件只在本机读取，不写进产物。产物只含「推荐结果」。
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from collections import defaultdict

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
OUT = os.path.join(DOCS, "recommended.jsonl")

# 源名 → 中文标签（跟 web/src/api.js 对齐；只影响显示）
# 已下线（不在此列）：ithome(T-040)、openai-news(T-044)、
#   simonwillison(T-047)、producthunt(T-047)、hf-blog(T-048)、arxiv-ai(T-048)
SRC_NAME = [
    "qbitai", "geekpark", "infoq", "nvidia-blog",
    "github-trending", "hackernews", "reddit-localllama", "lilianweng",
    "gradient", "lobsters", "arxiv-ro", "sspai",
]

LABEL = {"use": "能马上用", "save": "该存档", "know": "只需知道", "noise": "与我无关"}

# 【只抓不推】的源 —— 照常抓取、在「全部」区可见、数据留在仓库，但不进推荐区。
# 大卫原话：「那就放着不管，压仓库里，什么时候想看就拿出来」（2026-09-14）
# 理由：arXiv cs.RO 每天发 90+ 篇论文，与其他源（每天 1-5 条）差两个数量级，
#       不管怎么打分都会压倒推荐区（实测 79 条推荐里它占 63）。它不是"没用"，
#       是"量太大会淹掉别的"——所以保留但不推。
NO_RECOMMEND = {"arxiv-ro"}

# 智谱 GLM 的 OpenAI 兼容端点（免费档够用）
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4-flash"

# 明确的排除信号（大卫的标注里高频出现）—— 写进提示词，压掉误报
EXCLUDE_HINT = (
    "以下类型直接 0 分：会议/大会/榜单/征集/报名/展台报道/颁奖；"
    "手机·汽车·家电·可穿戴·耳机等消费电子新品发布或配色/售价/预售；"
    "股价/融资/财报/人事变动；纯转发式早报或资讯合集。"
)


def get_key():
    """GLM key：优先环境变量，其次 lucy 的 .env。"""
    k = os.environ.get("GLM_API_KEY")
    if k:
        return k.strip()
    for p in (r"D:\Hermes Agent CN Desktop\data\hermes-home\profiles\lucy\.env",
              os.path.join(HERE, ".env")):
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8-sig", errors="ignore"):
            if line.strip().startswith("GLM_API_KEY="):
                return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("找不到 GLM_API_KEY（环境变量或 .env 都没有）")


def clean(s):
    t = re.sub(r"<[^>]*>", " ", str(s or ""))
    for _ in range(5):
        n = re.sub(r"^\s*(总结|摘要)\s*[：:]\s*", "", t)
        if n == t:
            break
        t = n
    return re.sub(r"\s+", " ", t).strip()


def digest(e, limit=400):
    """给打分器看的「内容」：优先 summary；为空则退回 content 开头。

    ⚠️ 实测（T-048）：arxiv-ro 的 93 条 summary 全空 —— LLM 生成中文摘要那步
    没跑到（backfill_max_minutes=25 的时间预算被前面的源吃掉了），代码在摘要
    失败时写 None，没有退回原始内容。但 content 字段里存着完整的 arXiv Abstract。
    只拿标题去打分 → 模型看英文论文标题"都很技术" → 93 条论文全给 2 分，
    把推荐区淹了（111 条里 93 条是它）。
    """
    s = clean(e.get("summary"))
    if s:
        return s[:limit]
    c = clean(e.get("content"))
    # 去掉 arxiv 的 "arXiv:xxxx Announce Type: new Abstract:" 前缀噪音
    c = re.sub(r"^\s*arXiv:[\d.]+v\d+\s*Announce Type:\s*\w+\s*", "", c)
    c = re.sub(r"^\s*Abstract:\s*", "", c)
    return c[:limit]


def source_priors(marks, min_n=8, noise_rate=0.10):
    """从标注里学「源级先验」—— 某个源历史样本够多且几乎没有正例 → 整体跳过。

    为什么需要：模型能学会"什么样的内容是能动手的"（有代码/方法/工具），
    但学不会"这个源对我是噪音"。实测（T-047）：simonwillison 被大卫标了
    7/7「与我无关」，但打分器照样给它那些版本更新帖打 2 分 ——
    因为那些帖子确实"有可操作内容"，只是他不关心这个源。

    判据（保守）：
      · 该源被标过的条数 >= min_n（样本够）
      · 正例（能马上用 + 该存档）占比 < noise_rate
    → 该源整体不参与打分（并在输出里说明，方便大卫复核）
    """
    by = defaultdict(lambda: [0, 0])  # src -> [总数, 正例]
    for m in marks:
        s = m.get("source") or "?"
        by[s][0] += 1
        if m.get("intent") in ("use", "save"):
            by[s][1] += 1
    dropped = {}
    for s, (n, pos) in by.items():
        if n >= min_n and (pos / n) < noise_rate:
            dropped[s] = (n, pos)
    return dropped


def parse_ts(s):
    """把 RFC 2822 / ISO 8601 都解析成时间戳；解析不了返回 0。

    ⚠️ 不能用字符串排序：RFC 2822（"Wed, 31 May 2023…"）以字母开头，
    ISO（"2026-09-14T…"）以数字开头 —— 字符串比较会把字母排前面，
    导致 2023 年的老条目排在 2026 年新条目之前。实测踩过（T-043）。
    """
    s = str(s or "").strip()
    if not s:
        return 0.0
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        pass
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def find_marks(explicit=None):
    if explicit:
        return explicit
    cands = []
    for d in (os.path.join(os.path.expanduser("~"), "Downloads"),
              os.path.join(os.path.expanduser("~"), "Desktop"),
              os.path.join(os.path.expanduser("~"), "下载")):
        cands += glob.glob(os.path.join(d, "intent-marks*.jsonl"))
    if not cands:
        sys.exit("找不到 intent-marks*.jsonl —— 请先在站点上点「导出标注」")
    return max(cands, key=os.path.getmtime)


def load_marks(path):
    rows = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def load_entries():
    out = []
    for s in SRC_NAME:
        p = os.path.join(DOCS, "%s.jsonl" % s)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            r["_src"] = s
            out.append(r)
    return out


def build_examples(marks):
    by = defaultdict(list)
    for m in marks:
        by[m.get("intent")].append(m)
    # 正例全用；负例抽样（避免把提示词撑爆）
    ex = list(by["use"]) + list(by["save"]) + by["know"][:6] + by["noise"][:12]
    return ex


# 判据的核心：区分【可操作内容】和【新闻报道】
# 大卫的标注里"该存档"全是可操作的东西（框架/方法/工具），
# 而新闻报道（谁发布了什么、谁警告了什么）只能到 1 分。
# ⚠️ 实测（T-043）：判据写成"有没有用" → 模型全给 2 分（30 条里 17 条），
#    因为它根本没法区分。改写成"有没有可动手的东西"才分得开。
CRITERIA = """打分判据（严格按此，不要给中间分）：

问自己一个问题：这条内容里有没有【我真的能动手用的东西】？
（代码、方法、步骤、工具名、架构设计、实测数据、可复现的经验）

  3 = 有可操作内容，且我立刻就想动手试（今天/明天就会做）
  2 = 有可操作内容（能找到用法/思路/工具），但我不是马上用，先存着
  1 = 没有可操作内容，纯报道：谁发布了什么、谁警告了什么、谁融资了、
      行业趋势感慨、大会现场观察 —— 知道就行了
  0 = 跟我方向无关，或下面这些直接排除的类型

直接 0 分的类型：
  · 会议/大会/榜单/征集/报名/展台报道/颁奖/开发者日
  · 手机·汽车·家电·可穿戴·耳机等消费电子新品发布/配色/售价/预售
  · 股价/融资/财报/人事变动/裁员
  · 转发式早报、资讯合集、多条拼盘

【即使看着"可操作"，也降为 1 分或 0 分】（实测：这些占了误报的大头）
  · 单纯的版本号更新 / 例行 release note（如 "llm 0.35"、"datasette 1.0a39"、
    "xxx 2.9.1"）—— 能装不等于我要装
  · 纯引用/摘录帖（标题像 "Quoting XXX"）而没有作者自己的分析
  · 单个工具的补丁级小更新（第三位版本号变动）
"""


def score_batch(key, examples, batch):
    L = ["这是我的历史标注，请从中理解我的偏好。",
         "注意：我把「该存档」的都是【有可动手内容】的东西，",
         "而绝大多数新闻报道我都标了「与我无关」。", ""]
    pos = [m for m in examples if m.get("intent") in ("use", "save")]
    neg = [m for m in examples if m.get("intent") not in ("use", "save")]
    if pos:
        L.append("▼ 我标「能马上用 / 该存档」的（这些才是我要的，仔细看特征）：")
        for m in pos:
            t = m.get("title_zh") or m.get("title") or ""
            L.append("- [%s] %s → %s" % (m.get("source", "?"), t[:70],
                                        LABEL.get(m.get("intent"))))
        L.append("")
    if neg:
        L.append("▼ 我标「只需知道 / 与我无关」的（这类别给我高分）：")
        for m in neg:
            t = m.get("title_zh") or m.get("title") or ""
            L.append("- [%s] %s → %s" % (m.get("source", "?"), t[:70],
                                        LABEL.get(m.get("intent"))))
        L.append("")
    L += [CRITERIA, "",
          "现在给下面 %d 条新条目各打一个分（0/1/2/3）：" % len(batch), ""]
    for i, e in enumerate(batch, 1):
        title = e.get("title") or ""
        summ = digest(e)
        L.append("%d. [%s] %s%s" % (i, e["_src"], title[:80],
                  ("　｜ " + summ[:200]) if summ else ""))
    L += ["", '只输出 JSON 数组，不要解释：[{"i":1,"score":2,"why":"15字内理由"}]']
    prompt = "\n".join(L)

    # 用 requests 而不是 urllib：semgrep 的 dynamic-urllib-use-detected 规则会把
    # urlopen(Request(...)) 判为 blocking（urllib 支持 file:// 协议）。虽然这里的
    # URL 是写死的常量，但规则不认，且 requests 本来就是仓库依赖。
    resp = requests.post(
        API_URL,
        headers={"Authorization": "Bearer %s" % key,
                 "Content-Type": "application/json"},
        data=json.dumps({"model": MODEL,
                         "messages": [{"role": "user", "content": prompt}],
                         "temperature": 0.2}).encode("utf-8"),
        timeout=180,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marks")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--min-score", type=int, default=2)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--days", type=int, default=14, help="只看最近 N 天的条目（0=不限）")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    mp = find_marks(a.marks)
    marks = load_marks(mp)
    print("标注文件: %s（%d 条）" % (mp, len(marks)))

    by = defaultdict(int)
    for m in marks:
        by[m.get("intent")] += 1
    print("  分布: " + " ｜ ".join("%s %d" % (LABEL.get(k, k), v)
                                 for k, v in sorted(by.items(), key=lambda x: -x[1])))

    examples = build_examples(marks)
    print("示例池: %d 条" % len(examples))
    if by.get("use", 0) + by.get("save", 0) < 5:
        print("  ⚠️ 正例偏少（能马上用+该存档 < 5），打分可能偏保守 —— 继续标效果会更好")

    all_entries = load_entries()
    marked_links = set(m["link"] for m in marks if m.get("link"))
    cand = [e for e in all_entries if e.get("link") not in marked_links]

    # 源级先验：样本够多且几乎没正例的源，整体跳过（见 source_priors 的说明）
    dropped = source_priors(marks)
    if dropped:
        print("\n=== 源级先验（从你的标注学出来）===")
        for s, (n, pos) in sorted(dropped.items(), key=lambda x: -x[1][0]):
            print("  跳过 %-18s 你标过 %d 条，正例 %d 条 → 整体不推" % (s, n, pos))
        before = len(cand)
        cand = [e for e in cand if e["_src"] not in dropped]
        print("  → 滤掉 %d 条" % (before - len(cand)))

    # 只抓不推的源（数据留着，但不进推荐区）
    if NO_RECOMMEND:
        before = len(cand)
        cand = [e for e in cand if e["_src"] not in NO_RECOMMEND]
        print("\n=== 只抓不推 ===\n  %s（数据仍在仓库，可在「全部」区看）→ 滤掉 %d 条"
              % (", ".join(sorted(NO_RECOMMEND)), before - len(cand)))

    for e in cand:
        e["_ts"] = parse_ts(e.get("published"))
    if a.days:
        cutoff = time.time() - a.days * 86400
        before = len(cand)
        cand = [e for e in cand if e["_ts"] >= cutoff]
        print("时间过滤: 最近 %d 天 → %d 条（滤掉 %d 条老数据）" % (a.days, len(cand), before - len(cand)))
    cand.sort(key=lambda e: e["_ts"], reverse=True)
    cand = cand[:a.limit]
    print("候选: %d 条（已排除你标过的 %d 条）" % (len(cand), len(marked_links)))
    if not cand:
        sys.exit("没有候选条目")

    key = get_key()
    results = []
    for i in range(0, len(cand), a.batch):
        chunk = cand[i:i + a.batch]
        print("  打分 %d-%d …" % (i + 1, i + len(chunk)), flush=True)
        for s in score_batch(key, examples, chunk):
            try:
                idx = int(s.get("i", 0))
            except Exception:
                continue
            if 1 <= idx <= len(chunk):
                e = chunk[idx - 1]
                results.append({
                    "link": e.get("link"), "title": e.get("title") or "",
                    "title_zh": e.get("title_zh") or "", "source": e["_src"],
                    "category": e.get("category") or "",
                    "published": e.get("published") or "",
                    "summary": digest(e, 300),
                    "score": s.get("score", 0), "why": str(s.get("why") or "")[:60],
                })

    results.sort(key=lambda r: -(r["score"] if isinstance(r["score"], (int, float)) else 0))
    print("\n=== 打分分布 ===")
    for sc in (3, 2, 1, 0):
        n = len([r for r in results if r["score"] == sc])
        print("  %d 分: %d 条" % (sc, n))

    rec = [r for r in results if isinstance(r["score"], (int, float)) and r["score"] >= a.min_score]
    print("\n=== 进推荐区（≥%d 分）：%d 条 ===" % (a.min_score, len(rec)))
    for r in rec:
        print("  [%s] [%s] %s" % (r["score"], r["source"], r["title"][:58]))
        if r["why"]:
            print("        %s" % r["why"])

    if a.dry:
        print("\n（--dry：没写文件）")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rec:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\n已写 %s（%d 条）" % (OUT, len(rec)))


if __name__ == "__main__":
    main()
