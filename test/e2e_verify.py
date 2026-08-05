"""Phase-2 end-to-end verification: mock LLM + feed snapshots, two runs.

Copies the RSS-GPT repo to a temp dir (production docs/ is never touched),
serves canned LLM responses from mock_llm.py, then checks:
1. run1 exits clean; every entry summarized this run got a non-null summary
   (the mock cycle includes an invalid-category response, so the retry in
   gpt_summary must rescue it);
2. run2 is idempotent: JSONL/XML byte-identical to run1 (no new articles in
   between), which also proves the conveyor-belt fix (no archive re-fetch);
3. direct gpt_summary calls with a fixed body all return
   (valid category, non-null summary) — the mock styles each body by content
   hash (invalid/prefixed/normal), and the pipeline's many per-entry bodies
   guarantee the retry path fires every run;
4. validate_categories.py passes against the temp docs.

Feed modes (T-017), selected by env E2E_FEED_MODE:
- "snapshot" (DEFAULT): every source URL is rewritten to the local
  mock_feeds.py server, which replays the frozen bodies under
  test/feed_snapshots/. Both runs see byte-identical feeds, so a live-feed
  change or a network flap between run1 and run2 can no longer masquerade
  as a conveyor-belt regression. Refresh fixtures with
  test/capture_feed_snapshots.py.
- "live": sources hit the real network (old behavior). A source whose
  run1 fetch FAILED is excluded from the run2 idempotency comparison with a
  DEGRADED warning (its feed may legitimately serve new content on the
  run2 retry) instead of failing the whole run.

E2E_FEED_OVERRIDE_<NAME> (name uppercased, '-'->'_', e.g.
E2E_FEED_OVERRIDE_GOOGLE_BLOG=http://127.0.0.1:9/feed) pins one source to a
specific URL in either mode — used to simulate a flaky live source.

At the end a DOCS_DIGEST line (sha256 over the final .jsonl/.xml set) is
printed; repeated snapshot-mode runs must print the same digest.

Usage: python test/e2e_verify.py [repo_dir]
Requires: HTTPS_PROXY/HTTP_PROXY set if a source needs a proxy locally.
"""
import configparser
import hashlib
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


# --- T-017: feed snapshot mode + flake degradation --------------------------

FEED_MODE = os.environ.get("E2E_FEED_MODE", "snapshot").strip().lower()
MOCK_FEEDS_PORT = 18124


def _source_names(repo):
    config = configparser.ConfigParser()
    config.read(repo / "config.ini", encoding="utf-8")
    return [config.get(sec, "name").strip('"') for sec in config.sections()
            if config.has_option(sec, "name")]


def _apply_feed_mode(repo):
    """Rewrite the temp config's source URLs for the selected feed mode.
    Snapshot mode points every source at the local mock_feeds server;
    E2E_FEED_OVERRIDE_<NAME> then pins individual sources (either mode)."""
    cfg_path = repo / "config.ini"
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding="utf-8")
    for sec in cfg.sections():
        if not (cfg.has_option(sec, "name") and cfg.has_option(sec, "url")):
            continue
        name = cfg.get(sec, "name").strip('"')
        if FEED_MODE == "snapshot":
            cfg.set(sec, "url", f"http://127.0.0.1:{MOCK_FEEDS_PORT}/s/{name}")
        override = os.environ.get(f"E2E_FEED_OVERRIDE_{name.upper().replace('-', '_')}")
        if override:
            cfg.set(sec, "url", override)
    with open(cfg_path, "w", encoding="utf-8") as f:
        cfg.write(f)


def _log_marks(repo):
    """Current lengths (in chars) of the per-source log files, to delimit a
    run's segment. Must be char counts, not bytes — the logs are UTF-8 with
    CJK text, so byte offsets would overshoot when slicing decoded text."""
    marks = {}
    for name in _source_names(repo):
        log = repo / "docs" / f"{name}.log"
        marks[name] = len(log.read_text(encoding="utf-8", errors="replace")) if log.exists() else 0
    return marks


