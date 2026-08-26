import feedparser
import configparser
import os
import json
import httpx
from openai import OpenAI
from jinja2 import Template
from bs4 import BeautifulSoup
import re
import datetime
import requests
import time
import traceback
import collectors
#from dateutil.parser import parse

def get_cfg(sec, name, default=None):
    value=config.get(sec, name, fallback=default)
    if value:
        return value.strip('"')

config = configparser.ConfigParser()
# config.ini contains non-ASCII category names; always read as UTF-8 so
# Windows locales (GBK default) don't break parsing.
config.read('config.ini', encoding='utf-8')
secs = config.sections()
# Maxnumber of entries to in a feed.xml file
max_entries = 1000

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
U_NAME = os.environ.get('U_NAME')
OPENAI_PROXY = os.environ.get('OPENAI_PROXY')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
custom_model = os.environ.get('CUSTOM_MODEL')
deployment_url = f'https://{U_NAME}.github.io/RSS-GPT/'
BASE =get_cfg('cfg', 'BASE')
summary_length = int(get_cfg('cfg', 'summary_length'))
language = get_cfg('cfg', 'language')
# Wall-clock budget for the whole backfill phase, in minutes (0 = unlimited).
# A large per-source backfill budget against a slow/flaky API can otherwise
# run past the Actions job timeout — the job is killed before the commit step
# and every summary produced in that run is lost (observed 2026-07-29: a 6h
# run burned tokens and committed nothing).
backfill_max_minutes = float(get_cfg('cfg', 'backfill_max_minutes') or 0)
BACKFILL_DEADLINE = (datetime.datetime.now() + datetime.timedelta(minutes=backfill_max_minutes)).timestamp() if backfill_max_minutes > 0 else None

# LLM retry policy (T-012): at most LLM_MAX_ATTEMPTS API calls per entry per
# run (initial call + retries) with exponential backoff (2s, 4s) on call
# failures — bounds the per-run API-call amplification from retries.
LLM_MAX_ATTEMPTS = 3
LLM_BACKOFF_BASE = 2
# Retry queue: entries whose summarization ultimately failed are stored in
# docs/<name>.retry.jsonl and retried FIRST on later runs (never silently
# dropped). A non-empty queue guarantees at least this many LLM slots per
# run even when the source's backfill budget is smaller or disabled.
RETRY_QUEUE_BATCH = 10


def _llm_deadline(sec):
    """Per-source fair share of the global LLM time budget: the remaining time
    is split evenly across the remaining sources, so one big archive (openai's
    1000-entry backlog) can't eat the whole run while later sources get zero.
    Inline summaries and backfill in output() both respect this deadline."""
    if BACKFILL_DEADLINE is None:
        return None
    now = datetime.datetime.now().timestamp()
    sources = secs[1:]
    try:
        idx = sources.index(sec)
    except ValueError:
        idx = 0
    share = (BACKFILL_DEADLINE - now) / max(1, len(sources) - idx)
    return min(BACKFILL_DEADLINE, now + max(0.0, share))

# Per-feed decompressed size cap (bytes), default 50MB. iter_content decodes
# Content-Encoding transparently, so a gzip bomb (V-03: 305KB on the wire,
# 300MB decompressed, ~1.2GB peak RSS) is only visible *after* decompression —
# the cap must count decompressed bytes, not wire bytes.
feed_max_bytes = int(get_cfg('cfg', 'feed_max_bytes') or (50 * 1024 * 1024))

def fetch_feed(url, log_file):
    feed = None
    headers = {}
    try:
        # Use a fixed modern browser UA: some feeds (e.g. qbitai) reject
        # random or bot-like User-Agent strings with 403.
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        with requests.get(url, headers=headers, timeout=30, stream=True) as response:
            if response.status_code != 200:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Fetch error: {response.status_code}\n")
                return {'feed': None, 'status': response.status_code}
            chunks = []
            downloaded = 0
            for chunk in response.iter_content(chunk_size=65536):
                downloaded += len(chunk)
                if downloaded > feed_max_bytes:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"Fetch aborted: decompressed body exceeds feed_max_bytes={feed_max_bytes} bytes, source skipped: {url}\n")
                    return {'feed': None, 'status': 'too_large'}
                chunks.append(chunk)
            # Replay requests' own .text decoding on the buffered bytes so the
            # parsed result is identical to the old full-download path.
            response._content = b"".join(chunks)
            response._content_consumed = True
            feed = feedparser.parse(response.text)
            return {'feed': feed, 'status': 'success'}
    except requests.RequestException as e:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"Fetch error: {e}\n")
        return {'feed': None, 'status': 'failed'}

