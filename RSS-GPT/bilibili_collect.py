"""T-025 B站订阅源采集：独属数据格式，零 LLM（不翻译/不摘要/不分类）。

从公共 RSSHub 实例拉 bilibili.ini 里各 uid 的正式投稿视频，独属格式落
<base>/bilibili.jsonl（newest-first，base 取 config.ini [cfg] base），
日志 <base>/bilibili.log。产出随 cron-job 的 `git add docs/` 提交并随 Pages 发布。

契约纪律：
- 不 import main.py（无 __main__ 护栏，import 即跑全管线，T-006 实证）；
  依赖仅 stdlib + feedparser + requests（requirements.txt 已有，零新增）。
- 抓取纪律复刻 fetch_feed（main.py:81-111）：固定浏览器 UA（main.py:87 同款）、
  stream=True 分块读、iter_content 透明解压后累计字节超 feed_max_bytes
  （读 config.ini [cfg]，当前 52428800）即中止该 uid 记警告——V-03 口径。
- 降级：单 uid 抓取/解析失败记日志继续下一个；全部失败也 exit 0；
  bilibili.ini 缺失/解析错误 exit 2（施工错误要红，网络错误不红）。
  失败时既有 bilibili.jsonl 一个字节不动（仅在有新记录时才原子写回）。
"""

import configparser
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INI_PATH = os.path.join(SCRIPT_DIR, 'bilibili.ini')
CONFIG_INI = os.path.join(SCRIPT_DIR, 'config.ini')

# main.py:87 同款固定浏览器 UA
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# 正式投稿判定：仅 www.bilibili.com/video/BVxxxxxxxxxx 放行；
# 动态/直播/合集/充电类链接被此正则挡住（双保险，该路由本身只产正式投稿）
BVID_RE = re.compile(r'^https?://www\.bilibili\.com/video/(BV[0-9A-Za-z]{10})')
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
COVER_RE = re.compile(r'^https://i[0-9]\.hdslb\.com/')


def _strip(value):
    return (value or '').strip().strip('"').strip("'")


def load_bilibili_ini():
    """ini 缺失/解析错误 = 施工错误，exit 2。"""
    cfg = configparser.ConfigParser()
    try:
        with open(INI_PATH, encoding='utf-8') as f:
            cfg.read_file(f)
        base = _strip(cfg.get('bilibili', 'rsshub_base')).rstrip('/')
        uids = [u.strip() for u in _strip(cfg.get('bilibili', 'uids')).split(',') if u.strip()]
        per_max = int(_strip(cfg.get('bilibili', 'per_uid_per_run_max')))
    except Exception as e:
        print(f'bilibili: FATAL bilibili.ini missing/invalid: {e}', file=sys.stderr)
        sys.exit(2)
    if not base or not uids or per_max < 1:
        print('bilibili: FATAL bilibili.ini bad rsshub_base/uids/per_uid_per_run_max',
              file=sys.stderr)
        sys.exit(2)
    return base, uids, per_max


def load_pipeline_cfg():
    """输出目录与 feed_max_bytes 复用 config.ini [cfg]（只读，不改）。"""
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_INI, encoding='utf-8')
    out_base = _strip(cfg.get('cfg', 'base', fallback='docs/')) or 'docs/'
    try:
        feed_max = int(_strip(cfg.get('cfg', 'feed_max_bytes', fallback='')))
    except ValueError:
        feed_max = 50 * 1024 * 1024
    return out_base, feed_max


def fetch_text(url, feed_max_bytes):
    """复刻 fetch_feed（main.py:88-106）抓取纪律。

    iter_content 透明解压 Content-Encoding，计的是解压后字节（V-03 口径）。
    返回 (text, None) 或 (None, 失败原因)。
    """
    try:
        with requests.get(url, headers={'User-Agent': UA}, timeout=30, stream=True) as r:
            if r.status_code != 200:
                return None, f'http {r.status_code}'
            chunks = []
            downloaded = 0
            for chunk in r.iter_content(chunk_size=65536):
                downloaded += len(chunk)
                if downloaded > feed_max_bytes:
                    return None, f'too_large(>{feed_max_bytes})'
                chunks.append(chunk)
            r._content = b''.join(chunks)
            r._content_consumed = True
            return r.text, None
    except requests.RequestException as e:
        return None, f'fetch error: {e}'


