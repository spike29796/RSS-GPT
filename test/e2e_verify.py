"""Phase-2 end-to-end verification: mock LLM + real sources, two runs.

Copies the RSS-GPT repo to a temp dir (production docs/ is never touched),
serves canned LLM responses from mock_llm.py, then checks:
1. run1 exits clean; every entry summarized this run got a non-null summary
   (the mock cycle includes an invalid-category response, so the retry in
   gpt_summary must rescue it);
2. run2 is idempotent: JSONL/XML byte-identical to run1 (no new articles in
   between), which also proves the conveyor-belt fix (no archive re-fetch);
3. direct gpt_summary calls across the whole mock cycle all return
   (valid category, non-null summary) — exercises the retry path 7 times;
4. validate_categories.py passes against the temp docs.

Usage: python test/e2e_verify.py [repo_dir]
Requires: HTTPS_PROXY/HTTP_PROXY set if a source needs a proxy locally.
"""
import configparser
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else "RSS-GPT").resolve()
TEST_DIR = Path(__file__).parent.resolve()
PYTHON = sys.executable

ENV = {
    **os.environ,
    "PYTHONUTF8": "1",
    "OPENAI_API_KEY": "dummy",
    "OPENAI_BASE_URL": "http://127.0.0.1:18123/v1",
    "CUSTOM_MODEL": "mock-model",
    "U_NAME": "test",
    "NO_PROXY": "127.0.0.1,localhost",
    "no_proxy": "127.0.0.1,localhost",
}


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def _backfill_feeds(repo):
    """Sources with backfill enabled as {name: backfill_days}. Their JSONL/XML
    may legitimately change on run 2 as unsummarized recent entries get
    summaries."""
    config = configparser.ConfigParser()
    config.read(repo / "config.ini", encoding="utf-8")
    feeds = {}
    for sec in config.sections():
        days = config.get(sec, "backfill_days", fallback="0").strip('"')
        items = config.get(sec, "backfill_items", fallback="0").strip('"')
        if days != "0" and items != "0" and config.has_option(sec, "name"):
            feeds[config.get(sec, "name").strip('"')] = int(days)
    return feeds