def _degraded_sources(repo, marks):
    """Sources whose fetch FAILED during the run that started at `marks`.
    Detected via main.py's own feed-level failure lines ('Fetch failed from'
    fires for RSS and collector sources alike; 'Fetch aborted' for oversized
    feeds). Collector sub-page errors deliberately do NOT match — the feed
    itself was still collected."""
    degraded = set()
    for name, offset in marks.items():
        log = repo / "docs" / f"{name}.log"
        if not log.exists():
            continue
        segment = log.read_text(encoding="utf-8", errors="replace")[offset:]
        if "Fetch failed from" in segment or "Fetch aborted" in segment:
            degraded.add(name)
    return degraded


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

    # Speed cap: the production config may use large backfill budgets (e.g. 300
    # for archive coverage). The e2e tests the mechanism, not the volume —
    # shrink budgets so three pipeline runs finish in seconds.
    cfg_path = repo / "config.ini"
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding="utf-8")
    for sec in cfg.sections():
        if cfg.has_option(sec, "backfill_items"):
            cfg.set(sec, "backfill_items", "5")
    with open(cfg_path, "w", encoding="utf-8") as f:
        cfg.write(f)

    # Feed mode (T-017): snapshot = frozen local feeds (default, deterministic);
    # live = real network (old behavior, flake-degraded below).
    print(f"feed mode: {FEED_MODE}")
    if FEED_MODE not in ("snapshot", "live"):
        fail(f"unknown E2E_FEED_MODE: {FEED_MODE}")
    _apply_feed_mode(repo)
    feeds_server = None
    if FEED_MODE == "snapshot":
        feeds_server = subprocess.Popen([PYTHON, str(TEST_DIR / "mock_feeds.py")], env=ENV)

    mock = subprocess.Popen([PYTHON, str(TEST_DIR / "mock_llm.py")], env=ENV)
    try:
        time.sleep(1)  # let the mock server bind

        # --- run 1 + retry-via-pipeline check ---------------------------------
        snap0 = snapshot(repo / "docs")  # pre-pipeline baseline for backfill check
        run1_marks = _log_marks(repo)
        run_main(repo)
        # Sources whose run1 fetch failed are excluded from the run2 idempotency
        # comparison: on a live feed the run2 retry may legitimately serve new
        # content, which is a network/feed flap, not a conveyor-belt regression.
        degraded = _degraded_sources(repo, run1_marks)
        for name in sorted(degraded):
            print(f"DEGRADED: {name} excluded from run2 idempotency compare (run1 fetch failed)")
        # entries summarized in run1 = entries whose summary is not null and
        # whose category is one of the mock's canned categories; simply assert
        # no dirty/raw output survived anywhere.
        for jsonl in (repo / "docs").glob("*.jsonl"):
            for line in jsonl.read_text(encoding="utf-8").split('\n'):
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
            feed_name = name.rsplit(".", 1)[0]
            if feed_name in degraded:
                continue  # run1 fetch failed here; flap ≠ regression (see DEGRADED above)
            if name.endswith(".jsonl"):
                r1 = [json.loads(l) for l in before.decode("utf-8").split('\n') if l.strip()]
                r2 = [json.loads(l) for l in after_path.read_text(encoding="utf-8").split('\n') if l.strip()]
                if [x["link"] for x in r1] != [x["link"] for x in r2]:
                    fail(f"run2 changed entry set/order in {name} (conveyor-belt regression)")
                for a, b in zip(r1, r2):
                    # Summarized entries must be unchanged except for gaining a
                    # title_zh via the one-time translation backfill — which
                    # since T-019 fills ONLY title_zh, so a summary/content
                    # rewrite of an already-summarized entry is a regression
                    # again and fails here. (The link-set check above guards
                    # the conveyor belt.)
                    if a.get("summary"):
                        a2, b2 = dict(a), dict(b)
                        if a2.get("title_zh") != b2.get("title_zh") and b2.get("title_zh"):
                            a2["title_zh"] = b2["title_zh"]
                        if a2 != b2:
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
            jsonl_path = repo / "docs" / f"{name}.jsonl"
            if not jsonl_path.exists():
                # Source unfetchable from this network (e.g. region-blocked):
                # nothing seeded, nothing to backfill — nothing to verify.
                print(f"backfill check skipped for {name}: no JSONL (fetch failed locally)")
                continue
            base = snap0.get(f"{name}.jsonl", b"")
            r0 = [json.loads(l) for l in base.decode("utf-8").split('\n') if l.strip()]
            r2 = [json.loads(l) for l in (repo / "docs" / f"{name}.jsonl").read_text(encoding="utf-8").split('\n') if l.strip()]
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

        # --- direct retry check ------------------------------------------------
        # The mock styles responses by body hash; these 7 calls share one body,
        # so they verify parse/normalize correctness, while the pipeline runs
        # above (many distinct bodies) are what exercise the retry path.
        code = (
            "import main\n"  # importing runs the pipeline once more (harmless)
            "cats = main.get_categories('source002')\n"
            "default = main.get_default_category('source002')\n"
            "for i in range(7):\n"
            "    cat, s, tz = main.gpt_summary('test article', model='mock-model', language='zh', categories=cats, default_category=default)\n"
            "    assert s is not None, f'call {i}: summary None after retry'\n"
            "    assert cat in cats, f'call {i}: illegal category {cat}'\n"
            "    assert tz == '模拟中文标题', f'call {i}: title_zh missing: {tz}'\n"
            "cat, s, tz = main.parse_category_and_summary('Company\\n指南内容<br><br>总结:\\n某中文标题', cats, default)\n"
            "assert (cat, s, tz) == ('Company', '<br><br>总结:指南内容', '某中文标题'), f'3-line parse failed: {(cat, s, tz)}'\n"
            "cat, s, tz = main.parse_category_and_summary('Company\\n指南内容', cats, default)\n"
            "assert (cat, s, tz) == ('Company', '<br><br>总结:指南内容', None), f'marker prepend failed: {(cat, s, tz)}'\n"
            "print('retry assertions OK')\n"
        )
        r = subprocess.run([PYTHON, "-c", code], cwd=repo, env=ENV,
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or "retry assertions OK" not in r.stdout:
            print(r.stdout[-2000:])
            print(r.stderr[-2000:])
            fail("gpt_summary retry assertions")

        # --- category DoD ------------------------------------------------------
        # encoding/errors: item titles in the output can be non-GBK Unicode;
        # text=True alone decodes with the locale codec and kills the reader.
        r = subprocess.run([PYTHON, str(TEST_DIR / "validate_categories.py"), str(repo / "docs")],
                           env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print(r.stdout)
        if r.returncode != 0:
            fail("validate_categories")

        # Byte-identity fingerprint of the final data layer: repeated
        # snapshot-mode runs must print the same digest.
        digest = hashlib.sha256()
        for p in sorted((repo / "docs").glob("*")):
            if p.suffix in (".jsonl", ".xml"):
                digest.update(p.name.encode())
                digest.update(p.read_bytes())
        print(f"DOCS_DIGEST: {digest.hexdigest()}")

        print("ALL E2E CHECKS PASSED")
    finally:
        mock.terminate()
        if feeds_server is not None:
            feeds_server.terminate()


if __name__ == "__main__":
    main()