def generate_untitled(entry):
    try: return entry.title
    except: 
        try: return entry.article[:50]
        except: return entry.link


def clean_html(html_content):
    """
    This function is used to clean the HTML content.
    It will remove all the <script>, <style>, <img>, <a>, <video>, <audio>, <iframe>, <input> tags.
    Returns:
        Cleaned text for summarization
    """
    soup = BeautifulSoup(html_content, "html.parser")

    for script in soup.find_all("script"):
        script.decompose()

    for style in soup.find_all("style"):
        style.decompose()

    for img in soup.find_all("img"):
        img.decompose()

    for a in soup.find_all("a"):
        a.decompose()

    for video in soup.find_all("video"):
        video.decompose()

    for audio in soup.find_all("audio"):
        audio.decompose()
    
    for iframe in soup.find_all("iframe"):
        iframe.decompose()
    
    for input in soup.find_all("input"):
        input.decompose()

    return soup.get_text()

def filter_entry(entry, filter_apply, filter_type, filter_rule):
    """
    This function is used to filter the RSS feed.

    Args:
        entry: RSS feed entry
        filter_apply: title, article or link
        filter_type: include or exclude or regex match or regex not match
        filter_rule: regex rule or keyword rule, depends on the filter_type

    Raises:
        Exception: filter_apply not supported
        Exception: filter_type not supported
    """
    if filter_apply == 'title':
        text = entry.title
    elif filter_apply == 'article':
        text = entry.article
    elif filter_apply == 'link':
        text = entry.link
    elif not filter_apply:
        return True
    else:
        raise Exception('filter_apply not supported')

    if filter_type == 'include':
        return re.search(filter_rule, text)
    elif filter_type == 'exclude':
        return not re.search(filter_rule, text)
    elif filter_type == 'regex match':
        return re.search(filter_rule, text)
    elif filter_type == 'regex not match':
        return not re.search(filter_rule, text)
    elif not filter_type:
        return True
    else:
        raise Exception('filter_type not supported')

def load_entries(sec):
    """Load stored entries for a source as a list of plain dicts.

    The JSONL data file is the source of truth. When it does not exist yet
    (e.g. first run after deploying this change on the fork), fall back to
    converting the existing feed XML on the fly.

    Args:
        sec: section name in config.ini
    """
    base = os.path.join(BASE, get_cfg(sec, 'name'))
    jsonl_path = base + '.jsonl'
    if os.path.exists(jsonl_path):
        entries = []
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
    xml_path = base + '.xml'
    if os.path.exists(xml_path):
        import migrate_xml_to_jsonl
        feed = feedparser.parse(xml_path)
        return [migrate_xml_to_jsonl.entry_to_record(e) for e in feed.entries]
    return []

def truncate_entries(entries, max_entries):
    if len(entries) > max_entries:
        entries = entries[:max_entries]
    return entries

def _redact_secrets(text):
    """Scrub the API key / base URL out of text before it hits a log file."""
    for secret in (OPENAI_API_KEY, OPENAI_BASE_URL):
        if secret:
            text = text.replace(secret, '<redacted>')
    return text

