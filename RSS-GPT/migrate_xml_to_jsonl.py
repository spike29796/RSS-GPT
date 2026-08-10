"""One-time migration: convert generated feed XMLs into JSONL data files.

Each <item> becomes one JSON line:
    {"link", "title", "published", "updated", "category", "summary", "content"}

- content is the canonical HTML body rendered into <content:encoded>. The XML
  template wraps it as "\\n" + content + "\\n", so one leading and one trailing
  newline are stripped here; re-rendering adds them back byte-for-byte.
- summary is a best-effort extraction (first-line "<div> ... <div>" marker)
  kept for future search use; rendering never depends on it.

Usage: python migrate_xml_to_jsonl.py docs/qbitai.xml [more.xml ...]
Writes a sibling .jsonl next to each input XML (always overwrites).
"""
import json
import re
import sys

import feedparser

SUMMARY_MARKERS = ("总结:", "Summary:")


def entry_to_record(entry):
    content = ""
    if entry.get("content"):
        content = entry.content[0].get("value", "")
    # Undo the template's wrapping newlines (see module docstring).
    if content.startswith("\n"):
        content = content[1:]
    if content.endswith("\n"):
        content = content[:-1]

    summary = None
    m = re.match(r"^<div> (.*?) <div>(?:\n|$)", content, re.DOTALL)
    if m and any(marker in m.group(1) for marker in SUMMARY_MARKERS):
        summary = m.group(1)

    tags = [t.get("term") for t in entry.get("tags", [])]
    return {
        "link": entry.get("link", ""),
        "title": entry.get("title", ""),
        "published": entry.get("published"),
        "updated": entry.get("updated"),
        "category": tags[0] if tags else None,
        "summary": summary,
        "content": content,
    }


def migrate(xml_path):
    feed = feedparser.parse(xml_path)
    out_path = re.sub(r"\.xml$", ".jsonl", xml_path)
    missing_published = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for entry in feed.entries:
            record = entry_to_record(entry)
            if not record["published"]:
                missing_published += 1
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(feed.entries), missing_published, out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    for path in sys.argv[1:]:
        total, missing, out_path = migrate(path)
        print(f"{path} -> {out_path}: {total} items, {missing} missing published")
