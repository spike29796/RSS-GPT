"""Collectors for non-RSS sources.

A collector fetches a web page and returns a feedparser-compatible pseudo feed
(FeedParserDict with .feed.title/.feed.link/.entries), so the main pipeline in
main.py (dedup, category, JSONL, XML rendering) works unchanged.

Register new collectors in COLLECTORS and reference them from config.ini with
a `collector` key in the source section; the source's `url` key is passed as
the fetch target.
"""
import html
import json
import re
import socket
from email.utils import formatdate

import feedparser
import requests

# Same fixed modern browser UA as main.fetch_feed.
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

AWWWARDS_SITE_URL = 'https://www.awwwards.com/sites/{slug}'
AWWWARDS_THUMB_URL = 'https://assets.awwwards.com/awards/media/cache/thumb_417_299/{path}'

_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, *args, **kwargs):
    # www.awwwards.com publishes an AAAA record; GitHub Actions runners have
    # no IPv6 route, so the first connection attempt dies with ENETUNREACH
    # (Errno 101 "Network is unreachable") and the fetch fails. Force IPv4.
    return _orig_getaddrinfo(host, port, socket.AF_INET, *args, **kwargs)


def _get_ipv4(url, **kwargs):
    socket.getaddrinfo = _ipv4_getaddrinfo
    try:
        return requests.get(url, **kwargs)
    finally:
        socket.getaddrinfo = _orig_getaddrinfo


def _log(log_file, message):
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(message + '\n')


