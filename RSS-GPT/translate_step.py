# -*- coding: utf-8 -*-
"""摘要前置翻译：把「标题 + 正文」先翻成中文，再交给摘要环节。

接入点
    main.py 的 output()，在构造 query 之后、调 gpt_summary 之前。

为什么加这道工序（2026-10-06 实测数据）
    线上 102 条论文里，同一个词 "agents" 被现有管线译成「代理」24 条、
    「智能体」32 条 —— 同一个模型、同一批数据，自己跟自己打架。
    技术阅读里这种摇摆会积累错误的术语对应关系。
    术语表把这类词钉死。

调用端点（2026-10-22 改）
    原先调本机 Ollama 的 /api/generate。Ollama 只在 03:00-07:00 窗口在线，
    窗口外触发就干等到天亮。现改走 WB 反代（OpenAI 兼容 /chat/completions），
    与 main.py 的摘要链同一个端点，全天可用，不再受窗口约束。

配置（.env）
    TRANSLATE_URL=http://192.168.1.18:8788/v1   OpenAI 兼容根地址（要带 /v1）
    TRANSLATE_MODEL=glm-5.3-flash
    TRANSLATE_TIMEOUT=180
    TRANSLATE_MAX_CHARS=3000
    TRANSLATE_NUM_PREDICT=4096                  映射到 max_tokens
    认证复用 OPENAI_API_KEY（反代要 Bearer）

/api/generate 是 Ollama 原生接口，与 OpenAI 格式不通用：换地址不改请求体
会直接 404，所以这里连请求体一起换成 messages 形态。

没有配置 TRANSLATE_URL 时本模块直接放行原文，行为与接入前完全一致。
翻译失败同样放行原文 —— 新工序不许拖垮老工序。
"""
import json
import os
import urllib.request

TRANSLATE_URL = os.environ.get('TRANSLATE_URL', '').strip().rstrip('/')
TRANSLATE_MODEL = os.environ.get('TRANSLATE_MODEL', 'glm-5.3-flash').strip()
TRANSLATE_TIMEOUT = float(os.environ.get('TRANSLATE_TIMEOUT', '180'))
TRANSLATE_MAX_CHARS = int(os.environ.get('TRANSLATE_MAX_CHARS', '3000'))
TRANSLATE_NUM_PREDICT = int(os.environ.get('TRANSLATE_NUM_PREDICT', '4096'))
TRANSLATE_API_KEY = os.environ.get('OPENAI_API_KEY', '').strip()

# 术语表：硬性要求，出现即按此译。
# 只钉子确实会摇摆的词。表太长模型会乱，要加必须拿实测数据说话。
GLOSSARY = {
    'agents': '智能体',
    'agent': '智能体',
}

# 官方 prompt 形态（README 的 Terminology / constrained translation 一栏）
_PREFIX = '请将以下文本翻译为 中文，直接输出翻译结果，不要进行任何解释。\n\n'


def _glossary_block():
    if not GLOSSARY:
        return ''
    pairs = '，'.join('%s 固定译为「%s」' % (en, zh) for en, zh in GLOSSARY.items())
    return '要求：术语在全文中保持一致（%s），保留原文结构与占位符：\n\n' % pairs


def _headers():
    h = {'Content-Type': 'application/json'}
    if TRANSLATE_API_KEY:
        h['Authorization'] = 'Bearer ' + TRANSLATE_API_KEY
    return h


def _extract_choice(payload):
    """从 OpenAI 兼容响应里取正文。

    content 为空时回落到 reasoning_content —— 推理型模型会把正文放在那里
    （实测 deepseek-v4.1-flash 在反代上就是这个形态，content 空）。
    """
    choice = (payload.get('choices') or [{}])[0]
    msg = choice.get('message') or {}
    return ((msg.get('content') or '').strip()
            or (msg.get('reasoning_content') or '').strip())


