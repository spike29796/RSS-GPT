# -*- coding: utf-8 -*-
"""manual_probe.py -- one-shot end-to-end probe for the RSS-GPT pipeline.

Runs two real stages against the live services and commits + pushes after
each stage that produced output. A failing stage is recorded in the log and
the script still exits 0: a probe must never fail the scheduler.

  stage 1  fetch + summarize   one entry pulled live from a news source,
                               summarized through the WB relay
  stage 2  paper translate     one entry pulled live from an arxiv source,
                               translated through the WB relay

The summary call mirrors main.py's gpt_summary() shape (system instruction
holding the format rules, user message holding the article text) so the
probe exercises the same chat-completions path the pipeline uses.

Usage
    python manual_probe.py
    python manual_probe.py --news geekpark --paper arxiv-t2i
    python manual_probe.py --no-push          (commit only, no push)

Log
    probe.log beside this script. ASCII only on stdout (the Windows console
    here is GBK and will crash on non-ASCII prints).
"""
import argparse
import configparser
import datetime
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, '.env')
LOG_FILE = os.path.join(HERE, 'probe.log')
PROBE_DIR = 'probe'

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

STAGES = []


# ---------------------------------------------------------------- logging

def log(msg):
    """Append one line to probe.log (UTF-8) and echo an ASCII version."""
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write('[%s] %s\n' % (stamp, msg))
    except Exception:
        pass
    try:
        print(msg.encode('ascii', 'replace').decode('ascii'), flush=True)
    except Exception:
        pass


def log_block(title, body):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write('\n--- %s ---\n%s\n' % (title, body))
    except Exception:
        pass
    print('    [%s written to log]' % title, flush=True)


# ---------------------------------------------------------------- env

