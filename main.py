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
from fake_useragent import UserAgent
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
keyword_length = int(get_cfg('cfg', 'keyword_length'))
summary_length = int(get_cfg('cfg', 'summary_length'))
language = get_cfg('cfg', 'language')

def fetch_feed(url, log_file):
    feed = None
    response = None
    headers = {}
    try:
        # Use a fixed modern browser UA: some feeds (e.g. qbitai) reject
        # random or bot-like User-Agent strings with 403.
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            return {'feed': feed, 'status': 'success'}
        else:
            with open(log_file, 'a') as f:
                f.write(f"Fetch error: {response.status_code}\n")
            return {'feed': None, 'status': response.status_code}
    except requests.RequestException as e:
        with open(log_file, 'a') as f:
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

def get_default_category():
    """Fallback category to guarantee every item gets a valid value."""
    return get_cfg('cfg', 'default_category') or DEFAULT_CATEGORY

def parse_category_and_summary(text, categories, default_category):
    """Split the model output into (category, summary).

    The first non-empty line is expected to be the category and the rest is
    the summary. Any output that does not comply falls back to
    default_category with the original text kept as the summary, so the
    generated XML always has a valid <category> value.
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return default_category, text
    candidate = re.sub(r'^(分类|类别|category)\s*[:：]?\s*', '', lines[0], flags=re.IGNORECASE).strip()
    if candidate in categories:
        summary = '\n'.join(lines[1:])
        return candidate, summary if summary else text
    return default_category, text

def gpt_summary(query,model,language,categories,default_category):
    category_list = '、'.join(categories)
    if language == "zh":
        messages = [
            {"role": "user", "content": query},
            {"role": "assistant", "content": f"请用中文总结这篇文章，严格按照以下格式输出：第一行只输出一个分类，必须从以下分类中选择一个：{category_list}，除此之外第一行不要输出任何其他内容；从第二行开始，用中文在{summary_length}字内写一个包含所有要点的总结，按顺序分要点输出，并按照以下格式输出'<br><br>总结:'，<br>是HTML的换行符，输出时必须保留2个，并且必须在'总结:'二字之前"}
        ]
    else:
        messages = [
            {"role": "user", "content": query},
            {"role": "assistant", "content": f"Please summarize this article in {language} language, strictly follow this format: the first line must contain exactly one category chosen from: {category_list}, and nothing else; starting from the second line, write a summary containing all the points in {summary_length} words in {language}, output in order by points, and output in the following format '<br><br>Summary:' , <br> is the line break of HTML, 2 must be retained when output, and must be before the word 'Summary:'"}
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
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return parse_category_and_summary(completion.choices[0].message.content, categories, default_category)

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
    default_category = get_default_category()
    existing_entries = load_entries(sec)
    with open(log_file, 'a') as f:
        f.write('------------------------------------------------------\n')
        f.write(f'Started: {datetime.datetime.now()}\n')
        f.write(f'Existing_entries: {len(existing_entries)}\n')
    existing_entries = truncate_entries(existing_entries, max_entries=max_entries)
    # Be careful when the deleted ones are still in the feed, in that case, you will mess up the order of the entries.
    # Truncating old entries is for limiting the file size, 1000 is a safe number to avoid messing up the order.
    append_entries = []

    for rss_url in rss_urls:
        with open(log_file, 'a') as f:
            f.write(f"Fetching from {rss_url}\n")
            print(f"Fetching from {rss_url}")
        feed = fetch_feed(rss_url, log_file)['feed']
        if not feed:
            with open(log_file, 'a') as f:
                f.write(f"Fetch failed from {rss_url}\n")
            continue
        for entry in feed.entries:
            if cnt > max_entries:
                with open(log_file, 'a') as f:
                    f.write(f"Skip from: [{entry.title}]({entry.link})\n")
                break

            if entry.link.find('#replay') and entry.link.find('v2ex'):
                entry.link = entry.link.split('#')[0]

            if entry.link in [x['link'] for x in existing_entries]:
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
                with open(log_file, 'a') as f:
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
            elif OPENAI_API_KEY:
                token_length = len(cleaned_article)
                if custom_model:
                    try:
                        entry.gpt_category, entry.summary = gpt_summary(cleaned_article,model=custom_model, language=language, categories=categories, default_category=default_category)
                        with open(log_file, 'a') as f:
                            f.write(f"Token length: {token_length}\n")
                            f.write(f"Summarized using {custom_model}\n")
                            f.write(f"Category: {entry.gpt_category}\n")
                    except Exception as e:
                        entry.summary = None
                        with open(log_file, 'a') as f:
                            f.write(f"Summarization failed, append the original article\n")
                            f.write(f"error: {e}\n")
                else:
                    try:
                        entry.gpt_category, entry.summary = gpt_summary(cleaned_article,model="gpt-4o-mini", language=language, categories=categories, default_category=default_category)
                        with open(log_file, 'a') as f:
                            f.write(f"Token length: {token_length}\n")
                            f.write(f"Summarized using gpt-4o-mini\n")
                            f.write(f"Category: {entry.gpt_category}\n")
                    except:
                        try:
                            entry.gpt_category, entry.summary = gpt_summary(cleaned_article,model="gpt-4o", language=language, categories=categories, default_category=default_category)
                            with open(log_file, 'a') as f:
                                f.write(f"Token length: {token_length}\n")
                                f.write(f"Summarized using GPT-4o\n")
                                f.write(f"Category: {entry.gpt_category}\n")
                        except Exception as e:
                            entry.summary = None
                            with open(log_file, 'a') as f:
                                f.write(f"Summarization failed, append the original article\n")
                                f.write(f"error: {e}\n")

            # Guarantee every new item has a valid category, even when the
            # summary was skipped (beyond max_items) or summarization failed.
            # NOTE: must use getattr here - FeedParserDict attribute assignment
            # does not store dict keys, so entry.get('gpt_category') is always None.
            if not getattr(entry, 'gpt_category', None):
                entry.gpt_category = default_category

            append_entries.append(entry)
            with open(log_file, 'a') as f:
                f.write(f"Append: [{entry.title}]({entry.link})\n")

    with open(log_file, 'a') as f:
        f.write(f'append_entries: {len(append_entries)}\n')

    # Convert fetched entries to the unified record shape (same as JSONL lines).
    # content is the canonical <content:encoded> body: summary div + article,
    # identical to what the old two-loop template produced.
    append_records = []
    for entry in append_entries:
        summary = getattr(entry, 'summary', None)
        content = ("<div> " + summary + " <div>" if summary else "") + "\n" + entry.article
        append_records.append({
            "link": entry.link,
            "title": entry.title,
            "published": getattr(entry, 'published', None),
            "updated": getattr(entry, 'updated', None),
            "category": getattr(entry, 'gpt_category', None) or default_category,
            "summary": summary,
            "content": content,
        })

    # New entries first, then history (already truncated to max_entries above).
    entries = append_records + existing_entries

    # Data layer first: persist JSONL, then render the XML from the same list.
    with open(out_dir + '.jsonl', 'w', encoding='utf-8') as f:
        for record in entries:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    template = Template(open('template.xml').read())

    try:
        rss = template.render(feed=feed, entries=entries)
        with open(out_dir + '.xml', 'w', encoding='utf-8') as f:
            f.write(rss)
        with open(log_file, 'a') as f:
            f.write(f'Finish: {datetime.datetime.now()}\n')
    except:
        with open (log_file, 'a') as f:
            f.write(f"error when rendering xml, skip {out_dir}\n")
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
    with open(readme, 'r') as f:
        readme_lines = f.readlines()
    while readme_lines[-1].startswith('- ') or readme_lines[-1] == '\n':
        readme_lines = readme_lines[:-1]  # remove 1 line from the end for each feed
    readme_lines.append('\n')
    readme_lines.extend(links)
    with open(readme, 'w') as f:
        f.writelines(readme_lines)

append_readme("README.md", links)
append_readme("README-zh.md", links)

# Rendering index.html used in my GitHub page, delete this if you don't need it.
# Modify template.html to change the style
with open(os.path.join(BASE, 'index.html'), 'w') as f:
    template = Template(open('template.html').read())
    html = template.render(update_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), feeds=feeds)
    f.write(html)