def collect_awwwards_sotd(url, log_file):
    """Collect Awwwards Sites of the Day from the SOTD listing page.

    The page is server-side rendered; every <li> carries a
    data-collectable-model-value attribute holding HTML-entity-encoded JSON
    with slug/title/createdAt/tags/images.thumbnail. No JS execution needed.
    """
    try:
        response = _get_ipv4(url, headers={'User-Agent': USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        _log(log_file, f"Collector fetch error: {e}")
        return None
    if response.status_code != 200:
        _log(log_file, f"Collector fetch error: {response.status_code}")
        return None

    entries = []
    for raw in re.findall(r'data-collectable-model-value="([^"]+)"', response.text):
        try:
            item = json.loads(html.unescape(raw))
            slug = item['slug']
            thumbnail = item.get('images', {}).get('thumbnail')
            tags = item.get('tags') or []
            article = ''
            if thumbnail:
                article += f'<img src="{AWWWARDS_THUMB_URL.format(path=thumbnail)}" />'
            if tags:
                article += '<p>Tags: ' + ', '.join(tags) + '</p>'
            entries.append(feedparser.FeedParserDict({
                'link': AWWWARDS_SITE_URL.format(slug=slug),
                'title': item.get('title') or slug,
                'published': formatdate(item.get('createdAt'), usegmt=True) if item.get('createdAt') else None,
                'updated': None,
                'content': [feedparser.FeedParserDict({'value': article})],
            }))
        except (ValueError, KeyError, TypeError) as e:
            _log(log_file, f"Collector parse error, skip item: {e}")

    _log(log_file, f"Collector awwwards_sotd: {len(entries)} entries")
    return feedparser.FeedParserDict({
        'feed': feedparser.FeedParserDict({'title': 'Awwwards SOTD', 'link': url}),
        'entries': entries,
    })


_MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}


def _parse_blog_date(text):
    """'Jul 28, 2026' -> RFC 2822 string (locale-independent month lookup)."""
    m = re.match(r'([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})', text.strip())
    if not m:
        return None
    mon, day, year = _MONTHS[m.group(1)], int(m.group(2)), int(m.group(3))
    import datetime
    return formatdate(datetime.datetime(year, mon, day, tzinfo=datetime.timezone.utc).timestamp(), usegmt=True)


def collect_claude_blog(url, log_file):
    """Collect articles from claude.com/blog (Webflow, server-rendered).

    Every card carries its official tag(s), exposed as feedparser entry.tags
    so main.py's official-tag category resolution picks them up. The blog
    renders each card twice (grid + list view), so dedupe by link.
    """
    from bs4 import BeautifulSoup
    try:
        response = _get_ipv4(url, headers={'User-Agent': USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        _log(log_file, f"Collector fetch error: {e}")
        return None
    if response.status_code != 200:
        _log(log_file, f"Collector fetch error: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    entries = []
    seen = set()
    for card in soup.select('.card_blog_wrap'):
        try:
            anchor = card.find_parent('a', href=True) or card.find('a', href=True)
            if not anchor:
                continue
            link = 'https://claude.com' + anchor['href'] if anchor['href'].startswith('/') else anchor['href']
            if link in seen:
                continue
            seen.add(link)
            title_el = card.select_one('.card_blog_title')
            date_el = card.select_one('.u-text-style-caption')
            tags = [t.get_text(strip=True) for t in card.select('.card-main_tag-wrap div') if t.get_text(strip=True)]
            img = card.select_one('img.card_blog_illo')
            article = ''
            if img and img.get('src'):
                article += f'<img src="{img["src"]}" />'
            if tags:
                article += '<p>Tags: ' + ', '.join(tags) + '</p>'
            entries.append(feedparser.FeedParserDict({
                'link': link,
                'title': title_el.get_text(strip=True) if title_el else link,
                'published': _parse_blog_date(date_el.get_text()) if date_el else None,
                'updated': None,
                'tags': [feedparser.FeedParserDict({'term': t}) for t in tags],
                'content': [feedparser.FeedParserDict({'value': article})],
            }))
        except (AttributeError, KeyError, TypeError) as e:
            _log(log_file, f"Collector parse error, skip item: {e}")

    _log(log_file, f"Collector claude_blog: {len(entries)} entries")
    return feedparser.FeedParserDict({
        'feed': feedparser.FeedParserDict({'title': 'Claude Blog', 'link': url}),
        'entries': entries,
    })


def _fetch_text(url, log_file):
    """GET helper shared by collectors: IPv4-forced, fixed UA, returns text or None."""
    try:
        response = _get_ipv4(url, headers={'User-Agent': USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        _log(log_file, f"Collector fetch error: {e}")
        return None
    if response.status_code != 200:
        _log(log_file, f"Collector fetch error: {response.status_code}")
        return None
    # requests guesses ISO-8859-1 when the server omits charset (e.g.
    # api-docs.deepseek.com), garbling CJK text — all targets are UTF-8 sites.
    if not response.encoding or response.encoding.lower() == 'iso-8859-1':
        response.encoding = 'utf-8'
    return response.text


def _parse_slash_date(text):
    """'YYYY/MM/DD' -> RFC 2822 string."""
    m = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', text)
    if not m:
        return None
    import datetime
    return formatdate(datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=datetime.timezone.utc).timestamp(), usegmt=True)


def collect_deepseek_news(url, log_file):
    """Collect DeepSeek news from the Docusaurus sidebar (no RSS, no tags).

    Any news page's left sidebar lists all articles as
    <a class="menu__link" href="/(zh-cn/)?news/news...">Title YYYY/MM/DD</a>.
    Article bodies are fetched too (few pages, SSR) so the LLM has text.
    """
    from bs4 import BeautifulSoup
    html_text = _fetch_text(url, log_file)
    if html_text is None:
        return None
    soup = BeautifulSoup(html_text, 'html.parser')
    items = []
    seen = set()
    for a in soup.select('a.menu__link[href*="/news/news"]'):
        link = 'https://api-docs.deepseek.com' + a['href'] if a['href'].startswith('/') else a['href']
        if link in seen:
            continue
        seen.add(link)
        items.append((link, a.get_text(strip=True)))

    entries = []
    for link, text in items:
        try:
            published = _parse_slash_date(text)
            if published is None:
                # Sidebar section headers (e.g. the bare "新闻" parent link)
                # carry no date — not articles.
                continue
            title = re.sub(r'\s*\d{4}/\d{1,2}/\d{1,2}\s*$', '', text).strip() or link
            body = _fetch_text(link, log_file) or ''
            article_soup = BeautifulSoup(body, 'html.parser')
            article_el = article_soup.select('article') or article_soup.select('main')
            article = str(article_el[0]) if article_el else ''
            entries.append(feedparser.FeedParserDict({
                'link': link,
                'title': title,
                'published': published,
                'updated': None,
                'content': [feedparser.FeedParserDict({'value': article})],
            }))
        except (AttributeError, KeyError, TypeError, IndexError) as e:
            _log(log_file, f"Collector parse error, skip item: {e}")

    _log(log_file, f"Collector deepseek_news: {len(entries)} entries")
    return feedparser.FeedParserDict({
        'feed': feedparser.FeedParserDict({'title': 'DeepSeek News', 'link': url}),
        'entries': entries,
    })


def collect_kimi_blog(url, log_file):
    """Collect Kimi Research blog cards from www.kimi.com/blog (Next.js SSR).

    Cards are <a href="/blog/<slug>"> with .card-title / .card-date and a cover
    image. External cards (huggingface.co, github.com, moonshotai.github.io)
    are skipped. No official tags.
    """
    from bs4 import BeautifulSoup
    html_text = _fetch_text(url, log_file)
    if html_text is None:
        return None
    soup = BeautifulSoup(html_text, 'html.parser')
    entries = []
    seen = set()
    for anchor in soup.select('a[href^="/blog/"]'):
        try:
            link = 'https://www.kimi.com' + anchor['href'].split('#')[0]
            if link in seen or link.rstrip('/') == 'https://www.kimi.com/blog':
                continue
            seen.add(link)
            # The anchor may be an absolute overlay inside the card; walk up to
            # the smallest ancestor that carries the card's content.
            scope = anchor
            for _ in range(5):
                if scope is None or scope.select_one('.card-title') or scope.select_one('img'):
                    break
                scope = scope.parent
            if scope is None:
                scope = anchor
            title_el = scope.select_one('.card-title')
            date_el = scope.select_one('.card-date')
            img = scope.select_one('img')
            title = (title_el.get_text(strip=True) if title_el else None) or anchor.get('aria-label') or link
            article = ''
            if img and img.get('src'):
                article += f'<img src="{img["src"]}" />'
            entries.append(feedparser.FeedParserDict({
                'link': link,
                'title': title,
                'published': _parse_slash_date(date_el.get_text()) if date_el else None,
                'updated': None,
                'content': [feedparser.FeedParserDict({'value': article})],
            }))
        except (AttributeError, KeyError, TypeError) as e:
            _log(log_file, f"Collector parse error, skip item: {e}")

    _log(log_file, f"Collector kimi_blog: {len(entries)} entries")
    return feedparser.FeedParserDict({
        'feed': feedparser.FeedParserDict({'title': 'Kimi Blog', 'link': url}),
        'entries': entries,
    })


def collect_spacex_updates(url, log_file):
    """Collect SpaceX updates from the public JSON API behind spacex.com/updates.

    GET <url> (the JSON endpoint) returns the full array (not date-sorted):
    updateId/title/date/image/contentBlocks. Note: Cloudflare region-blocks
    CN/HK IPs (error 1009) — GitHub Actions (US egress) works fine.
    """
    try:
        response = _get_ipv4(url, headers={'User-Agent': USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        _log(log_file, f"Collector fetch error: {e}")
        return None
    if response.status_code != 200:
        _log(log_file, f"Collector fetch error: {response.status_code}")
        return None
    try:
        items = response.json()
    except ValueError as e:
        _log(log_file, f"Collector JSON error: {e}")
        return None

    entries = []
    for item in items:
        try:
            slug = item['updateId']
            blocks = item.get('contentBlocks') or []
            article = ''.join(
                # Skip block ids/None values — only real text goes to the LLM.
                '<p>' + ' '.join(str(v) for v in b.values() if v and not isinstance(v, (int, float))) + '</p>' if isinstance(b, dict) else f'<p>{b}</p>'
                for b in blocks
            )
            image = item.get('image') or {}
            formats = image.get('formats') or {}
            img_url = (formats.get('large') or formats.get('medium') or {}).get('url') or image.get('url')
            if img_url:
                article = f'<img src="{img_url}" />' + article
            entries.append(feedparser.FeedParserDict({
                'link': f'https://www.spacex.com/updates/#{slug}',
                'title': item.get('title') or slug,
                'published': _parse_slash_date((item.get('date') or '').replace('-', '/')) if item.get('date') else None,
                'updated': None,
                'content': [feedparser.FeedParserDict({'value': article})],
            }))
        except (AttributeError, KeyError, TypeError) as e:
            _log(log_file, f"Collector parse error, skip item: {e}")

    _log(log_file, f"Collector spacex_updates: {len(entries)} entries")
    return feedparser.FeedParserDict({
        'feed': feedparser.FeedParserDict({'title': 'SpaceX Updates', 'link': 'https://www.spacex.com/updates/'}),
        'entries': entries,
    })


COLLECTORS = {
    'awwwards_sotd': collect_awwwards_sotd,
    'claude_blog': collect_claude_blog,
    'deepseek_news': collect_deepseek_news,
    'kimi_blog': collect_kimi_blog,
    'spacex_updates': collect_spacex_updates,
}