def load_env():
    """Same semantics as run_local.py: fill os.environ, never overwrite."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                os.environ.setdefault(k, v)


def load_sources():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(HERE, 'config.ini'), encoding='utf-8')
    out = {}
    for sec in cfg.sections():
        if not sec.startswith('source'):
            continue
        name = (cfg.get(sec, 'name', fallback='') or '').strip().strip('"')
        url = (cfg.get(sec, 'url', fallback='') or '').strip().strip('"')
        if name and url:
            out[name] = url
    return out


# ---------------------------------------------------------------- helpers

def http_get(url, timeout=30, max_bytes=8 * 1024 * 1024):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
        return r.status, raw.decode('utf-8', 'replace')


def first_entry(xml_text):
    """Minimal RSS/Atom take: first <item> or <entry> with its fields.

    Deliberately regex based instead of feedparser: the probe must not add a
    dependency the host may not have, and it only needs title/link/summary.
    """
    import re
    m = re.search(r'<item[\s>].*?</item>', xml_text, re.S)
    if not m:
        m = re.search(r'<entry[\s>].*?</entry>', xml_text, re.S)
    if not m:
        return None
    block = m.group(0)

    def pick(*tags):
        for t in tags:
            mm = re.search(r'<%s[^>]*>(.*?)</%s>' % (t, t), block, re.S)
            if mm:
                v = mm.group(1)
                v = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', v, flags=re.S)
                v = re.sub(r'<[^>]+>', ' ', v)
                v = re.sub(r'\s+', ' ', v).strip()
                if v:
                    return v
        return ''

    return {
        'title': pick('title'),
        'link': pick('link', 'guid'),
        'body': pick('description', 'summary', 'content:encoded', 'content'),
    }


def chat(base_url, api_key, model, messages, timeout=120):
    """Raw chat-completions POST: avoids depending on the openai SDK version
    installed on the host."""
    payload = json.dumps({
        'model': model,
        'messages': messages,
        'stream': False,
    }).encode('utf-8')
    req = urllib.request.Request(
        base_url.rstrip('/') + '/chat/completions',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + (api_key or 'x'),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode('utf-8', 'replace'))
    choice = (data.get('choices') or [{}])[0]
    msg = choice.get('message') or {}
    content = (msg.get('content') or '').strip()
    reasoning = (msg.get('reasoning_content') or '').strip()
    return {
        'content': content,
        'reasoning': reasoning,
        'usage': data.get('usage') or {},
        'finish': choice.get('finish_reason'),
        'raw_head': json.dumps(data, ensure_ascii=False)[:400],
    }


def git(args, name=None, timeout=180):
    t0 = time.time()
    p = subprocess.run('git ' + args, shell=True, cwd=HERE,
                       capture_output=True)
    out = (p.stdout or b'').decode('utf-8', 'replace')
    err = (p.stderr or b'').decode('utf-8', 'replace')
    sec = round(time.time() - t0, 1)
    if name:
        print('    >>> git %-38s rc=%s (%.1fs)' % (args[:38], p.returncode, sec),
              flush=True)
    if p.returncode != 0 and name:
        log('    git %s failed rc=%s: %s' % (args, p.returncode,
                                             (err or out).strip()[:300]))
    return p.returncode, out, err


def commit_and_push(tag, do_push=True):
    """Stage probe/, commit, then sync + push. Returns (ok, note)."""
    rc_add, _, _ = git('add %s' % PROBE_DIR, name='add')
    if rc_add != 0:
        return False, 'add failed rc=%s' % rc_add

    msg = 'probe(%s) at %s' % (tag, datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    rc_c, out_c, _ = git('commit -m "%s" -- %s' % (msg, PROBE_DIR), name='commit')
    if rc_c != 0:
        return False, 'nothing to commit'

    if not do_push:
        return True, 'committed, push skipped'

    rc_p, _, _ = git('pull --rebase --autostash origin main', name='pull')
    if rc_p != 0:
        log('    pull failed rc=%s, aborting rebase and continuing' % rc_p)
        git('rebase --abort', name='rebase-abort')

    for attempt in range(1, 4):
        rc_push, _, _ = git('push origin main', name='push')
        if rc_push == 0:
            return True, 'pushed on attempt %d' % attempt
        log('    push failed rc=%s (attempt %d/3)' % (rc_push, attempt))
        if attempt < 3:
            time.sleep(15)
    return False, 'push failed 3 times'


def write_probe(name, payload):
    os.makedirs(os.path.join(HERE, PROBE_DIR), exist_ok=True)
    path = os.path.join(HERE, PROBE_DIR, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def record(stage, ok, sec, note, detail=''):
    STAGES.append({'stage': stage, 'ok': ok, 'sec': sec, 'note': note})
    log('%-22s %s  %.1fs  %s' % (stage, '[OK]  ' if ok else '[FAIL]', sec, note))
    if detail:
        log_block(stage, detail)


# ---------------------------------------------------------------- stages

def stage_news_summary(source_name, url, base_url, api_key, model,
                       do_push=True):
    t0 = time.time()
    detail = []
    try:
        status, xml_text = http_get(url)
        detail.append('fetch %s -> HTTP %s, %d bytes' % (url, status, len(xml_text)))
        entry = first_entry(xml_text)
        if not entry:
            raise RuntimeError('no parseable item/entry in feed')
        detail.append('title: %s' % entry['title'][:160])
        detail.append('link:  %s' % entry['link'][:200])

        query = (entry['title'] + '\n' + entry['body'])[:2000]
        instruction = (
            'Write a one-sentence guide for this article in zh language and '
            'translate the title into zh, strictly follow this format: the '
            'first line must contain exactly one category chosen from: '
            'model release,industry,developer,open source,product, and nothing '
            'else; the second line must be a single sentence of no more than '
            '50 words in zh, no bullet points, no numbering; the third line '
            'must contain only the translation of the FIRST LINE of the input '
            '(that first line is the article title).'
        )
        messages = [
            {'role': 'system', 'content': instruction},
            {'role': 'user', 'content': query},
        ]
        detail.append('summary request -> %s model=%s' % (base_url, model))
        t1 = time.time()
        res = chat(base_url, api_key, model, messages)
        took = time.time() - t1
        content = res['content'] or res['reasoning']
        detail.append('summary response in %.1fs, finish=%s, usage=%s'
                      % (took, res['finish'], res['usage']))
        detail.append('raw head: %s' % res['raw_head'])
        detail.append('content:\n%s' % content[:1200])
        if not content:
            raise RuntimeError('empty content from relay')

        payload = {
            'probe': 'news_summary',
            'ran_at': datetime.datetime.now().isoformat(),
            'source': source_name,
            'source_url': url,
            'entry': entry,
            'relay': base_url,
            'model': model,
            'latency_sec': round(took, 2),
            'usage': res['usage'],
            'summary': content,
        }
        write_probe('news_summary.json', payload)

        ok, note = commit_and_push('news_summary', do_push)
        detail.append('git: %s' % note)
        record('1 news fetch+summary', ok, time.time() - t0,
               '%s | relay %.1fs | %s' % (entry['title'][:60], took, note),
               '\n'.join(detail))
        return ok
    except Exception as e:
        detail.append(traceback.format_exc())
        record('1 news fetch+summary', False, time.time() - t0,
               '%s: %s' % (type(e).__name__, str(e)[:150]), '\n'.join(detail))
        return False


def stage_paper_translate(source_name, url, base_url, api_key, model,
                          do_push=True):
    t0 = time.time()
    detail = []
    try:
        status, xml_text = http_get(url)
        detail.append('fetch %s -> HTTP %s, %d bytes' % (url, status, len(xml_text)))
        entry = first_entry(xml_text)
        if not entry:
            raise RuntimeError('no parseable item/entry in feed')
        detail.append('title: %s' % entry['title'][:160])
        detail.append('link:  %s' % entry['link'][:200])

        src = entry['body'][:3000] or entry['title']
        instruction = (
            'Translate the following abstract into Chinese. Output only the '
            'translation, no explanation. Keep the terminology consistent: '
            '"agents" and "agent" must always be rendered as the Chinese term '
            'for intelligent agent.'
        )
        messages = [
            {'role': 'system', 'content': instruction},
            {'role': 'user', 'content': src},
        ]
        detail.append('translate request -> %s model=%s' % (base_url, model))
        t1 = time.time()
        res = chat(base_url, api_key, model, messages)
        took = time.time() - t1
        content = res['content'] or res['reasoning']
        detail.append('translate response in %.1fs, finish=%s, usage=%s'
                      % (took, res['finish'], res['usage']))
        detail.append('raw head: %s' % res['raw_head'])
        detail.append('content:\n%s' % content[:1200])
        if not content:
            raise RuntimeError('empty content from relay')

        payload = {
            'probe': 'paper_translate',
            'ran_at': datetime.datetime.now().isoformat(),
            'source': source_name,
            'source_url': url,
            'entry_title': entry['title'],
            'entry_link': entry['link'],
            'source_chars': len(src),
            'relay': base_url,
            'model': model,
            'latency_sec': round(took, 2),
            'usage': res['usage'],
            'translation': content,
        }
        write_probe('paper_translate.json', payload)

        ok, note = commit_and_push('paper_translate', do_push)
        detail.append('git: %s' % note)
        record('2 paper fetch+translate', ok, time.time() - t0,
               '%s | relay %.1fs | %s' % (entry['title'][:60], took, note),
               '\n'.join(detail))
        return ok
    except Exception as e:
        detail.append(traceback.format_exc())
        record('2 paper fetch+translate', False, time.time() - t0,
               '%s: %s' % (type(e).__name__, str(e)[:150]), '\n'.join(detail))
        return False


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--news', default='geekpark',
                    help='source name for the fetch+summary stage')
    ap.add_argument('--paper', default='arxiv-t2i',
                    help='source name for the paper translate stage')
    ap.add_argument('--no-push', action='store_true',
                    help='commit but do not push')
    args = ap.parse_args()

    load_env()
    base_url = os.environ.get('OPENAI_BASE_URL', '')
    api_key = os.environ.get('OPENAI_API_KEY', '')
    model = os.environ.get('CUSTOM_MODEL', '')
    sources = load_sources()

    log('')
    log('=' * 62)
    log('manual probe start')
    log('relay      : %s' % base_url)
    log('model      : %s' % model)
    log('api key    : %s' % ('present' if api_key else 'MISSING'))
    log('news source: %s -> %s' % (args.news, sources.get(args.news, 'NOT IN config.ini')))
    log('paper source: %s -> %s' % (args.paper, sources.get(args.paper, 'NOT IN config.ini')))
    log('push       : %s' % ('off' if args.no_push else 'on'))

    problems = []
    if not base_url:
        problems.append('OPENAI_BASE_URL missing')
    if not model:
        problems.append('CUSTOM_MODEL missing')
    for nm in (args.news, args.paper):
        if nm not in sources:
            problems.append('source "%s" not found in config.ini' % nm)
    if problems:
        record('preflight', False, 0, '; '.join(problems))
    else:
        record('preflight', True, 0,
               'relay=%s model=%s' % (base_url, model))
        stage_news_summary(args.news, sources[args.news], base_url, api_key,
                           model, not args.no_push)
        stage_paper_translate(args.paper, sources[args.paper], base_url,
                              api_key, model, not args.no_push)

    ok_n = sum(1 for s in STAGES if s['ok'])
    log('-' * 62)
    log('probe finished: %d/%d stages ok' % (ok_n, len(STAGES)))
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ran_at': datetime.datetime.now().isoformat(),
                                'stages': STAGES}, ensure_ascii=False) + '\n')
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        log('probe crashed:')
        log_block('crash', traceback.format_exc())
        sys.exit(0)
