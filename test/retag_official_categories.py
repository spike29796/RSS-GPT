"""One-off: retag openai-news entries with the feed's official <category>.

Fetches the official RSS (all 1000+ items carry a CDATA <category>), builds a
link -> official-tag map, and rewrites the category field of every record in
docs/openai-news.jsonl. Then run test/rerender_xml.py.

Usage: python test/retag_official_categories.py [docs_dir]
Requires network access to openai.com (set HTTPS_PROXY locally if needed).
"""
import json
import sys
from pathlib import Path

import feedparser
import requests

DOCS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "RSS-GPT" / "docs"
FEED_URL = "https://openai.com/news/rss.xml"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def main():
    resp = requests.get(FEED_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    tag_by_link = {}
    for entry in feed.entries:
        tags = getattr(entry, "tags", None)
        if tags and tags[0].get("term"):
            tag_by_link[entry.link] = tags[0]["term"]
    print(f"official tags fetched: {len(tag_by_link)}")

    path = DOCS_DIR / "openai-news.jsonl"
    # Feed items without a tag (the oldest ~100) get the source default so the
    # value always stays within the official vocabulary.
    import configparser
    config = configparser.ConfigParser()
    config.read(DOCS_DIR.parent / "config.ini", encoding="utf-8")
    default = config.get("source002", "default_category").strip('"')
    records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    retagged = missing = 0
    for rec in records:
        tag = tag_by_link.get(rec["link"])
        if tag is None:
            missing += 1
            tag = default
        if rec.get("category") != tag:
            rec["category"] = tag
            retagged += 1
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"retagged={retagged} unchanged={len(records) - retagged} defaulted_no_feed_tag={missing}")


if __name__ == "__main__":
    main()
