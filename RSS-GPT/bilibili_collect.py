"""T-025 B站订阅源采集：独属数据格式，零 LLM（不翻译/不摘要/不分类）。

数据源 = B站官方公开 API 直采（包工头 2026-08-12 拍板，弃 RSSHub）：
WBI 签名的 x/space/wbi/arc/search 拉 bilibili.ini 各 uid 的正式投稿视频，
独属格式落 <base>/bilibili.jsonl（newest-first，base 取 config.ini [cfg] base），
日志 <base>/bilibili.log。产出随 cron-job 的 `git add docs/` 提交并随 Pages 发布。

契约纪律：
- 不 import main.py（无 __main__ 护栏）；依赖仅 stdlib + requests
  （requirements.txt 已有，零新增；直采 JSON 后 feedparser 不再需要）。
- 抓取纪律沿用 V-03 口径：固定浏览器 UA（main.py:87 同款）、stream=True
  分块读、解压后累计字节超 feed_max_bytes（读 config.ini，当前 52428800）
  即中止该请求记警告——对 JSON 响应同样生效。
- 风控纪律：dm 指纹四件套一个不许少（缺了必 -352）；不带登录 cookie、
  不提频对抗风控；-352 成规模回归 → blocked 报组长升级。
- 降级：单 uid HTTP 非 200 / JSON code != 0 → 记日志继续下一个；全挂
  exit 0；ini 缺失/解析错误 exit 2；零新增时既有 jsonl 一个字节不动。
"""

import configparser
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INI_PATH = os.path.join(SCRIPT_DIR, 'bilibili.ini')
CONFIG_INI = os.path.join(SCRIPT_DIR, 'config.ini')

# main.py:87 同款固定浏览器 UA
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# WBI 签名置换表（工单身契约，组长实测验证）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

# dm 指纹四件套（契约写死的指纹常量，缺了必 -352）
DM_IMG_LIST = '[]'
DM_IMG_STR = 'V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ'
DM_COVER_IMG_STR = ('QU5HTEUgKEludGVsLCBJbnRlbChSKSBVSEQgR3JhcGhpY3Mg'
                    'RGV2aWNlLCBPcGVuR0wgNC41KQ')
DM_IMG_INTER = '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}'

COVER_RE = re.compile(r'^https://i[0-9]\.hdslb\.com/')


def _strip(value):
    return (value or '').strip().strip('"').strip("'")


def load_bilibili_ini():
    """ini 缺失/解析错误 = 施工错误，exit 2。"""
    cfg = configparser.ConfigParser()
    try:
        with open(INI_PATH, encoding='utf-8') as f:
            cfg.read_file(f)
        api_base = _strip(cfg.get('bilibili', 'api_base')).rstrip('/')
        uids = [u.strip() for u in _strip(cfg.get('bilibili', 'uids')).split(',') if u.strip()]
        per_max = int(_strip(cfg.get('bilibili', 'per_uid_per_run_max')))
        interval = float(_strip(cfg.get('bilibili', 'request_interval_sec') or '1'))
    except Exception as e:
        print(f'bilibili: FATAL bilibili.ini missing/invalid: {e}', file=sys.stderr)
        sys.exit(2)
    if not api_base or not uids or per_max < 1 or interval < 0:
        print('bilibili: FATAL bilibili.ini bad api_base/uids/per_uid_per_run_max/'
              'request_interval_sec', file=sys.stderr)
        sys.exit(2)
    return api_base, uids, per_max, interval


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


def fetch_text_stream(session, url, headers, feed_max_bytes):
    """V-03 口径流式抓取：iter_content 透明解压，计解压后字节，超限中止。
    返回 (text, None) 或 (None, 失败原因)。"""
    try:
        with session.get(url, headers=headers, timeout=30, stream=True) as r:
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


def make_session():
    """会话引导（契约）：cookiejar opener，先摸首页收 buvid3/b_nut（失败不致命）。
    trust_env=False——api.bilibili.com 直连不走代理（组长实测口径）。"""
    session = requests.Session()
    session.trust_env = False
    try:
        session.get('https://www.bilibili.com/', headers={'User-Agent': UA}, timeout=15)
    except requests.RequestException:
        pass
    return session


def get_wbi_keys(session, api_base, feed_max_bytes):
    """nav 接口取 img_key/sub_key（未登录 code -101 也照给，已实测）。
    返回 (mixin_key, None) 或 (None, 失败原因)。"""
    text, err = fetch_text_stream(session, f'{api_base}/x/web-interface/nav',
                                  {'User-Agent': UA, 'Referer': 'https://www.bilibili.com/'},
                                  feed_max_bytes)
    if err is not None:
        return None, f'nav {err}'
    try:
        wbi_img = json.loads(text)['data']['wbi_img']
        img_key = wbi_img['img_url'].rsplit('/', 1)[1].split('.')[0]
        sub_key = wbi_img['sub_url'].rsplit('/', 1)[1].split('.')[0]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return None, f'nav parse error: {e}'
    raw = img_key + sub_key
    return ''.join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32], None