def load_retry_queue(retry_path):
    """Load a source's retry queue (JSONL, one record per line:
    {"link", "reason", "fail_count", "ts"}). Entries land here when
    summarization ultimately failed (API error after all retries, persistent
    empty content, or non-compliant output) so later runs retry them first
    instead of silently dropping them."""
    queue = {}
    if os.path.exists(retry_path):
        with open(retry_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    queue[rec['link']] = rec
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
    return queue

def save_retry_queue(retry_path, queue):
    """Persist the retry queue; delete the file when nothing is pending."""
    if queue:
        with open(retry_path, 'w', encoding='utf-8') as f:
            for rec in queue.values():
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    elif os.path.exists(retry_path):
        os.remove(retry_path)

def mark_retry(queue, link, reason):
    rec = queue.get(link) or {'link': link, 'fail_count': 0}
    rec['reason'] = reason
    rec['fail_count'] = rec.get('fail_count', 0) + 1
    rec['ts'] = datetime.datetime.now().isoformat(timespec='seconds')
    queue[link] = rec

def record_article(record):
    """Extract the raw article body from a stored record (inverse of the
    content assembly in output()). Unsummarized records store content as
    "\\n" + article; summarized ones carry the summary div as a prefix."""
    article = record['content'][1:] if record['content'].startswith('\n') else record['content']
    if record.get('summary'):
        prefix = "<div> " + record['summary'] + " <div>"
        article = article[len(prefix):] if article.startswith(prefix) else article
    return article

# Built-in fallback used only when config.ini has no categories configured.
DEFAULT_CATEGORIES = ['模型发布', '行业动态', '政策法规', '开源项目', '产品应用']
DEFAULT_CATEGORY = '行业动态'

def get_categories(sec=None):
    """Resolve the allowed category list: per-source override first, then the
    global [cfg] categories key, then the built-in default."""
    raw = get_cfg(sec, 'categories') if sec else None
    if not raw:
        raw = get_cfg('cfg', 'categories')
    if raw:
        return [c.strip() for c in raw.split(',') if c.strip()]
    return list(DEFAULT_CATEGORIES)

def get_default_category(sec=None):
    """Fallback category to guarantee every item gets a valid value.
    Per-source `default_category` key overrides the global one (same pattern
    as get_categories)."""
    if sec:
        value = get_cfg(sec, 'default_category')
        if value:
            return value
    return get_cfg('cfg', 'default_category') or DEFAULT_CATEGORY

SUMMARY_MARKERS = ('<br><br>总结:', '<br><br>Summary:')


def normalize_summary(summary):
    """Ensure the summary starts with the '<br><br>总结:' marker.

    Some models emit the guide text first and append the marker at the end
    (e.g. "指南内容<br><br>总结:"); reorder so the frontend always gets the
    marker-first form. Missing markers are prepended.
    """
    for marker in SUMMARY_MARKERS:
        if marker in summary:
            if summary.startswith(marker):
                return summary
            before, after = summary.split(marker, 1)
            return marker + (before + after).strip()
    return SUMMARY_MARKERS[0] + summary


def parse_category_and_summary(text, categories, default_category):
    """Split the model output into (category, summary).

    The first non-empty line is expected to be the category and the rest is
    the summary. Any output that does not comply falls back to
    default_category with summary=None (same as a summarization failure), so
    the generated XML always has a valid <category> value and non-compliant
    raw model output never leaks into the data layer.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return default_category, None, None
    candidate = re.sub(r'^(分类|类别|category)\s*[:：]?\s*', '', lines[0], flags=re.IGNORECASE).strip()
    if candidate in categories:
        summary = normalize_summary(lines[1]) if len(lines) > 1 else None
        if not summary:
            return candidate, None, None
        # Third line (optional): the translated title. Missing is acceptable
        # and does not trigger a retry.
        title_zh = None
        if len(lines) > 2:
            title_zh = re.sub(r'^(标题|title)\s*[:：]?\s*', '', lines[2], flags=re.IGNORECASE).strip() or None
        return candidate, summary, title_zh
    return default_category, None, None

def gpt_summary(query,model,language,categories,default_category,log_file=None):
    category_list = '、'.join(categories)
    # Input cap: a one-sentence guide needs the lead, not the full article.
    # Multi-k-token articles multiply cost AND latency on a slow relay.
    if len(query) > 2000:
        query = query[:2000]
    # Format instruction goes in the system message (the upstream code put it
    # in an assistant message, which many models treat as content to continue
    # rather than an instruction, hurting format compliance).
    if language == "zh":
        instruction = f"请用中文为这篇文章写一句话导读并翻译标题，严格按照以下格式输出：第一行只输出一个分类，必须从以下分类中选择一个：{category_list}，除此之外第一行不要输出任何其他内容；第二行用中文写一句话导读，不超过{summary_length}字，必须是一句话，不要分点、不要编号，并按照以下格式输出'<br><br>总结:'，<br>是HTML的换行符，输出时必须保留2个，并且必须在'总结:'二字之前；第三行只输出文章标题的中文翻译，除此之外第三行不要输出任何其他内容"
    else:
        instruction = f"Write a one-sentence guide for this article in {language} language and translate the title into {language}, strictly follow this format: the first line must contain exactly one category chosen from: {category_list}, and nothing else; the second line must be a single sentence of no more than {summary_length} words in {language}, no bullet points, no numbering, output in the following format '<br><br>Summary:' , <br> is the line break of HTML, 2 must be retained when output, and must be before the word 'Summary:'; the third line must contain only the article title translated into {language}, and nothing else"
    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": query},
    ]
    if not OPENAI_PROXY:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
    else:
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            # Or use the `OPENAI_BASE_URL` env var
            base_url=OPENAI_BASE_URL,
            # example: "http://my.test.server.example.com:8083",
            http_client=httpx.Client(proxy=OPENAI_PROXY),
            # example:"http://my.test.proxy.example.com",
        )
    # Bounded retries with exponential backoff: at most LLM_MAX_ATTEMPTS API
    # calls per entry per run. Retried conditions: API errors (e.g. the
    # intermittent 404s some relays return) and empty/None content (reasoning
    # models occasionally return it — previously a None content escaped the
    # retry loop via an AttributeError in the parser and burned the entry).
    # Format-non-compliant output is also retried, but immediately (it is not
    # an API fault, so no backoff).
    category, summary, title_zh = default_category, None, None
    for attempt in range(LLM_MAX_ATTEMPTS):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=120,
            )
        except Exception as e:
            if attempt < LLM_MAX_ATTEMPTS - 1:
                wait = LLM_BACKOFF_BASE * 2 ** attempt
                if log_file:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"LLM call failed (attempt {attempt + 1}/{LLM_MAX_ATTEMPTS}), retrying in {wait}s: {_redact_secrets(type(e).__name__ + ': ' + str(e))}\n")
                time.sleep(wait)
                continue
            raise
        # Token accounting per call — settles cost questions with data instead
        # of guesses. Reasoning tokens (thinking models) are called out when
        # the provider reports them.
        if log_file and getattr(completion, 'usage', None):
            u = completion.usage
            details = getattr(u, 'completion_tokens_details', None)
            reasoning = getattr(details, 'reasoning_tokens', 0) if details else 0
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"LLM usage: prompt={u.prompt_tokens} completion={u.completion_tokens} reasoning={reasoning} total={u.total_tokens}\n")
        content = completion.choices[0].message.content if getattr(completion, 'choices', None) else None
        if not content or not content.strip():
            if log_file:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"LLM returned empty content (attempt {attempt + 1}/{LLM_MAX_ATTEMPTS})\n")
            if attempt < LLM_MAX_ATTEMPTS - 1:
                time.sleep(LLM_BACKOFF_BASE * 2 ** attempt)
                continue
            return default_category, None, None
        category, summary, title_zh = parse_category_and_summary(content, categories, default_category)
        if summary is not None:
            return category, summary, title_zh
    return category, summary, title_zh

def output(sec, language):
    """ output
    This function is used to output the summary of the RSS feed.

    Args:
        sec: section name in config.ini

    Raises:
        Exception: filter_apply, type, rule must be set together in config.ini
    """
    log_file = os.path.join(BASE, get_cfg(sec, 'name') + '.log')
    out_dir = os.path.join(BASE, get_cfg(sec, 'name'))
    # read rss_url as a list separated by comma
    rss_urls = get_cfg(sec, 'url')
    rss_urls = rss_urls.split(',')

    # RSS feed filter apply, filter title, article or link, summarize title, article or link
    filter_apply = get_cfg(sec, 'filter_apply')

    # RSS feed filter type, include or exclude or regex match or regex not match
    filter_type = get_cfg(sec, 'filter_type')

    # Regex rule or keyword rule, depends on the filter_type
    filter_rule = get_cfg(sec, 'filter_rule')

    # filter_apply, type, rule must be set together
    if filter_apply and filter_type and filter_rule:
        pass
    elif not filter_apply and not filter_type and not filter_rule:
        pass
    else:
        raise Exception('filter_apply, type, rule must be set together')

    # Max number of items to summarize
    max_items = get_cfg(sec, 'max_items')
    if not max_items:
        max_items = 0
    else:
        max_items = int(max_items)
    cnt = 0
    categories = get_categories(sec)
    default_category = get_default_category(sec)
    collector_name = get_cfg(sec, 'collector')
    existing_entries = load_entries(sec)
    llm_deadline = _llm_deadline(sec)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write('------------------------------------------------------\n')
        f.write(f'Started: {datetime.datetime.now()}\n')
        f.write(f'Existing_entries: {len(existing_entries)}\n')
    # NOTE: do NOT truncate existing entries here. Truncating before the merge
    # drops the oldest entries, which then look "new" to the dedup check when
    # the feed still serves them, causing a conveyor-belt re-fetch cycle
    # (see docs BUG-conveyor-belt). Truncate once, after the merge below.
    # Links dropped by that truncation are recorded in a tombstone file
    # (docs/<name>.dropped) so they are never re-fetched as "new" while the
    # feed keeps serving them. To force a re-fetch, delete the .dropped file.
    dropped_path = os.path.join(BASE, get_cfg(sec, 'name') + '.dropped')
    dropped_links = set()
    if os.path.exists(dropped_path):
        with open(dropped_path, 'r', encoding='utf-8') as f:
            dropped_links = {line.strip() for line in f if line.strip()}
    # Retry queue (T-012): entries whose summarization ultimately failed in
    # earlier runs. Inline failures this run are added to it; the backfill
    # phase below retries queued entries first and clears them on success.
    retry_path = os.path.join(BASE, get_cfg(sec, 'name') + '.retry.jsonl')
    retry_queue = load_retry_queue(retry_path)
    # Links marked this run are excluded from this run's retry/backfill phase
    # so an entry never exceeds LLM_MAX_ATTEMPTS API calls per run.
    retry_marked = set()
    append_entries = []

    for rss_url in rss_urls:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"Fetching from {rss_url}\n")
            print(f"Fetching from {rss_url}")
        if collector_name:
            # Non-RSS source: the collector fetches rss_url and returns a
            # feedparser-compatible pseudo feed.
            collector = collectors.COLLECTORS.get(collector_name)
            if collector is None:
                raise Exception(f'unknown collector: {collector_name}')
            feed = collector(rss_url, log_file)
        else:
            feed = fetch_feed(rss_url, log_file)['feed']
        if not feed:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Fetch failed from {rss_url}\n")
            continue
        for entry in feed.entries:
            if cnt > max_entries:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Skip from: [{entry.title}]({entry.link})\n")
                break

            if '#replay' in entry.link and 'v2ex' in entry.link:
                entry.link = entry.link.split('#')[0]

            if entry.link in [x['link'] for x in existing_entries]:
                continue

            if entry.link in dropped_links:
                continue

            if entry.link in [x.link for x in append_entries]:
                continue

            entry.title = generate_untitled(entry)

            try:
                entry.article = entry.content[0].value
            except:
                try: entry.article = entry.description
                except: entry.article = entry.title

            cleaned_article = clean_html(entry.article)

            if not filter_entry(entry, filter_apply, filter_type, filter_rule):
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Filter: [{entry.title}]({entry.link})\n")
                continue


#            # format to Thu, 27 Jul 2023 13:13:42 +0000
#            if 'updated' in entry:
#                entry.updated = parse(entry.updated).strftime('%a, %d %b %Y %H:%M:%S %z')
#            if 'published' in entry:
#                entry.published = parse(entry.published).strftime('%a, %d %b %Y %H:%M:%S %z')

            cnt += 1
            if cnt > max_items:
                entry.summary = None
            elif OPENAI_API_KEY and (llm_deadline is None or datetime.datetime.now().timestamp() <= llm_deadline):
                # Also gated by the time budget: new items missed today are
                # picked up by backfill on later runs — a lost commit is worse.
                token_length = len(cleaned_article)
                # Title is prepended to the summary input: collector sources
                # (e.g. awwwards) have little body text beyond tags.
                query = f"{entry.title}\n{cleaned_article}"
                if custom_model:
                    try:
                        entry.gpt_category, entry.summary, entry.title_zh = gpt_summary(query,model=custom_model, language=language, categories=categories, default_category=default_category, log_file=log_file)
                        with open(log_file, 'a', encoding='utf-8') as f:
                            f.write(f"Token length: {token_length}\n")
                            f.write(f"Summarized using {custom_model}\n")
                            f.write(f"Category: {entry.gpt_category}\n")
                    except Exception as e:
                        entry.summary = None
                        mark_retry(retry_queue, entry.link, 'api_error')
                        retry_marked.add(entry.link)
                        with open(log_file, 'a', encoding='utf-8') as f:
                            f.write(f"Summarization failed, append the original article\n")
                            f.write(f"error: {_redact_secrets(type(e).__name__ + ': ' + str(e))}\n")
                else:
                    try:
                        entry.gpt_category, entry.summary, entry.title_zh = gpt_summary(query,model="gpt-4o-mini", language=language, categories=categories, default_category=default_category, log_file=log_file)
                        with open(log_file, 'a', encoding='utf-8') as f:
                            f.write(f"Token length: {token_length}\n")
                            f.write(f"Summarized using gpt-4o-mini\n")
                            f.write(f"Category: {entry.gpt_category}\n")
                    except Exception:
                        try:
                            entry.gpt_category, entry.summary, entry.title_zh = gpt_summary(query,model="gpt-4o", language=language, categories=categories, default_category=default_category, log_file=log_file)
                            with open(log_file, 'a', encoding='utf-8') as f:
                                f.write(f"Token length: {token_length}\n")
                                f.write(f"Summarized using GPT-4o\n")
                                f.write(f"Category: {entry.gpt_category}\n")
                        except Exception as e:
                            entry.summary = None
                            mark_retry(retry_queue, entry.link, 'api_error')
                            retry_marked.add(entry.link)
                            with open(log_file, 'a', encoding='utf-8') as f:
                                f.write(f"Summarization failed, append the original article\n")
                                f.write(f"error: {_redact_secrets(type(e).__name__ + ': ' + str(e))}\n")
                if getattr(entry, 'summary', None) is None and entry.link not in retry_marked:
                    # The LLM answered but the output never complied (or the
                    # content was persistently empty): queue the entry for
                    # priority retry on the next run instead of dropping it.
                    mark_retry(retry_queue, entry.link, 'bad_output')
                    retry_marked.add(entry.link)
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"Summarization produced no usable output, queued for retry: [{entry.title}]({entry.link})\n")

            # Category resolution: the feed's own tag wins when available
            # (e.g. openai.com/news ships an official <category> per item),
            # overriding any LLM-chosen value. Sources with noise tags (e.g.
            # WordPress 'Featured') can list them in `ignore_tags`; the first
            # remaining tag is used. Without tags, keep the LLM category,
            # falling back to the default so every item has a valid value.
            # NOTE: must use getattr here - FeedParserDict attribute assignment
            # does not store dict keys, so entry.get('gpt_category') is always None.
            ignored_tags = {t.strip() for t in (get_cfg(sec, 'ignore_tags') or '').split(',') if t.strip()}
            official_category = None
            try:
                for tag in entry.tags:
                    if tag.term and tag.term not in ignored_tags:
                        official_category = tag.term
                        break
            except (AttributeError, IndexError, KeyError, TypeError):
                pass
            if official_category:
                entry.gpt_category = official_category
            elif not getattr(entry, 'gpt_category', None):
                entry.gpt_category = default_category

            append_entries.append(entry)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Append: [{entry.title}]({entry.link})\n")

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f'append_entries: {len(append_entries)}\n')

    # Convert fetched entries to the unified record shape (same as JSONL lines).
    # content is the canonical <content:encoded> body: summary div + article,
    # identical to what the old two-loop template produced.
    append_records = []
    for entry in append_entries:
        summary = getattr(entry, 'summary', None)
        content = ("<div> " + summary + " <div>" if summary else "") + "\n" + entry.article
        published = getattr(entry, 'published', None)
        if not published:
            # Atom feeds (e.g. apple-newsroom) carry only <updated>; normalize
            # via feedparser's parsed struct_time (UTC) to the same RFC 2822
            # shape RSS entries use, so pubDate/backfill windows can parse it.
            st = getattr(entry, 'updated_parsed', None)
            if st:
                from calendar import timegm
                from email.utils import formatdate
                published = formatdate(timegm(st), usegmt=True)
        append_records.append({
            "link": entry.link,
            "title": entry.title,
            "title_zh": getattr(entry, 'title_zh', None),
            "published": published,
            "updated": getattr(entry, 'updated', None),
            "category": getattr(entry, 'gpt_category', None) or default_category,
            "summary": summary,
            "content": content,
        })

    # New entries first, then history; truncate AFTER the merge (conveyor-belt
    # fix). Anything cut off by the truncation goes into the tombstone file so
    # the dedup check above keeps treating it as seen while the feed serves it.
    merged = append_records + existing_entries
    entries = truncate_entries(merged, max_entries=max_entries)
    for record in merged[len(entries):]:
        dropped_links.add(record['link'])
    if dropped_links:
        # Keep the file bounded; the most recently dropped links matter most.
        with open(dropped_path, 'w', encoding='utf-8') as f:
            for link in sorted(dropped_links)[-5000:]:
                f.write(link + '\n')

    # Backfill + retry-queue phase: spend a bounded per-run LLM budget on
    # entries that never got a summary. Priority 1 is the retry queue
    # (entries that FAILED summarization in earlier runs — exempt from the
    # backfill_days window, cleared on success, never silently dropped);
    # priority 2 is the normal backfill window (beyond max_items when
    # appended, or produced before summarization worked; entries with a
    # summary but no title_zh are also eligible — one-time translation
    # backfill). Entries stay newest-first.
    backfill_days = int(get_cfg(sec, 'backfill_days') or 0)
    backfill_items = int(get_cfg(sec, 'backfill_items') or 0)
    if OPENAI_API_KEY:
        from concurrent.futures import ThreadPoolExecutor
        from email.utils import parsedate_to_datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        # A non-empty retry queue guarantees at least RETRY_QUEUE_BATCH LLM
        # slots this run, even when backfill is small/disabled for the source.
        budget = max(backfill_items, RETRY_QUEUE_BATCH) if retry_queue else backfill_items
        candidates = []
        if retry_queue:
            for record in entries:
                if len(candidates) >= budget:
                    break
                if record['link'] not in retry_queue:
                    continue
                if record['link'] in retry_marked:
                    continue  # already burned this run's attempts inline
                if record.get('summary') and record.get('title_zh'):
                    # Completed by other means since it was queued: clear the
                    # record without spending an API call.
                    del retry_queue[record['link']]
                    continue
                candidates.append((record, record_article(record)))
        if backfill_days > 0 and backfill_items > 0 and len(candidates) < budget:
            # Eligible candidates, newest first.
            queued_links = {record['link'] for record, _ in candidates}
            for record in entries:
                if len(candidates) >= budget:
                    break
                if record['link'] in queued_links or record['link'] in retry_marked:
                    continue
                if record.get('summary') and record.get('title_zh'):
                    continue
                try:
                    published = parsedate_to_datetime(record.get('published') or '')
                except (TypeError, ValueError):
                    continue
                if (now - published).days > backfill_days:
                    continue
                candidates.append((record, record_article(record)))

        def backfill_one(record, article):
            started = datetime.datetime.now().timestamp()
            query = f"{record['title']}\n{clean_html(article)}"
            try:
                category, summary, title_zh = gpt_summary(query, model=custom_model or "gpt-4o-mini", language=language, categories=categories, default_category=default_category, log_file=log_file)
            except Exception as e:
                mark_retry(retry_queue, record['link'], 'api_error')
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Backfill failed: [{record['title']}]({record['link']})\nerror: {_redact_secrets(type(e).__name__ + ': ' + str(e))}\n")
                return 0
            if summary is None:
                mark_retry(retry_queue, record['link'], 'bad_output')
                return 0  # non-compliant output; stays queued for the next run
            elapsed = datetime.datetime.now().timestamp() - started
            had_summary = bool(record.get('summary'))
            if had_summary:
                # One-time translation backfill (T-019): the entry already has
                # a summary — fill ONLY the missing title_zh. summary/content/
                # category and every other field stay byte-identical.
                # Previously this path also rewrote summary/content with fresh
                # LLM output, clobbering good summaries (and tripping the e2e
                # "run2 must not mutate summarized entries" assertion).
                if title_zh:
                    record['title_zh'] = title_zh
            else:
                # Keep an already-valid category (e.g. the feed's official
                # tag); only repair missing/stale ones.
                if record.get('category') not in categories:
                    record['category'] = category
                record['summary'] = summary
                if title_zh:
                    record['title_zh'] = title_zh
                record['content'] = "<div> " + summary + " <div>" + "\n" + article
            if record['link'] in retry_queue:
                del retry_queue[record['link']]
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Retry queue cleared: [{record['title']}]({record['link']})\n")
            with open(log_file, 'a', encoding='utf-8') as f:
                if had_summary:
                    f.write(f"title_zh backfilled in {elapsed:.0f}s using {custom_model or 'gpt-4o-mini'}: [{record['title']}]({record['link']})\n")
                else:
                    f.write(f"Backfilled in {elapsed:.0f}s using {custom_model or 'gpt-4o-mini'}: [{record['title']}]({record['link']})\nCategory: {category}\n")
            return 1

        backfilled = 0
        # Account limit is 3 concurrent requests — batch accordingly.
        for i in range(0, len(candidates), 3):
            if llm_deadline is not None and datetime.datetime.now().timestamp() > llm_deadline:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write('Backfill time budget exhausted; remaining entries deferred to the next run.\n')
                break
            with ThreadPoolExecutor(max_workers=3) as pool:
                backfilled += sum(pool.map(lambda c: backfill_one(*c), candidates[i:i + 3]))
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'backfilled_entries: {backfilled}\n')

        # Purge queue records whose entry no longer exists (truncated out of
        # the feed history), then persist the queue once for the whole run.
        live_links = {record['link'] for record in entries}
        for link in list(retry_queue):
            if link not in live_links:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Retry queue purge (entry gone): {link}\n")
                del retry_queue[link]
        save_retry_queue(retry_path, retry_queue)

    # Total fetch failure on a source with no history: do not create empty
    # artifacts (an empty JSONL + missing XML breaks validation downstream).
    if not feed and not entries:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('Fetch failed and no existing entries; skipping output.\n')
        return

    # Lone surrogates (e.g. "\ud800" from LLM JSON responses) cannot be
    # UTF-8 encoded and would crash the disk writes below. They carry no
    # meaning, so drop them before anything hits disk.
    lone_surrogates = re.compile(r'[\ud800-\udfff]')
    for record in entries:
        for key, value in record.items():
            if isinstance(value, str):
                record[key] = lone_surrogates.sub('', value)

    # Data layer first: persist JSONL, then render the XML from the same list.
    with open(out_dir + '.jsonl', 'w', encoding='utf-8') as f:
        for record in entries:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    template = Template(open('template.xml', encoding='utf-8').read())

    # XML 1.0 forbids most C0 control chars even inside CDATA (observed: NUL
    # bytes in deepseek-news article bodies). Strip them at the render
    # boundary so the emitted feed always parses; the JSONL data layer
    # (already written above) keeps the original text.
    invalid_xml_chars = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]')

    def strip_invalid_xml_chars(value):
        return invalid_xml_chars.sub('', value) if isinstance(value, str) else value

    for record in entries:
        for key, value in record.items():
            record[key] = strip_invalid_xml_chars(value)

    try:
        if not feed and os.path.exists(out_dir + '.xml'):
            # Fetch failed this run: reuse the previous XML's channel metadata
            # so the re-rendered XML still reflects the JSONL (e.g. summaries
            # backfilled while the source was unreachable).
            feed = feedparser.parse(out_dir + '.xml')
        rss = template.render(feed=feed, entries=entries)
        with open(out_dir + '.xml', 'w', encoding='utf-8') as f:
            f.write(rss)
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f'Finish: {datetime.datetime.now()}\n')
    except Exception:
        with open (log_file, 'a', encoding='utf-8') as f:
            f.write(f"error when rendering xml, skip {out_dir}\n")
            f.write(traceback.format_exc())
            print(f"error when rendering xml, skip {out_dir}\n")

try:
    os.mkdir(BASE)
except:
    pass

feeds = []
links = []

for x in secs[1:]:
    output(x, language=language)
    feed = {"url": get_cfg(x, 'url').replace(',','<br>'), "name": get_cfg(x, 'name')}
    feeds.append(feed)  # for rendering index.html
    links.append("- "+ get_cfg(x, 'url').replace(',',', ') + " -> " + deployment_url + feed['name'] + ".xml\n")

def append_readme(readme, links):
    with open(readme, 'r', encoding='utf-8') as f:
        readme_lines = f.readlines()
    while readme_lines[-1].startswith('- ') or readme_lines[-1] == '\n':
        readme_lines = readme_lines[:-1]  # remove 1 line from the end for each feed
    readme_lines.append('\n')
    readme_lines.extend(links)
    with open(readme, 'w', encoding='utf-8') as f:
        f.writelines(readme_lines)

append_readme("../README.md", links)

# Rendering the RSS link-list page for GitHub Pages. Since phase 3 the site
# entry page docs/index.html is the Vue app's build artifact, so this list is
# rendered to feeds.html instead — never overwrite index.html here.
with open(os.path.join(BASE, 'feeds.html'), 'w', encoding='utf-8') as f:
    template = Template(open('template.html', encoding='utf-8').read())
    html = template.render(update_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), feeds=feeds)
    f.write(html)
