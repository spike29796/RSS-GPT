# -*- coding: utf-8 -*-
"""批量摘要入口：一次请求处理 N 条，返回格式在 system prompt 里钉死。

设计参考 SillyTavern 预设的思路 —— 先把返回结构写死（JSON 数组 + 固定字段），
再喂内容。这样一次调用顶 N 次，解析是确定的。

单独的模块，不 import main（main.py 顶层有采集代码，一 import 就跑）。
失败时返回 None，调用方回退逐条 gpt_summary()。
"""
import json
import os

import translate_step

BATCH_SIZE = int(os.environ.get('SUMMARY_BATCH_SIZE', '10'))

_HEAD = (
    '你是内容摘要引擎。用户会给你一个 JSON 数组，数组里是 N 篇文章，'
    '每篇有 id、title、article 三个字段。\n'
    '你必须返回一个 JSON 数组，长度必须等于 N，每一项的 id 与输入一一对应。\n'
    '每一项的格式固定为：\n'
    '{"id": <输入的id>, "category": "<分类>", "summary": "<br><br>总结:<一句话>", "title_zh": "<标题的中文>"}\n'
    '\n'
    '严格要求：\n'
    '1. 只输出 JSON 数组本身。不要任何解释文字，不要前后缀，不要 markdown 代码块标记（不要 ```json）。\n'
    '2. category 必须从以下分类中选择且只选一个：{cats}\n'
    '3. summary 必须是一句话，不超过 {n} 字，不要分点、不要编号；'
    '必须以 <br><br>总结: 开头，<br> 是 HTML 换行符，必须保留两个。\n'
    '4. title_zh 是文章标题（title 字段）的中文翻译。若标题已经是中文，原样输出；'
    '若标题是英文专有名词（如产品名），可音译或保留原文；禁止抄正文里的句子。\n'
    '5. 返回数组长度必须等于 N。任何一条即使信息不足也要给出该条的最佳结果，'
    '不要跳过、不要合并条目。\n'
)


def _log(log_file, msg):
    if not log_file:
        return
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('[summary_batch] %s\n' % msg)
    except Exception:
        pass


def _strip_fence(text):
    """剥掉 ```json 围栏，并截取最外层 JSON 数组。"""
    t = (text or '').strip()
    if t.startswith('```'):
        parts = t.split('\n', 1)
        t = parts[1] if len(parts) > 1 else ''
        if t.rstrip().endswith('```'):
            t = t.rstrip()[:-3]
        t = t.strip()
    if not t.startswith('['):
        i, j = t.find('['), t.rfind(']')
        if i != -1 and j > i:
            t = t[i:j + 1]
    return t


def _client():
    """按 main.py 同样的规则建 OpenAI 客户端（含可选代理）。

    key 从 translate_step.api_key() 现取（双 key 轮换）：中途切过 key 之后，
    下一包立刻用新 key，不必重启。
    """
    from openai import OpenAI
    import httpx

    base = os.environ.get('OPENAI_BASE_URL') or os.environ.get('TRANSLATE_URL')
    key = (translate_step.api_key() or os.environ.get('TRANSLATE_API_KEY')
           or os.environ.get('TRANSLATE_KEY') or 'not-needed')
    proxy = os.environ.get('OPENAI_PROXY')
    kw = {'api_key': key, 'base_url': base}
    if proxy:
        kw['http_client'] = httpx.Client(proxy=proxy)
    return OpenAI(**kw)


def summarize_batch(items, model, categories, default_category, language='zh',
                    summary_length=100, log_file=None, stats=None):
    """一次摘要 N 条。

    items 形如 [{"id": int, "query": "标题\\n正文"}, ...]
    返回 {id: "<分类>\\n<summary>\\n<title_zh>"}（三行原文，交给调用方用
    parse_category_and_summary 解析）；整体失败返回 None。
    stats 传入 dict 时，把翻译和摘要两次调用的 usage 都写进去。
    """
    if not items:
        return None
    if language != 'zh':
        # 只有中文站点的输出格式钉死了；其他语言回退逐条。
        return None

    # 1) 批量翻译前置：与逐条版一致，先译成中文再摘要，用于钉术语。
    cap = int(os.environ.get('TRANSLATE_MAX_CHARS', '3000'))
    tr_in = [{'id': it['id'], 'text': it['query'][:cap]} for it in items]
    translated = translate_step.translate_batch_to_zh(tr_in, log_file=log_file, stats=stats)
    if translated is None:
        # 批量翻译失败：逐条兜底。宁可多花几次请求，也别让摘要直接吃原文 ——
        # 术语靠翻译链钉住，吃原文等于整批丢掉钉术语那一层。
        translated = {}
        for it in items:
            zh = translate_step.translate_to_zh(it['query'][:cap], log_file=log_file)
            translated[it['id']] = zh or it['query'][:cap]
        _log(log_file, '翻译批量失败，已逐条兜底')

    # 2) 拼 payload。标题和正文分开给模型，避免它把正文句子当标题。
    payload = []
    for it in items:
        q = translated.get(it['id']) or it['query']
        q = q[:cap]
        lines = q.split('\n', 1)
        title = lines[0].strip()
        article = (lines[1] if len(lines) > 1 else lines[0]).strip()
        payload.append({'id': it['id'], 'title': title, 'article': article[:1500]})

    sys_prompt = (_HEAD.replace('{cats}', '、'.join(categories))
                       .replace('{n}', str(summary_length)))
    messages = [
        {'role': 'system', 'content': sys_prompt},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
    ]
    max_tokens = int(os.environ.get('SUMMARY_BATCH_MAX_TOKENS', '4096'))

    # 3) 一次请求拿回整包。
    try:
        client = _client()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
            timeout=180,
        )
    except Exception as e:
        translate_step.note_call(False, '%s: %s' % (type(e).__name__, str(e)[:120]))
        _log(log_file, '整包失败（%s: %s），回退逐条'
                       % (type(e).__name__, str(e)[:160]))
        return None

    content = resp.choices[0].message.content if getattr(resp, 'choices', None) else None
    if isinstance(stats, dict):
        u = getattr(resp, 'usage', None)
        stats['summary'] = {
            'prompt': getattr(u, 'prompt_tokens', None),
            'completion': getattr(u, 'completion_tokens', None),
            'total': getattr(u, 'total_tokens', None),
        }
    if not content or not content.strip():
        translate_step.note_call(False, 'empty content')
        _log(log_file, '模型返回空内容')
        return None
    try:
        arr = json.loads(_strip_fence(content))
    except Exception as e:
        translate_step.note_call(False, 'unparsable JSON: %s' % str(e)[:100])
        _log(log_file, '整包失败（%s: %s），回退逐条'
                       % (type(e).__name__, str(e)[:160]))
        return None
    translate_step.note_call(True)

    # 4) 按 id 拆回三行文本。缺项/坏项直接不要，调用方对缺的那些回退逐条。
    out = {}
    for row in arr if isinstance(arr, list) else []:
        if not isinstance(row, dict) or 'id' not in row:
            continue
        summ = (row.get('summary') or '').strip()
        if not summ:
            continue
        cat = (row.get('category') or '').strip() or default_category
        tzh = (row.get('title_zh') or '').strip()
        out[row['id']] = '%s\n%s\n%s' % (cat, summ, tzh)

    _log(log_file, '整包返回：%d 条入 -> %d 条出' % (len(payload), len(out)))
    return out or None
