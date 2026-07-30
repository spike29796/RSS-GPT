"""Validate RSS-GPT output XMLs against the category DoD.

Checks, for each generated feed:
- every <item> has at least one <category>
- category legality per source: sources with a `categories` key in config.ini
  are checked against it (+ the global list); sources WITHOUT one are open-
  vocab (official feed tags pass through unchecked, e.g. blog.google)
- at least one item carries a summary containing the expected marker
  (exempt: collector sources that never call the LLM, and freshly seeded
  backfill-enabled sources whose summaries are still pending)

Feeds with no XML on disk are SKIPPED with a note (never seeded from this
network, e.g. region-blocked) — distinct from a parse failure, which fails.

Usage: python test/validate_categories.py RSS-GPT/docs
"""
import configparser
import os
import sys

import feedparser

FEEDS = [
    "openai-news",
    "claude-blog",
    "google-blog",
    "deepseek-news",
    "kimi-blog",
    "microsoft-blog",
    "apple-newsroom",
    "spacex-updates",
    "nvidia-blog",
]


def load_config(docs_dir):
    config_path = os.path.join(os.path.dirname(docs_dir), "config.ini")
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")
    return config


def feed_allowed(config):
    """{feed_name: allowed_set or None}. None = open vocab (no categories key
    configured for that source): any official tag passes."""
    global_raw = config.get("cfg", "categories").strip('"')
    global_set = {c.strip() for c in global_raw.split(",") if c.strip()}
    result = {}
    for sec in config.sections():
        if not config.has_option(sec, "name"):
            continue
        name = config.get(sec, "name").strip('"')
        if config.has_option(sec, "categories"):
            raw = config.get(sec, "categories").strip('"')
            result[name] = global_set | {c.strip() for c in raw.split(",") if c.strip()}
        else:
            result[name] = None
    return result


def load_collector_feeds(config):
    """Names of sources backed by a collector (no LLM summaries expected)."""
    return {
        config.get(sec, "name").strip('"')
        for sec in config.sections()
        if config.has_option(sec, "collector") and config.has_option(sec, "name")
    }


def load_backfill_feeds(config):
    """Names of sources with backfill enabled. A freshly seeded one legitimately
    has zero summaries until the next scheduled run fills them."""
    names = set()
    for sec in config.sections():
        if not config.has_option(sec, "name"):
            continue
        days = config.get(sec, "backfill_days", fallback="0").strip('"')
        items = config.get(sec, "backfill_items", fallback="0").strip('"')
        if days != "0" and items != "0":
            names.add(config.get(sec, "name").strip('"'))
    return names


def main(docs_dir):
    config = load_config(docs_dir)
    allowed_by_feed = feed_allowed(config)
    collector_feeds = load_collector_feeds(config)
    backfill_feeds = load_backfill_feeds(config)
    failures = []
    for name in FEEDS:
        path = f"{docs_dir}/{name}.xml"
        if not os.path.exists(path):
            # Never seeded from this network (e.g. region-blocked fetch):
            # nothing on disk to validate. Distinct from a parse failure.
            print(f"{name}: SKIPPED (no XML — not seeded yet)")
            continue
        feed = feedparser.parse(path)
        if feed.bozo and not feed.entries:
            failures.append(f"{name}: XML parse error: {feed.bozo_exception}")
            continue
        allowed = allowed_by_feed.get(name)
        total = len(feed.entries)
        with_summary = 0
        for i, entry in enumerate(feed.entries):
            terms = [t.get("term") for t in entry.get("tags", [])]
            if not terms:
                failures.append(f"{name}: item #{i} '{entry.get('title', '?')[:30]}' has no category")
            if allowed is not None:
                for term in terms:
                    if term not in allowed:
                        failures.append(f"{name}: item #{i} illegal category '{term}'")
            content = ""
            if entry.get("content"):
                content = entry.content[0].get("value", "")
            if "总结:" in content or "Summary:" in content:
                with_summary += 1
        print(f"{name}: {total} items, {with_summary} with summary")
        if with_summary == 0 and name not in collector_feeds and name not in backfill_feeds:
            # Zero summaries is only a failure when the source summarizes
            # inline (non-collector) and has no backfill to catch up later.
            failures.append(f"{name}: no item contains a summary")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "RSS-GPT/docs")
