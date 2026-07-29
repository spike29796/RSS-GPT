"""Re-render feed XMLs from the JSONL data layer without fetching or LLM calls.

Uses the same template.xml and record shape as main.py; channel title/link are
taken from the current XML (identical to what the source feed provides).
Useful after repairing JSONL data so the published XML matches the data layer.

Usage: python test/rerender_xml.py [docs_dir]
"""
import json
import sys
from pathlib import Path

import feedparser
from jinja2 import Template

DOCS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "RSS-GPT" / "docs"
FEEDS = ["openai-news", "claude-blog"]


def main():
    template = Template((DOCS_DIR.parent / "template.xml").read_text(encoding="utf-8"))
    for name in FEEDS:
        xml_path = DOCS_DIR / f"{name}.xml"
        feed = feedparser.parse(str(xml_path))  # only feed.feed.title/link are used
        entries = [
            json.loads(line)
            for line in (DOCS_DIR / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        xml_path.write_text(template.render(feed=feed, entries=entries), encoding="utf-8")
        print(f"{name}: re-rendered {len(entries)} items")


if __name__ == "__main__":
    main()
