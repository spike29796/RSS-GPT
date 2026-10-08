# -*- coding: utf-8 -*-
"""论文双语阅读页 —— 译文预生成脚本。

为什么要有这个脚本
    站点是 GitHub Pages 静态托管，浏览器里跑不了模型，所以译文不能「点开时才翻」。
    译文必须在这里**预先**生成成静态 JSON，前端只读文件；点某段就当场显示，零等待。

产物
    docs/paper/<id>.json    id = sha1(link)[:16]，与前端 web/src/paperId.js 同一算法
    {
      "id", "source", "link", "title", "title_zh", "published", "translated_at",
      "paragraphs": [{
        "en": "英文段",
        "zh": "中文译文（整段）",
        "sents": [{"en": "英文句", "zh": "中文句"}, ...]   # 行间穿插用；对不齐时为 null
      }, ...]
    }

    阅读页按 sents 逐句穿插渲染：英文句一行，紧跟它自己的中文句。
    sents 为 null 的段退回旧样式（英文整段 + 「看中文」点开）。

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

# index-translate 的 Modelfile 没写 num_predict，Ollama 用默认上限截断长输出。
# 句级翻译的输出比整段翻译长（多了换行和逐句之间的冗余），必须显式抬高上限，
# 否则 JSON 少半个大括号 / 中文断在半句，而且是静默的 —— 不报错，直接写坏文件。
TRANSLATE_NUM_PREDICT = int(os.environ.get('TRANSLATE_NUM_PREDICT', '4096'))


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

def _post_generate(prompt, num_predict, timeout):
    """调 Ollama 生成，返回剥掉思考链前缀的纯文本。

    num_predict 必须显式给：index-translate 的 Modelfile 没设这个参数，
    长输出会被默认上限静默截断 —— 表现为 JSON 少半个大括号、译文断在半句。
    """
    body = json.dumps({
        'model': TRANSLATE_MODEL,
        'prompt': prompt,
        'stream': False,
        'think': False,
        'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': num_predict},
    }).encode('utf-8')
    req = urllib.request.Request(
        TRANSLATE_URL + '/api/generate',
        data=body,
        headers={'Content-Type': 'application/json'},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    out = (resp.get('response') or '').strip()
    # 实测响应会带一段思考链前缀（think:false 不总是生效），解析前统一剥掉
    out = re.sub(r'^[\s\S]*?<｜end▁of▁thinking｜>', '', out, count=1).strip()
    return out


def translate(text):
    """与 translate_step.translate_to_zh 同 prompt / 同 options，但不截断。

    成功返回译文；失败抛异常，由调用处决定怎么降级（translate_step 是静默退回原文，
    这里不能那样 —— 退回原文等于把英文当译文写进文件，前端会重复显示英文）。
    """
    prompt = translate_step._PREFIX + translate_step._glossary_block() + text
    out = _post_generate(prompt, num_predict=TRANSLATE_NUM_PREDICT, timeout=TRANSLATE_TIMEOUT)
    if not out:
        raise RuntimeError('翻译返回空内容')
    return out


# 句级对照方案（踩坑记录，别回退）
#
# 试过让模型自己切句并成对输出 {"en":..., "zh":...}：短段（758 字符）成功 6/6，
# 长段（1662 字符）连跑 3 次输出逐字节相同、全部退化成「整段当一句」，en 字段里塞的还是中文。
# 让它只切句不翻译时又完全正常（11 句，0 汉字）—— 崩点是「切句+翻译+复制原文」的联合任务，
# 不是切句能力，也不是模型改写英文（一度以为它把 are able to solve 改成 can solve，
# 核对 docs/paper/f995cd3882081852.json 原文后确认原文就是 can solve many narrow，误判已撤回）。
# 所以改成：Python 切块 → 模型只输出中文数组 → 按索引配对。
# 这样错位在结构上不可能发生（索引对齐），英文永远是原文（不经过模型），
# 切块粒度不完美也只是「块不严格等于一句」，不会造成中文贴错英文。
_SENT_BOUNDARY_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'(\[])')

# 切出的碎片短于这个长度就并回前一块 —— 挡缩写误切（"et al. Smith" 之类）
_MIN_BLOCK_CHARS = 25


def split_sentences(text):
    """把英文段切成句块。宽松切分：块边界清楚即可，不追求语言学严格。

    块与中文按索引一一对应，所以切歪了也只是粒度问题，不会错位。
    """
    text = (text or '').strip()
    if len(text) <= _MIN_BLOCK_CHARS:
        return [text] if text else []
    out = []
    for piece in _SENT_BOUNDARY_RE.split(text):
        piece = piece.strip()
        if not piece:
            continue
        if out and len(piece) < _MIN_BLOCK_CHARS:
            out[-1] = out[-1] + ' ' + piece
        else:
            out.append(piece)
    return out or [text]


# 只输出中文，不要 JSON。理由：中文译文里引号、书名号、括号满地都是，
# 模型拿全角引号当 JSON 定界符是必然事件（实测 12 段里 2 段栽在这上面，
# 还有 2 段干脆不输出数组、直接给「【统一视角】。我们将…」一段话）。
# 换成「编号 + 一行一句」：两侧都不碰引号，行数对不对一眼能查。
BLOCK_TRANSLATE_PROMPT = (
    '任务：把下面编号的英文句子逐句翻译成中文。\n'
    '输出格式：每句一行，行首写同样的编号，格式是「编号. 译文」。\n'
    '例如输入 3 句，输出就是：\n'
    '1. 第一句的中文译文\n'
    '2. 第二句的中文译文\n'
    '3. 第三句的中文译文\n'
    '\n'
    '要求：\n'
    '- 编号从 1 到 N 连续，不跳号，不多出句子。\n'
    '- 每行只写一句的完整译文，行内不要换行。\n'
    '- 不要输出英文原文，不要解释，不要空行。\n'
    '- 不要输出 JSON、markdown、代码围栏。\n'
    '\n'
    '要翻译的英文句子：\n'
)


def _repair_json_escapes(s):
    """把 JSON 里不合法的反斜杠转义修成合法的。

    论文正文带 LaTeX 残留（`\\in\\mathcal{R}` 这类）。模型翻中文时会把公式原样抄回来，
    抄的时候只写一个反斜杠，`"\\in"` 在 JSON 里就是非法转义，整个数组解析直接失败。
    合法的转义只有 \\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX 这几种。
    """
    s = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)
    # \u 后面必须正好跟 4 位十六进制，否则也是非法
    s = re.sub(r'\\u(?![0-9a-fA-F]{4})', r'\\\\u', s)
    return s


def _extract_json_array(raw):
    """从模型输出里抠出 JSON 数组。输出可能带思考链残渣或代码围栏。"""
    if not raw:
        return None
    start = raw.find('[')
    end = raw.rfind(']')
    if start < 0 or end <= start:
        return None
    chunk = raw[start:end + 1]
    for candidate in (chunk, _repair_json_escapes(chunk)):
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


_NUM_LINE_RE = re.compile(r'^\s*(\d{1,3})\s*[.、)．]\s*(.*)$')


def _parse_numbered(raw, n):
    """按「编号. 译文」解析模型输出。行内续行并进上一项，编号不全就返回 None。

    宁可返回 None 退整段，也不猜残行的归属 —— 猜错就是把中文贴到别的句子上。
    """
    if not raw:
        return None
    items, cur = {}, None
    for line in raw.splitlines():
        m = _NUM_LINE_RE.match(line)
        if m:
            idx = int(m.group(1))
            if 1 <= idx <= n:
                cur = idx
                items[cur] = m.group(2).strip()
            else:
                cur = None
        elif cur is not None and line.strip():
            items[cur] = (items.get(cur, '') + ' ' + line.strip()).strip()
    if len(items) != n:
        return None
    return [items[i] for i in range(1, n + 1)]


def translate_blocks(blocks):
    """一次调用翻一批句块，返回中文数组。项数不符或空项即抛异常。"""
    if not blocks:
        return []
    numbered = '\n'.join('%d. %s' % (i + 1, b) for i, b in enumerate(blocks))
    raw = _post_generate(translate_step._glossary_block() + BLOCK_TRANSLATE_PROMPT + numbered,
                         num_predict=TRANSLATE_NUM_PREDICT, timeout=TRANSLATE_TIMEOUT)
    out = _parse_numbered(raw, len(blocks))
    if out is None:
        arr = _extract_json_array(raw)
        if isinstance(arr, list) and len(arr) == len(blocks):
            out = [str(x).strip() for x in arr]
    if out is None:
        raise RuntimeError('中文行数与块数不符：期望 %d' % len(blocks))
    if any(not x for x in out):
        raise RuntimeError('中文译文有空行')
    return out


def translate_sentences(text):
    """一段英文 → (整段中文, 句级对照数组)。

    返回 (zh, sents)：
      zh    —— 整段中文，前端降级渲染（无 sents 时点击展开）用
      sents —— [{'en': ..., 'zh': ...}, ...]；拿不到可靠对齐时是 None

    只调一次模型（一次翻整段的全部句块）。任何一步不可信就整段退回旧路径 ——
    宁可这一段没有穿插，也不让中文错位贴到别的句子上。
    """
    blocks = split_sentences(text)
    if len(blocks) > 1:
        try:
            zh_list = translate_blocks(blocks)
            return ' '.join(zh_list), [{'en': b, 'zh': z} for b, z in zip(blocks, zh_list)]
        except Exception as e:
            print('[warn] 句级翻译失败（%s: %s），退回整段翻译：%s…'
                  % (type(e).__name__, e, text[:40]), file=sys.stderr)

    return translate(text), None


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
    """读已生成的 json，返回 {en_hash: (zh, sents, has_sents)} —— 段级增量用。

    sents 也要一起缓存：--force 重跑时若只捞回 zh，句级对照就白跑了，
    整篇会退化成旧的点开看中文。

    has_sents 区分两种情况：
      False —— 这篇 json 出自句级改造之前，段里根本没有 sents 字段，
               必须重跑才能补上句级对照；
      True  —— 有字段，sents 是脚本自己的结论（None = 这段切不了），直接复用。
    """
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
            out[para_key(en)] = (zh, p.get('sents'), 'sents' in p)
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
        cached = cache.get(para_key(en))
        if cached and cached[0] and cached[2]:
            zh, sents = cached[0], cached[1]
            reused += 1
        else:
            zh, sents, done = '', None, False
            for attempt in (1, 2):
                try:
                    zh, sents = translate_sentences(en)
                    done = True
                    break
                except Exception as e:
                    log('段翻译失败（第%d次，%s: %s）' % (attempt, type(e).__name__, e))
            if done:
                translated += 1
            else:
                failed += 1
                log('段翻译放弃（%d 字符）' % len(en))
        rows.append({'en': en, 'zh': zh, 'sents': sents})

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