def signed_query(params, mixin_key):
    """WBI 签名：加 wts → 按 key 排序 → urlencode → w_rid = md5(query + mixin_key)。
    参数全部参与签名，一个不许少（契约实测口径）。"""
    params = dict(params)
    params['wts'] = int(time.time())
    query = urllib.parse.urlencode(sorted(params.items()))
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return query + '&w_rid=' + w_rid


def fetch_vlist(session, api_base, uid, mixin_key, feed_max_bytes):
    """拉单个 uid 的投稿列表。返回 (vlist, total_count, None) 或 (None, None, 原因)。"""
    params = {
        'mid': uid,
        'ps': '5',
        'pn': '1',
        'order': 'pubdate',
        'platform': 'web',
        'web_location': '1550101',
        'order_avoided': 'true',
        'dm_img_list': DM_IMG_LIST,
        'dm_img_str': DM_IMG_STR,
        'dm_cover_img_str': DM_COVER_IMG_STR,
        'dm_img_inter': DM_IMG_INTER,
    }
    url = f'{api_base}/x/space/wbi/arc/search?{signed_query(params, mixin_key)}'
    headers = {'User-Agent': UA, 'Referer': f'https://space.bilibili.com/{uid}/video'}
    text, err = fetch_text_stream(session, url, headers, feed_max_bytes)
    if err is not None:
        return None, None, err
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        return None, None, f'json parse error: {e}'
    if payload.get('code') != 0:
        return None, None, f'api code {payload.get("code")}'
    data = payload['data']
    return data['list']['vlist'], data['page']['count'], None


def extract_records(vlist, uid, skip):
    """vlist 条目 → 七字段契约；不合约的条目记入 skip(reason) 并丢弃。"""
    records = []
    for v in vlist:
        bvid = (v.get('bvid') or '').strip()
        if not bvid:
            skip('bvid 缺失')
            continue
        if v.get('is_charge_video'):
            skip('充电专属')
            continue
        cover = (v.get('pic') or '').strip()
        if cover.startswith('http://'):
            cover = 'https://' + cover[len('http://'):]  # 协议升级（契约）
        if not COVER_RE.match(cover):
            skip('封面缺失或域不符')
            continue
        title = (v.get('title') or '').strip()
        up_name = (v.get('author') or '').strip()
        created = v.get('created')
        if not title or not up_name or not isinstance(created, (int, float)):
            skip('契约字段缺失(title/up_name/created)')
            continue
        records.append({
            'bvid': bvid,
            'link': f'https://www.bilibili.com/video/{bvid}',  # 规范化重建
            'title': title,               # 原文，零 LLM
            'cover': cover,               # B站 CDN 直链，不下载转存
            'up_name': up_name,
            'uid': uid,
            'published': formatdate(created, usegmt=True),  # unix 秒 → RFC 2822 GMT
        })
    return records


def _sort_key(record):
    try:
        return parsedate_to_datetime(record['published']).timestamp()
    except Exception:
        return 0.0


def main():
    api_base, uids, per_max, interval = load_bilibili_ini()
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
                 f'base={api_base} ---']
    new_records = []
    ok_count = 0

    session = make_session()
    mixin_key, err = get_wbi_keys(session, api_base, feed_max_bytes)
    if err is not None:
        log_lines.append(f'wbi_keys FETCH_FAIL {err}')

    for i, uid in enumerate(uids):
        if mixin_key is None:
            log_lines.append(f'uid={uid} FETCH_FAIL no wbi keys')
        else:
            vlist, total, err = fetch_vlist(session, api_base, uid, mixin_key, feed_max_bytes)
            if err is not None:
                log_lines.append(f'uid={uid} FETCH_FAIL {err}')
            else:
                ok_count += 1
                skips = {}
                added = 0
                for rec in extract_records(vlist, uid,
                                           lambda r: skips.__setitem__(r, skips.get(r, 0) + 1)):
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
                log_lines.append(f'uid={uid} new={added} skip={skip_str} total={total}')
        if i < len(uids) - 1:
            time.sleep(interval)  # 每 uid 请求间隔，防风控（契约）

    # 有新记录才写回：合并后按发布时间全局倒序原子替换；
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
    # 网络/风控失败不红（exit 0），施工错误已在 load_bilibili_ini exit 2


if __name__ == '__main__':
    main()
