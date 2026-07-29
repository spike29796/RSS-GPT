"""One-off data repair: clear non-compliant raw model outputs stored as summaries.

Background: the production model repeatedly ignored the "category line + summary"
format; parse_category_and_summary used to keep the whole raw output as the
summary, so prompt echoes / chain-of-thought ended up in docs/*.jsonl (and the
rendered XML). Since main.py now falls back to summary=None, this script applies
the same fix retroactively: summary -> null, and the "<div> summary <div>"
prefix is stripped from content. XML regenerates from JSONL on the next run.

Usage: python test/clean_dirty_summaries.py [docs_dir]
"""
import json
import sys
from pathlib import Path

DOCS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "RSS-GPT" / "docs"
FEEDS = ["qbitai", "ithome", "openai-news"]


def is_dirty(summary: str) -> bool:
    return len(summary) > 800 or "第一行" in summary or "Title:" in summary


def main():
    total_cleaned = 0
    for name in FEEDS:
        path = DOCS_DIR / f"{name}.jsonl"
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        cleaned = []
        for rec in records:
            summary = rec.get("summary") or ""
            if not is_dirty(summary):
                continue
            prefix = "<div> " + summary + " <div>"
            content = rec.get("content") or ""
            if content.startswith(prefix):
                rec["content"] = content[len(prefix):]
            else:
                # summary was never rendered into content; nothing to strip
                assert summary not in content, f"unexpected content layout: {rec.get('link')}"
            rec["summary"] = None
            cleaned.append(rec)
            print(f"[{name}] cleaned: {rec.get('title', '')[:50]} | {rec.get('link')}")
        if cleaned:
            with open(path, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        total_cleaned += len(cleaned)
    print(f"total cleaned: {total_cleaned}")


if __name__ == "__main__":
    main()
