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
from email.utils import formatdate

import feedparser
import requests

# Same fixed modern browser UA as main.fetch_feed.
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

AWWWARDS_SITE_URL = 'https://www.awwwards.com/sites/{slug}'
AWWWARDS_THUMB_URL = 'https://assets.awwwards.com/awards/media/cache/thumb_417_299/{path}'


def _log(log_file, message):
    with open(log_file, 'a') as f:
        f.write(message + '\n')


def collect_awwwards_sotd(url, log_file):
    """Collect Awwwards Sites of the Day from the SOTD listing page.

    The page is server-side rendered; every <li> carries a
    data-collectable-model-value attribute holding HTML-entity-encoded JSON
    with slug/title/createdAt/tags/images.thumbnail. No JS execution needed.
    """
    try:
        response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=30)
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


COLLECTORS = {
    'awwwards_sotd': collect_awwwards_sotd,
}
