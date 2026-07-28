"""Validate RSS-GPT output XMLs against the category DoD.

Checks, for each generated feed:
- every <item> has at least one <category>
- every category value is within the allowed 5 classes
- at least one item carries a summary containing the expected marker

Usage: python test/validate_categories.py RSS-GPT/docs
"""
import sys

import feedparser

ALLOWED = {"模型发布", "行业动态", "政策法规", "开源项目", "产品应用"}
FEEDS = ["qbitai", "openai-news", "ithome"]


def main(docs_dir):
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
                if term not in ALLOWED:
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
