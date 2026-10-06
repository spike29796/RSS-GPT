# -*- coding: utf-8 -*-
"""摘要前置翻译：把「标题 + 正文」先翻成中文，再交给摘要环节。

接入点
    main.py 的 output()，在构造 query 之后、调 gpt_summary 之前。

为什么加这道工序（2026-10-06 实测数据）
    线上 102 条论文里，同一个词 "agents" 被现有管线译成「代理」24 条、
    「智能体」32 条 —— 同一个模型、同一批数据，自己跟自己打架。
    技术阅读里这种摇摆会积累错误的术语对应关系。
    Index-Translate-9B 走 instTrans 术语约束翻译，能把这类词钉死。

配置（.env，全部可选）
    TRANSLATE_URL=http://127.0.0.1:11434     Ollama 原生 API 根地址
    TRANSLATE_MODEL=index-translate
    TRANSLATE_TIMEOUT=180
    TRANSLATE_MAX_CHARS=3000

没有配置 TRANSLATE_URL 时本模块直接放行原文，行为与接入前完全一致。
翻译失败同样放行原文 —— 新工序不许拖垮老工序。
"""
import json
import os
import urllib.request

TRANSLATE_URL = os.environ.get('TRANSLATE_URL', '').strip().rstrip('/')
TRANSLATE_MODEL = os.environ.get('TRANSLATE_MODEL', 'index-translate').strip()
TRANSLATE_TIMEOUT = float(os.environ.get('TRANSLATE_TIMEOUT', '180'))
TRANSLATE_MAX_CHARS = int(os.environ.get('TRANSLATE_MAX_CHARS', '3000'))

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


def translate_to_zh(query, log_file=None):
    """把摘要输入翻成中文。任何异常都退回原文。"""
    if not TRANSLATE_URL:
        return query

    src = query[:TRANSLATE_MAX_CHARS]
    prompt = _PREFIX + _glossary_block() + src

    body = json.dumps({
        'model': TRANSLATE_MODEL,
        'prompt': prompt,
        'stream': False,
        'think': False,
        'options': {'temperature': 0, 'num_ctx': 8192},
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            TRANSLATE_URL + '/api/generate',
            data=body,
            headers={'Content-Type': 'application/json'},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=TRANSLATE_TIMEOUT).read())
        out = (resp.get('response') or '').strip()
        if not out:
            _log(log_file, '翻译返回空内容，退回原文')
            return query
        _log(log_file, '翻译完成：%d 字符 -> %d 字符' % (len(src), len(out)))
        return out
    except Exception as e:
        _log(log_file, '翻译失败（%s: %s），退回原文' % (type(e).__name__, e))
        return query


def _log(log_file, msg):
    if not log_file:
        return
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('[translate] ' + msg + '\n')
    except Exception:
        pass