def extract_records(feed, uid, skip):
    """从 feed 提取正式投稿记录；不合约的条目记入 skip(reason) 并丢弃。

    数据契约字段缺一不入库：bvid/link/title/cover/up_name/uid/published。
    """
    records = []
    for entry in feed.entries:
        m = BVID_RE.match(getattr(entry, 'link', '') or '')
        if not m:
            skip('非正式投稿链接')
            continue
        bvid = m.group(1)
        im = IMG_RE.search(getattr(entry, 'description', '') or '')
        cover = im.group(1) if im else ''
        if not COVER_RE.match(cover):
            skip('封面缺失或域不符')
            continue
        title = (getattr(entry, 'title', '') or '').strip()
        up_name = (getattr(entry, 'author', '') or '').strip()
        published = (getattr(entry, 'published', '') or '').strip()
        if not title or not up_name or not published:
            skip('契约字段缺失(title/up_name/published)')
            continue
        records.append({
            'bvid': bvid,
            'link': f'https://www.bilibili.com/video/{bvid}',  # 规范化重建，不照抄 feed
            'title': title,          # entry.title 原文，零 LLM
            'cover': cover,          # B站 CDN 直链，不下载转存
            'up_name': up_name,      # entry.author
            'uid': uid,
            'published': published,  # RFC 2822 原样
        })
    return records


def _sort_key(record):
    try:
        return parsedate_to_datetime(record['published']).timestamp()
    except Exception:
        return 0.0


def main():
    rsshub_base, uids, per_max = load_bilibili_ini()
    out_base, feed_max_bytes = load_pipeline_cfg()
    out_dir = os.path.join(SCRIPT_DIR, out_base)
    os.makedirs(out_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, 'bilibili.jsonl')
    log_path = os.path.join(out_dir, 'bilibili.log')

    existing = []
    if os.path.exists(jsonl_path):
        with open(jsonl_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    existing.append(json.loads(line))
    seen = {r['bvid'] for r in existing}

    log_lines = [f'--- run {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")} UTC '
                 f'base={rsshub_base} ---']
    new_records = []
    ok_count = 0

    for uid in uids:
        skips = {}
        text, err = fetch_text(f'{rsshub_base}/bilibili/user/video/{uid}', feed_max_bytes)
        if err is not None:
            log_lines.append(f'uid={uid} FETCH_FAIL {err}')
            continue
        feed = feedparser.parse(text)
        if not feed.entries:
            log_lines.append(f'uid={uid} PARSE_EMPTY bozo={getattr(feed, "bozo", 0)}')
            continue
        ok_count += 1
        added = 0
        for rec in extract_records(feed, uid, lambda r: skips.__setitem__(r, skips.get(r, 0) + 1)):
            if rec['bvid'] in seen:
                skips['bvid 去重'] = skips.get('bvid 去重', 0) + 1
                continue
            if added >= per_max:
                skips['超 per_uid_per_run_max'] = skips.get('超 per_uid_per_run_max', 0) + 1
                continue
            seen.add(rec['bvid'])
            new_records.append(rec)
            added += 1
        skip_str = ','.join(f'{k}x{v}' for k, v in sorted(skips.items())) or 'none'
        log_lines.append(f'uid={uid} new={added} skip={skip_str}')

    # 有新记录才写回：合并后按发布时间倒序（供播放栏合流取前 10），原子替换；
    # 全部失败/零新增时既有 jsonl 一个字节不动。
    if new_records:
        merged = new_records + existing
        merged.sort(key=_sort_key, reverse=True)
        tmp_path = jsonl_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            for rec in merged:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        os.replace(tmp_path, jsonl_path)

    log_lines.append(f'bilibili: ok {ok_count}/{len(uids)}, new {len(new_records)}')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write('\n'.join(log_lines) + '\n')
    print(log_lines[-1])
    # 网络/解析失败不红（exit 0），施工错误已在 load_bilibili_ini exit 2


if __name__ == '__main__':
    main()
