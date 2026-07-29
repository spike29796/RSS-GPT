"""One-off refresh: null out long-form summaries and stale categories so the
daily backfill refills them with the new one-line format.

For each source with backfill_days > 0, entries within the window are reset:
- summary plain text longer than 80 chars (old 200-char bullet format)
  -> summary=None, and the "<div> summary <div>" prefix stripped from content;
- category not in the source's current allowed set (e.g. awwwards' old
  「设计灵感」) -> reset to the source's default_category.

Afterwards run test/rerender_xml.py, then validate_categories.py.
Usage: python test/refresh_summaries.py [docs_dir]
"""
import json
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

DOCS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "RSS-GPT" / "docs"
MAX_PLAIN = 80
TAG_RE = re.compile(r"<[^>]+>")


def main():
    import configparser
    config = configparser.ConfigParser()
    config.read(DOCS_DIR.parent / "config.ini", encoding="utf-8")
    now = datetime.now(timezone.utc)

    for sec in config.sections():
        days = int(config.get(sec, "backfill_days", fallback="0").strip('"'))
        if days <= 0:
            continue
        name = config.get(sec, "name").strip('"')
        global_cats = [c.strip() for c in config.get("cfg", "categories").strip('"').split(",") if c.strip()]
        allowed = [c.strip() for c in config.get(sec, "categories", fallback="").strip('"').split(",") if c.strip()] or global_cats
        default = config.get(sec, "default_category", fallback=config.get("cfg", "default_category")).strip('"')

        path = DOCS_DIR / f"{name}.jsonl"
        records = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        n_summary = n_cat = 0
        for rec in records:
            try:
                published = parsedate_to_datetime(rec.get("published") or "")
            except (TypeError, ValueError):
                continue
            if (now - published).days > days:
                continue
            summary = rec.get("summary")
            if summary:
                plain = TAG_RE.sub("", summary).replace("总结:", "").strip()
                if len(plain) > MAX_PLAIN:
                    prefix = "<div> " + summary + " <div>"
                    if rec["content"].startswith(prefix):
                        rec["content"] = rec["content"][len(prefix):]
                    rec["summary"] = None
                    n_summary += 1
            if rec.get("category") not in allowed:
                rec["category"] = default
                n_cat += 1
        if n_summary or n_cat:
            with open(path, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{name}: reset_summary={n_summary} reset_category={n_cat} (window {days}d)")


if __name__ == "__main__":
    main()