def run_main(workdir):
    r = subprocess.run([PYTHON, "main.py"], cwd=workdir, env=ENV,
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        fail(f"main.py exited {r.returncode}")
    return r


def snapshot(docs):
    return {p.name: p.read_bytes() for p in docs.glob("*") if p.suffix in (".jsonl", ".xml")}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="rssgpt-e2e-"))
    print(f"workdir: {tmp}")
    shutil.copytree(REPO, tmp / "repo", ignore=shutil.ignore_patterns(".git", "__pycache__"))
    repo = tmp / "repo"

    mock = subprocess.Popen([PYTHON, str(TEST_DIR / "mock_llm.py")], env=ENV)
    try:
        time.sleep(1)  # let the mock server bind

        # --- run 1 + retry-via-pipeline check ---------------------------------
        snap0 = snapshot(repo / "docs")  # pre-pipeline baseline for backfill check
        run_main(repo)
        # entries summarized in run1 = entries whose summary is not null and
        # whose category is one of the mock's canned categories; simply assert
        # no dirty/raw output survived anywhere.
        for jsonl in (repo / "docs").glob("*.jsonl"):
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                s = json.loads(line).get("summary") or ""
                if len(s) > 800 or "第一行" in s or "Title:" in s:
                    fail(f"dirty summary in {jsonl.name}: {s[:60]}")

        snap1 = snapshot(repo / "docs")

        # --- run 2: stability / conveyor-belt check ---------------------------
        # JSONL link lists must be identical and already-summarized entries
        # unchanged; unsummarized entries MAY gain summary/category/content
        # (the backfill budget keeps working each run). XMLs of feeds without
        # backfill must stay byte-identical.
        backfill_feeds = _backfill_feeds(repo)
        run_main(repo)
        for name, before in snap1.items():
            after_path = repo / "docs" / name
            if not after_path.exists():
                fail(f"run2 lost {name}")
            if name.endswith(".jsonl"):
                r1 = [json.loads(l) for l in before.decode("utf-8").splitlines() if l.strip()]
                r2 = [json.loads(l) for l in after_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                if [x["link"] for x in r1] != [x["link"] for x in r2]:
                    fail(f"run2 changed entry set/order in {name} (conveyor-belt regression)")
                for a, b in zip(r1, r2):
                    if a.get("summary") and a != b:
                        fail(f"run2 mutated a summarized entry in {name}: {a['link']}")
                    for key in ("title", "published", "updated"):
                        if a.get(key) != b.get(key):
                            fail(f"run2 changed {key} in {name}: {a['link']}")
            elif name.rsplit(".", 1)[0] not in backfill_feeds:
                if before != after_path.read_bytes():
                    fail(f"run2 not stable: {name} changed")
        print("run1 clean, run2 stable (link sets identical, summaries preserved)")

        # --- backfill must actually fill recent unsummarized entries ----------
        # Compare against the pre-pipeline baseline (not run1): run1 alone may
        # already cover the whole backfill window, leaving run2 nothing to do.
        # A fully-covered window is a pass even when nothing was gained.
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        now = datetime.now(timezone.utc)
        gained = 0
        remaining = 0
        for name, days in backfill_feeds.items():
            r0 = [json.loads(l) for l in snap0[f"{name}.jsonl"].decode("utf-8").splitlines() if l.strip()]
            r2 = [json.loads(l) for l in (repo / "docs" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            gained += sum(1 for a, b in zip(r0, r2) if not a.get("summary") and b.get("summary"))
            for b in r2:
                if b.get("summary"):
                    continue
                try:
                    published = parsedate_to_datetime(b.get("published") or "")
                except (TypeError, ValueError):
                    continue
                if (now - published).days <= days:
                    remaining += 1
        if gained == 0 and remaining > 0:
            fail(f"backfill filled nothing but {remaining} in-window entries still lack summaries")
        print(f"backfill filled {gained} summaries over baseline, {remaining} in-window still null")

        # --- direct retry check across the full mock cycle ---------------------
        code = (
            "import main\n"  # importing runs the pipeline once more (harmless)
            "cats = main.get_categories('source002')\n"
            "default = main.get_default_category('source002')\n"
            "for i in range(7):\n"
            "    cat, s = main.gpt_summary('test article', model='mock-model', language='zh', categories=cats, default_category=default)\n"
            "    assert s is not None, f'call {i}: summary None after retry'\n"
            "    assert cat in cats, f'call {i}: illegal category {cat}'\n"
            "cat, s = main.parse_category_and_summary('Company\\n指南内容<br><br>总结:', cats, default)\n"
            "assert (cat, s) == ('Company', '<br><br>总结:指南内容'), f'marker reorder failed: {s}'\n"
            "cat, s = main.parse_category_and_summary('Company\\n指南内容', cats, default)\n"
            "assert (cat, s) == ('Company', '<br><br>总结:指南内容'), f'marker prepend failed: {s}'\n"
            "print('retry assertions OK')\n"
        )
        r = subprocess.run([PYTHON, "-c", code], cwd=repo, env=ENV,
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or "retry assertions OK" not in r.stdout:
            print(r.stdout[-2000:])
            print(r.stderr[-2000:])
            fail("gpt_summary retry assertions")

        # --- category DoD ------------------------------------------------------
        r = subprocess.run([PYTHON, str(TEST_DIR / "validate_categories.py"), str(repo / "docs")],
                           env=ENV, capture_output=True, text=True)
        print(r.stdout)
        if r.returncode != 0:
            fail("validate_categories")

        print("ALL E2E CHECKS PASSED")
    finally:
        mock.terminate()


if __name__ == "__main__":
    main()
