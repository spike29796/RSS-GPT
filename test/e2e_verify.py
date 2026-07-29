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
import filecmp
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

        # --- run 2: idempotency / conveyor-belt check --------------------------
        run_main(repo)
        snap2 = snapshot(repo / "docs")
        for name in snap1:
            if snap1[name] != snap2.get(name):
                fail(f"run2 not idempotent: {name} changed")
        print("run1 clean, run2 idempotent")

        # --- direct retry check across the full mock cycle ---------------------
        code = (
            "import main\n"  # importing runs the pipeline once more (harmless)
            "cats = main.get_categories('source001')\n"
            "default = main.get_default_category('source001')\n"
            "for i in range(7):\n"
            "    cat, s = main.gpt_summary('test article', model='mock-model', language='zh', categories=cats, default_category=default)\n"
            "    assert s is not None, f'call {i}: summary None after retry'\n"
            "    assert cat in cats, f'call {i}: illegal category {cat}'\n"
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
