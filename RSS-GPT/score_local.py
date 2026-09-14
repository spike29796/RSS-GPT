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


def evaluate_previous(prev_path, marks):
    """机制自检：拿「上一轮推荐过的条目」对照「他后来实际标的」，算命中率。

    为什么需要（T-050）：打分器推完就完了 —— 推得准不准没有任何数字，
    "这机制有效"就只是一面之词。这是评分机制能不能被信任的核心：
    没有反馈的评分器等于没有评分器。

    做法：跑新的一轮前，读上一轮的 recommended.jsonl，
    对每条去标注里查它后来被标成什么 → 命中 / 误报 / 未标注。
    """
    if not os.path.exists(prev_path):
        return None
    prev = []
    for line in open(prev_path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if line:
            try:
                prev.append(json.loads(line))
            except Exception:
                pass
    if not prev:
        return None

    by_link = {m.get("link"): m for m in marks if m.get("link")}
    hit = miss = unlabeled = 0
    misses = []
    for r in prev:
        m = by_link.get(r.get("link"))
        if not m:
            unlabeled += 1
            continue
        if m.get("intent") in ("use", "save"):
            hit += 1
        else:
            miss += 1
            misses.append((m.get("intent"), (r.get("title") or "")[:52]))
    labeled = hit + miss
    return {"total": len(prev), "labeled": labeled, "hit": hit,
            "miss": miss, "unlabeled": unlabeled, "misses": misses[:10]}


def run_selftest(key, marks, batch=20):
    """留出验证：把大卫自己的正例/负例藏起来当考卷，看打分器能不能认出来。

    这是判断打分机制好坏的硬指标 —— 不看内容、只看分数分离度：
      · 正例（他标了能马上用/该存档）得分应该高
      · 负例（他标了与我无关）得分应该低
    如果它给自己的正例都打不出高分，那机制就是坏的，不是内容的错。

    ⚠️ 关键：考卷里的条目必须从示例池里剔除，否则是泄题（模型照抄例子拿满分）。
    """
    pos = [m for m in marks if m.get("intent") in ("use", "save") and (m.get("title") or "")]
    neg = [m for m in marks if m.get("intent") == "noise" and (m.get("title") or "")]
    if not pos:
        print("没有正例可测（先标几条能马上用/该存档）")
        return

    # 留出：正例留最多 5 条、负例留 8 条当考卷。
    # ⚠️ 别抽太多正例 —— 本来就只有 12 条，抽 8 条后示例池只剩 4 条正例，
    # 模型学不到偏好，测出来的是"示例不足"而不是"判据好不好"。
    import random
    random.seed(42)
    test_pos = pos[:5]
    test_neg = random.sample(neg, min(8, len(neg)))
    test_links = set(m.get("link") for m in test_pos + test_neg)

    # 示例池 = 标注里去掉考卷条目
    pool = [m for m in marks if m.get("link") not in test_links]
    examples = build_examples(pool)

    print("\n" + "=" * 60)
    print("机制自测（留出验证）")
    print("=" * 60)
    print("  示例池: %d 条 ｜ 考卷: 正例 %d 条 + 负例 %d 条"
          % (len(examples), len(test_pos), len(test_neg)))

    def as_entry(m):
        return {"title": m.get("title") or "", "summary": m.get("summary") or "",
                "content": m.get("content") or "", "_src": m.get("source") or "?"}

    results = {"pos": [], "neg": []}
    for label, items in (("正例", test_pos), ("负例", test_neg)):
        for i in range(0, len(items), batch):
            chunk = [as_entry(m) for m in items[i:i + batch]]
            for s in score_batch(key, examples, chunk):
                try:
                    idx = int(s.get("i", 0))
                except Exception:
                    continue
                if 1 <= idx <= len(chunk):
                    results["pos" if label == "正例" else "neg"].append(
                        (s.get("score", 0), chunk[idx - 1]["title"][:52]))

    def stat(rs):
        if not rs:
            return "（无数据）"
        avg = sum(r[0] for r in rs) / len(rs)
        return "平均 %.2f 分 ｜ %s" % (avg, " ".join(str(r[0]) for r in rs))

    print("\n  正例（他标了「要的」）得分：%s" % stat(results["pos"]))
    print("  负例（他标了「与我无关」）得分：%s" % stat(results["neg"]))

    if results["pos"] and results["neg"]:
        ap = sum(r[0] for r in results["pos"]) / len(results["pos"])
        an = sum(r[0] for r in results["neg"]) / len(results["neg"])
        gap = ap - an
        print("\n  分离度（正例均分 - 负例均分）: %.2f" % gap)
        # 判定：≥2 分才算能进推荐区
        pos_ok = len([r for r in results["pos"] if r[0] >= 2]) / len(results["pos"]) * 100
        neg_bad = len([r for r in results["neg"] if r[0] >= 2]) / len(results["neg"]) * 100
        print("  正例里 ≥2 分（会被推荐）的: %.0f%%   ← 召回" % pos_ok)
        print("  负例里 ≥2 分（误报）的:     %.0f%%   ← 误报率" % neg_bad)
        if gap >= 1.0 and pos_ok >= 60 and neg_bad <= 30:
            print("\n  ✅ 机制成立：能把他要的和不要的分开")
        else:
            print("\n  ⚠️ 机制还不够：分离度不足或误报偏高，需要调判据/加标注")

    print("\n  考卷明细（正例应高分、负例应低分）：")
    for sc, t in results["pos"]:
        print("    [%s] %s" % (sc, t))
    for sc, t in results["neg"]:
        print("    [%s] %s  ← 负例" % (sc, t))


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
CRITERIA = """打分方法（分两步判断，不要跳步）：

【第一问】这条内容里有【可以直接拿来做的东西】吗？
  算「有」：代码、命令行、配置、具体的工具/框架名、可复现的步骤或实测数据
  算「没有」：只是报道某事发生、谁发布了什么、谁说了什么、行业趋势感慨、大会现场观察

  第一问答「没有」 → 直接给 0 或 1 分，结束（不用看第二问）
    0 = 跟 AI/技术完全无关（汽车/手机/家电/财经/政治/娱乐）
    1 = 是 AI/技术新闻，但里面没有能动的东西

【第二问】只对第一问答「有」的条目问：这个东西跟我【现在在做的方向】有关系吗？
  我的方向：AI 应用开发、本地部署模型、Agent 工程、代码工具链

  有关系 → 2 分（值得存档，以后要用）
  有关系且我马上就想动手试 → 3 分
  没关系（比如游戏开发、硬件电路、纯学术不落地） → 1 分

注意：宁可给 0 或 1，不要都给 2。大部分内容应该是 0-1 分，只有少数是 2-3 分。
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
    #
    # T-050：加 3 次重试 —— 这是个要双击自己跑的脚本，跑一次 5 分钟，
    # 不能因为一次网络抖动就整轮白跑（实测遇到过 ConnectTimeout）。
    payload = json.dumps({"model": MODEL,
                          "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.2}).encode("utf-8")
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(
                API_URL,
                headers={"Authorization": "Bearer %s" % key,
                         "Content-Type": "application/json"},
                data=payload, timeout=120)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            break
        except Exception as e:
            last_err = e
            if attempt < 2:
                print("    (第 %d 次调用失败：%s，10 秒后重试)" % (attempt + 1, str(e)[:60]))
                time.sleep(10)
    else:
        raise RuntimeError("GLM 调用连续 3 次失败：%s" % last_err)

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
    ap.add_argument("--selftest", action="store_true",
                    help="留出验证：拿你自己的正例/负例当考卷，测打分机制好不好")
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

    # --selftest：只跑机制验证，不写文件、不碰推荐区
    if a.selftest:
        run_selftest(get_key(), marks, batch=a.batch)
        return


    ev = evaluate_previous(OUT, marks)
    if ev:
        print("\n=== 机制自检（上一轮推荐 vs 你后来的标注）===")
        print("  上轮推荐 %d 条 ｜ 你已标 %d 条 ｜ 还没标 %d 条"
              % (ev["total"], ev["labeled"], ev["unlabeled"]))
        if ev["labeled"]:
            rate = ev["hit"] / ev["labeled"] * 100
            print("  命中（你标了能马上用/该存档）：%d 条" % ev["hit"])
            print("  误报（你标了只需知道/与我无关）：%d 条" % ev["miss"])
            print("  → 精确率 %.0f%%%s" % (rate, "  ✅ 机制有效" if rate >= 50
                                          else "  ⚠️ 低于一半，机制需要调"))
            if ev["misses"]:
                print("  误报样例：")
                for it, t in ev["misses"]:
                    print("    [%s] %s" % (LABEL.get(it, it), t))
        else:
            print("  （推荐的条目你还没标过 —— 去站点上标几条，下轮就有数字了）")
    else:
        print("\n=== 机制自检 ===\n  （第一次跑，没有上一轮可比）")

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
