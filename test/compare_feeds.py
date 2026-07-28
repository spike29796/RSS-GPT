"""Compare two RSS XML files item by item, aligned by link.

Used to prove the phase-1 refactor (JSONL data layer + unified template)
does not change feed output. New items may legitimately appear at the top of
the current file (fresh fetches), so comparison is aligned by link:

- every item in baseline must still exist in current, with identical
  link/title/category/content
- the relative order of shared items must be preserved
- items only in current are reported as new, not as failures

Usage: python test/compare_feeds.py baseline.xml current.xml
Exit code 0 = identical on shared items, 1 = differences found.
"""
import sys

import feedparser


def load(path):
    feed = feedparser.parse(path)
    items = []
    for e in feed.entries:
        content = ""
        if e.get("content"):
            content = e.content[0].get("value", "")
        items.append({
            "link": e.get("link", ""),
            "title": e.get("title", ""),
            "categories": [t.get("term") for t in e.get("tags", [])],
            "content": content,
        })
    return items


def main(path_a, path_b):
    a, b = load(path_a), load(path_b)
    map_a = {item["link"]: item for item in a}
    links_b = {item["link"] for item in b}
    failures = []

    for item in a:
        if item["link"] not in links_b:
            failures.append(f"missing in current: '{item['title'][:40]}' ({item['link']})")

    new_count = 0
    for item in b:
        base = map_a.get(item["link"])
        if base is None:
            new_count += 1
            continue
        for key in ("title", "categories", "content"):
            if base[key] != item[key]:
                failures.append(
                    f"'{item['title'][:40]}' field '{key}' differs:\n"
                    f"  baseline: {str(base[key])[:120]!r}\n"
                    f"  current:  {str(item[key])[:120]!r}"
                )

    shared_in_a = [item["link"] for item in a if item["link"] in links_b]
    shared_in_b = [item["link"] for item in b if item["link"] in map_a]
    if shared_in_a != shared_in_b:
        failures.append("relative order of shared items changed")

    print(f"baseline {len(a)} items, current {len(b)} items, new {new_count}")
    if failures:
        print(f"DIFFERENCES ({len(failures)}):")
        for f in failures[:20]:
            print(" -", f)
        if len(failures) > 20:
            print(f" ... and {len(failures) - 20} more")
        sys.exit(1)
    print("IDENTICAL on shared items")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