def translate_to_zh(query, log_file=None):
    """把摘要输入翻成中文。任何异常都退回原文。"""
    if not TRANSLATE_URL:
        return query

    src = query[:TRANSLATE_MAX_CHARS]

    body = json.dumps({
        'model': TRANSLATE_MODEL,
        'messages': [
            {'role': 'system', 'content': _PREFIX + _glossary_block()},
            {'role': 'user', 'content': src},
        ],
        'stream': False,
        'temperature': 0,
        'max_tokens': TRANSLATE_NUM_PREDICT,
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            TRANSLATE_URL + '/chat/completions',
            data=body,
            headers=_headers(),
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=TRANSLATE_TIMEOUT).read())
        out = _extract_choice(resp)
        if not out:
            _log(log_file, '翻译返回空内容，退回原文')
            return query
        _log(log_file, '翻译完成：%d 字符 -> %d 字符' % (len(src), len(out)))
        return out
    except Exception as e:
        _log(log_file, '翻译失败（%s: %s），退回原文' % (type(e).__name__, e))
        return query


BATCH_SIZE = int(os.environ.get('TRANSLATE_BATCH_SIZE', '10'))

# 批量模式：格式在 system 里钉死，模型只负责填数据。
# 参考 SillyTavern 预设的做法 —— 先把返回结构写死，再喂内容。
_BATCH_SYSTEM = (
    '你是翻译引擎。用户会给你一个 JSON 数组，里面是 N 条待翻译文本。\n'
    '严格要求：\n'
    '1. 只输出 JSON 数组，不要任何解释，不要 markdown 代码块标记。\n'
    '2. 输出的数组长度必须等于输入的 N，每一项的 id 必须与输入一一对应。\n'
    '3. 每一项的格式固定为：{"id": <输入的id>, "zh": "<中文译文>"}\n'
)


def _strip_fence(text):
    """剥掉 ```json 围栏，并截出最外层的 JSON 数组。"""
    t = (text or '').strip()
    if t.startswith('```'):
        t = t.split('\n', 1)[1] if '\n' in t else ''
        if t.rstrip().endswith('```'):
            t = t.rstrip()[:-3]
        t = t.strip()
    # 无条件按最外层 [ ... ] 截取。模型经常在数组后面补一句解释，
    # 只在「不以 [ 开头」时才截，会把 [{...}] 后面那句话一起带进去，
    # json.loads 直接报 Extra data —— 沙箱实测就是这么崩的。
    i, j = t.find('['), t.rfind(']')
    if i != -1 and j > i:
        t = t[i:j + 1]
    return t


def translate_batch_to_zh(items, log_file=None, stats=None):
    """一次翻 N 条。items 形如 [{"id": 1, "text": "..."}]，返回 {id: 译文}。

    stats 传入 dict 时，把本次调用的 usage 写进 stats['translate']。
    任何环节失败都返回 None，调用方回退到逐条 translate_to_zh()。
    """
    if not TRANSLATE_URL or not items:
        return None
    payload = [{'id': it['id'], 'text': it['text'][:TRANSLATE_MAX_CHARS]} for it in items]
    body = json.dumps({
        'model': TRANSLATE_MODEL,
        'messages': [
            {'role': 'system', 'content': _BATCH_SYSTEM + _glossary_block()},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ],
        'stream': False,
        'temperature': 0,
        'max_tokens': TRANSLATE_NUM_PREDICT,
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            TRANSLATE_URL + '/chat/completions',
            data=body,
            headers=_headers(),
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=TRANSLATE_TIMEOUT).read())
        if isinstance(stats, dict):
            u = resp.get('usage') or {}
            stats['translate'] = {
                'prompt': u.get('prompt_tokens'),
                'completion': u.get('completion_tokens'),
                'total': u.get('total_tokens'),
            }
        # strict=False：译文里出现裸换行这类控制字符时不至于整包作废。
        arr = json.loads(_strip_fence(_extract_choice(resp)), strict=False)
        out = {}
        for row in arr:
            if isinstance(row, dict) and 'id' in row and (row.get('zh') or '').strip():
                out[row['id']] = row['zh'].strip()
        if not out:
            # 空返回要留证据：可能模型给了空数组，也可能换了结构。
            _log(log_file, '批量翻译空返回，模型原始输出前 300 字符：%r'
                 % _extract_choice(resp)[:300])
        _log(log_file, '批量翻译：%d 条入 -> %d 条出' % (len(payload), len(out)))
        return out or None
    except Exception as e:
        _log(log_file, '批量翻译失败（%s: %s），交调用方兜底' % (type(e).__name__, e))
        return None


def _log(log_file, msg):
    if not log_file:
        return
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('[translate] ' + msg + '\n')
    except Exception:
        pass
