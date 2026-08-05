"""Capture live feed snapshots for e2e snapshot mode (T-017).

Fetches each source's configured URL once from the live network and stores
the raw response body as test/feed_snapshots/<name>.body plus a <name>.json
meta (url, status, content_type, fetched_at, bytes). On fetch failure the
error goes into the meta; any previously captured body is kept and flagged
"stale" (mock_feeds keeps serving it). Sources with no body at all (e.g.
region-blocked from this network) are served as a deterministic 500 by
mock_feeds, mirroring "unreachable from here".

Re-run manually whenever the frozen feeds should move forward:

    python test/capture_feed_snapshots.py [path/to/config.ini]
"""
import configparser
import datetime
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.resolve()
CONFIG = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "RSS-GPT" / "config.ini"
OUT = ROOT / "feed_snapshots"
# Same fixed modern browser UA as main.fetch_feed / collectors.
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


def sources(config_path):
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")
    for sec in config.sections():
        if config.has_option(sec, "name") and config.has_option(sec, "url"):
            name = config.get(sec, "name").strip('"')
            urls = [u.strip().strip('"') for u in config.get(sec, "url").split(",") if u.strip()]
            yield name, urls


def main():
    OUT.mkdir(exist_ok=True)
    ok = stale = missing = 0
    for name, urls in sources(CONFIG):
        url = urls[0]
        body_path = OUT / f"{name}.body"
        meta = {
            "name": name,
            "url": url,
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        for attempt in range(3):
            try:
                r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
                meta.update(status=r.status_code,
                            content_type=r.headers.get("Content-Type", ""),
                            bytes=len(r.content))
                if r.status_code == 200:
                    body_path.write_bytes(r.content)
                break
            except requests.RequestException as e:
                meta["error"] = f"{type(e).__name__}: {e}"
                if attempt < 2:
                    time.sleep(2)
        if body_path.exists():
            if "error" in meta or meta.get("status") != 200:
                meta["stale"] = True
                stale += 1
                print(f"{name}: fetch failed ({meta.get('error') or meta.get('status')}), kept stale body")
            else:
                ok += 1
                print(f"{name}: captured {meta['bytes']} bytes")
        else:
            missing += 1
            print(f"{name}: NO SNAPSHOT (fetch failed: {meta.get('error') or meta.get('status')}) -> mock serves 500")
        (OUT / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\ndone: {ok} captured, {stale} stale-kept, {missing} missing (out of {ok + stale + missing})")


if __name__ == "__main__":
    main()
