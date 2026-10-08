# -*- coding: utf-8 -*-
"""论文双语阅读页 —— 译文预生成脚本。

为什么要有这个脚本
    站点是 GitHub Pages 静态托管，浏览器里跑不了模型，所以译文不能「点开时才翻」。
    译文必须在这里**预先**生成成静态 JSON，前端只读文件；点某段就当场显示，零等待。

产物
    docs/paper/<id>.json    id = sha1(link)[:16]，与前端 web/src/paperId.js 同一算法
    {
      "id", "source", "link", "title", "title_zh", "published", "translated_at",
      "paragraphs": [{"en": "英文段", "zh": "中文译文"}, ...]
    }

增量
    条目级：docs/paper/<id>.json 已存在 → 整条跳过（--force 可覆盖）
    段级：按 en 文本的 sha1 建索引，已翻好的段直接复用，不重翻
          —— 所以脚本可以中断、可以续跑，重复执行不会浪费算力。

翻译调用
    完全复用 translate_step.py 的 prompt / 术语表 / options（只 import，不改它），
    但不带它的 TRANSLATE_MAX_CHARS 截断 —— 正文是给人读的，按段切已保证长度安全。

单条失败不拖垮其他条；跑完打印统计。
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, 'docs')
PAPER_DIR = os.path.join(DOCS_DIR, 'paper')
ENV_FILE = os.path.join(HERE, '.env')

MIN_PARA_CHARS = 40      # 过短的段（标题、小标签、"GitHub"）丢掉
MAX_PARA_CHARS = 2500    # 超长的段切开，保证单段翻译长度安全
DEFAULT_TRANSLATE_URL = 'http://127.0.0.1:11434'

# 这两个 jsonl 不是资讯源：recommended 是打分器产物、bilibili 是视频，不进阅读页
SKIP_FILES = {'recommended', 'bilibili'}

UA = {'User-Agent': 'Mozilla/5.0 (compatible; RSS-GPT paper_translate)'}


def _load_env(path=ENV_FILE):
    """读 .env（与 run_local.py 同口径：setdefault，不覆盖已有环境变量）。

    必须在 import translate_step 之前调用 —— 那个模块在导入时就把
    TRANSLATE_URL / TRANSLATE_MODEL 读成模块常量了。
    用 utf-8-sig 打开：Windows 上记事本/PowerShell 存出来的 .env 常带 BOM，
    带 BOM 时第一个键会变成 '﻿TRANSLATE_URL'，配置静默失效。
    """
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip().lstrip('﻿')
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    os.environ.setdefault(k, v)
    except Exception as e:
        print('[warn] 读 .env 失败：%s' % e, file=sys.stderr)


_load_env()
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import translate_step  # noqa: E402  只 import，不改它

TRANSLATE_URL = (os.environ.get('TRANSLATE_URL') or DEFAULT_TRANSLATE_URL).strip().rstrip('/')
TRANSLATE_MODEL = os.environ.get('TRANSLATE_MODEL', 'index-translate').strip()
TRANSLATE_TIMEOUT = float(os.environ.get('TRANSLATE_TIMEOUT', '180'))


# ---------------------------------------------------------------- 基础工具

def sha1_16(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]


def para_key(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


def http_get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')


def strip_tags(fragment):
    text = re.sub(r'(?s)<[^>]*>', ' ', fragment)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


# ---------------------------------------------------------------- 翻译

def translate(text):
    """与 translate_step.translate_to_zh 同 prompt / 同 options，但不截断。

    成功返回译文；失败抛异常，由调用处决定怎么降级（translate_step 是静默退回原文，
    这里不能那样 —— 退回原文等于把英文当译文写进文件，前端会重复显示英文）。
    """
    prompt = translate_step._PREFIX + translate_step._glossary_block() + text
    body = json.dumps({
        'model': TRANSLATE_MODEL,
        'prompt': prompt,
        'stream': False,
        'think': False,
        'options': {'temperature': 0, 'num_ctx': 8192},
    }).encode('utf-8')
    req = urllib.request.Request(
        TRANSLATE_URL + '/api/generate',
        data=body,
        headers={'Content-Type': 'application/json'},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=TRANSLATE_TIMEOUT).read())
    out = (resp.get('response') or '').strip()
    if not out:
        raise RuntimeError('翻译返回空内容')
    return out


# ---------------------------------------------------------------- 正文抓取

ARXIV_ABS_RE = re.compile(r'arxiv\.org/abs/([A-Za-z0-9._\-/]+)', re.I)


def arxiv_html_url(link):
    m = ARXIV_ABS_RE.search(link or '')
    return 'https://arxiv.org/html/' + m.group(1) if m else None


def _clean_page(page):
    """去掉 script/style/svg 等噪音，避免把 JS 当正文抽出来。"""
    return re.sub(r'(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>', ' ', page)


def _paras_from_tags(page, pattern):
    out = []
    for frag in re.findall(pattern, page):
        t = strip_tags(frag)
        if t:
            out.append(t)
    return out


def extract_paragraphs(page):
    """从 HTML 抽正文段落。arXiv 新版 HTML 用 <p class="ltx_p">，优先按它抽；
    抽不到就退回任意 <p>。标准库够用，不引重依赖。"""
    page = _clean_page(page)
    # 1) arXiv LaTeXML 正文段
    paras = _paras_from_tags(page, r'(?is)<p[^>]*class="[^"]*ltx_p[^"]*"[^>]*>(.*?)</p>')
    if len(paras) >= 3:
        return paras
    # 2) 通用 <p>
    paras = _paras_from_tags(page, r'(?is)<p[^>]*>(.*?)</p>')
    if paras:
        return paras
    # 3) 最后退回 <li>（有些博客正文全在列表里）；再退不回就交给 entry['content']
    return _paras_from_tags(page, r'(?is)<li[^>]*>(.*?)</li>')


def split_long(text, limit=MAX_PARA_CHARS):
    """超长段按句号切开；仍超长再硬切。"""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ''
    for sent in re.split(r'(?<=[.!?。！？])\s+', text):
        if cur and len(cur) + len(sent) + 1 > limit:
            parts.append(cur)
            cur = sent
        else:
            cur = (cur + ' ' + sent).strip() if cur else sent
    if cur:
        parts.append(cur)
    out = []
    for p in parts:
        while len(p) > limit:
            out.append(p[:limit])
            p = p[limit:]
        if p:
            out.append(p)
    return out


def to_paragraphs(raw_paras):
    """统一收口：按空行再切一次 → 丢过短段 → 切过长段 → 去重。"""
    out, seen = [], set()
    for raw in raw_paras:
        for chunk in re.split(r'\n\s*\n', raw or ''):
            t = re.sub(r'\s+', ' ', chunk).strip()
            if len(t) < MIN_PARA_CHARS:
                continue
            for piece in split_long(t):
                if piece not in seen:
                    seen.add(piece)
                    out.append(piece)
    return out


def fallback_from_content(entry):
    """正文全抓不到时，退回 jsonl 里的 content 片段。"""
    content = entry.get('content') or ''
    text = strip_tags(content)
    # jsonl 的 content 常以 "总结:xxx" 摘要打头，剥掉这一层
    text = re.sub(r'^\s*(总结|摘要)\s*[：:]\s*', '', text)
    return to_paragraphs([text])


def gather_paragraphs(entry, log):
    """按优先级尽力抓正文：arXiv HTML → 原文页 → entry['content']。"""
    link = entry.get('link') or ''
    candidates = []
    ah = arxiv_html_url(link)
    if ah:
        candidates.append(('arxiv-html', ah))
    if link.startswith('http'):
        candidates.append(('page', link))

    for label, url in candidates:
        try:
            paras = to_paragraphs(extract_paragraphs(http_get(url)))
        except Exception as e:
            log('抓取失败 %s（%s: %s）' % (url, type(e).__name__, e))
            continue
        if paras:
            log('正文来源 %s：%d 段' % (label, len(paras)))
            return paras
        log('正文来源 %s 抽不到段落，换下一个：%s' % (label, url))

    paras = fallback_from_content(entry)
    log('正文来源 fallback(content)：%d 段' % len(paras))
    return paras


# ---------------------------------------------------------------- 条目处理

def load_existing(path):
    """读已生成的 json，返回 {en_hash: zh} —— 段级增量用。"""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    out = {}
    for p in data.get('paragraphs') or []:
        en = p.get('en')
        zh = p.get('zh')
        if en and zh:
            out[para_key(en)] = zh
    return out


def process_entry(entry, source, args, log):
    """翻译一条。返回 (status, stats)：status ∈ ok/skip/fail。"""
    link = (entry.get('link') or '').strip()
    if not link.startswith('http'):
        return 'fail', {'reason': '无有效 link'}

    pid = sha1_16(link)
    out_path = os.path.join(PAPER_DIR, pid + '.json')
    if os.path.exists(out_path) and not args.force:
        return 'skip', {}

    paragraphs = gather_paragraphs(entry, log)
    if not paragraphs:
        return 'fail', {'reason': '正文与 content 都抓不到段落'}

    cache = load_existing(out_path) if args.force else {}
    rows, reused, translated, failed = [], 0, 0, 0
    for en in paragraphs:
        zh = cache.get(para_key(en))
        if zh:
            reused += 1
        else:
            zh = ''
            for attempt in (1, 2):
                try:
                    zh = translate(en)
                    break
                except Exception as e:
                    log('段翻译失败（第%d次，%s: %s）' % (attempt, type(e).__name__, e))
            if zh:
                translated += 1
            else:
                failed += 1
                log('段翻译放弃（%d 字符）' % len(en))
        rows.append({'en': en, 'zh': zh})

    if not any(r['zh'] for r in rows):
        return 'fail', {'reason': '整条所有段都翻译失败'}

    data = {
        'id': pid,
        'source': source,
        'link': link,
        'title': entry.get('title') or '',
        'title_zh': entry.get('title_zh') or '',
        'published': entry.get('published') or entry.get('updated') or '',
        'translated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'paragraphs': rows,
    }
    os.makedirs(PAPER_DIR, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return 'ok', {
        'id': pid, 'paras': len(rows), 'translated': translated,
        'reused': reused, 'failed': failed, 'path': out_path,
    }


# ---------------------------------------------------------------- 扫描

def iter_candidates(source_filter):
    """扫 docs/*.jsonl，返回 [(source, entry)]，源内按时间倒序（先翻最新）。"""
    if not os.path.isdir(DOCS_DIR):
        return
    names = sorted(
        n for n in os.listdir(DOCS_DIR)
        if n.endswith('.jsonl') and os.path.isfile(os.path.join(DOCS_DIR, n))
    )
    for name in names:
        stem = name[:-len('.jsonl')]
        if stem in SKIP_FILES or stem.endswith('.retry'):
            continue
        if source_filter and stem != source_filter:
            continue
        entries = []
        with open(os.path.join(DOCS_DIR, name), encoding='utf-8') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if isinstance(e, dict) and e.get('link'):
                    entries.append(e)
        entries.sort(key=lambda e: e.get('published') or e.get('updated') or '', reverse=True)
        for e in entries:
            yield stem, e


def main():
    ap = argparse.ArgumentParser(description='论文双语阅读页译文预生成')
    ap.add_argument('--limit', type=int, default=0,
                    help='最多新翻几条（0=不限）；已生成的条目跳过、不计入')
    ap.add_argument('--source', default='', help='只处理这个源（jsonl 文件名去后缀）')
    ap.add_argument('--force', action='store_true', help='忽略已存在文件，重翻（段级缓存仍生效）')
    args = ap.parse_args()

    t0 = time.time()
    n_ok = n_skip = n_fail = 0
    n_paras = n_translated = n_failed_paras = 0

    def log(msg):
        print('  ' + msg, flush=True)

    print('翻译端点：%s  模型：%s' % (TRANSLATE_URL, TRANSLATE_MODEL), flush=True)
    print('输出目录：%s' % PAPER_DIR, flush=True)

    for source, entry in iter_candidates(args.source):
        if args.limit and n_ok >= args.limit:
            break
        title = (entry.get('title') or entry.get('link') or '')[:80]
        print('[%s] %s' % (source, title), flush=True)
        try:
            status, st = process_entry(entry, source, args, log)
        except Exception as e:
            status, st = 'fail', {'reason': '%s: %s' % (type(e).__name__, e)}
        if status == 'ok':
            n_ok += 1
            n_paras += st['paras']
            n_translated += st['translated']
            n_failed_paras += st['failed']
            print('  ✓ 写出 %s（%d 段，新翻 %d，复用 %d，失败 %d）'
                  % (os.path.basename(st['path']), st['paras'], st['translated'],
                     st['reused'], st['failed']), flush=True)
        elif status == 'skip':
            n_skip += 1
            print('  · 已存在，跳过', flush=True)
        else:
            n_fail += 1
            print('  ✗ 失败：%s' % st.get('reason', ''), flush=True)

    dt = time.time() - t0
    print('\n=== 统计 ===', flush=True)
    print('条目：成功 %d，跳过 %d，失败 %d' % (n_ok, n_skip, n_fail), flush=True)
    print('段落：生成 %d 段，其中新翻 %d 段、段级失败 %d 段' % (n_paras, n_translated, n_failed_paras), flush=True)
    if n_translated:
        print('耗时：%.1fs（新翻 %d 段，平均 %.2fs/段）' % (dt, n_translated, dt / n_translated), flush=True)
    else:
        print('耗时：%.1fs' % dt, flush=True)


if __name__ == '__main__':
    main()
