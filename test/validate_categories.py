"""Validate RSS-GPT output XMLs against the category DoD.

Checks, for each generated feed:
- every <item> has at least one <category>
- every category value is within the allowed classes (read from config.ini,
  no hardcoded list — the config is the single source of truth)
- at least one item carries a summary containing the expected marker

Usage: python test/validate_categories.py RSS-GPT/docs
"""
import configparser
import os
import sys

import feedparser

FEEDS = ["qbitai", "openai-news", "ithome"]


def load_allowed(docs_dir):
    config_path = os.path.join(os.path.dirname(docs_dir), "config.ini")
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")
    raw = config.get("cfg", "categories").strip('"')
    return {c.strip() for c in raw.split(",") if c.strip()}


def main(docs_dir):
    allowed = load_allowed(docs_dir)
    failures = []
    for name in FEEDS:
        path = f"{docs_dir}/{name}.xml"
        feed = feedparser.parse(path)
        if feed.bozo and not feed.entries:
            failures.append(f"{name}: XML parse error: {feed.bozo_exception}")
            continue
        total = len(feed.entries)
        with_summary = 0
        for i, entry in enumerate(feed.entries):
            terms = [t.get("term") for t in entry.get("tags", [])]
            if not terms:
                failures.append(f"{name}: item #{i} '{entry.get('title', '?')[:30]}' has no category")
            for term in terms:
                if term not in allowed:
                    failures.append(f"{name}: item #{i} illegal category '{term}'")
            content = ""
            if entry.get("content"):
                content = entry.content[0].get("value", "")
            if "总结:" in content or "Summary:" in content:
                with_summary += 1
        print(f"{name}: {total} items, {with_summary} with summary")
        if with_summary == 0:
            failures.append(f"{name}: no item contains a summary")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "RSS-GPT/docs")
