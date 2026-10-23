# -*- coding: utf-8 -*-
"""两条线共享的「双 key 轮换 + 打穿退避」。

判据只有一条：连续 10 次模型调用「没有正确返回内容」。
    失败（任一）：请求抛异常（HTTPError / URLError / 超时）、HTTP 非 200、
                  返回内容为空、内容解析不出所需结构
    成功：拿到非空可用的内容 -> 连续计数清零
粒度：每一次模型调用算一次。计数跨批次、跨两条线持久化（状态文件），两条线共用。

动作（大卫 2026-10-23 定）：
    main   连续失败 10 次 -> 切 backup、写回 .env、计数清零、继续跑不等待
    backup 连续失败 10 次 -> 停 90 分钟（5400 秒）-> 醒后切回 main、计数清零
    任何一次成功都清零；成功了就永远不切

为什么要有它：反代那个账号池打穿（整体冷却）时，管线会拿同一把 key 无限撞。
2026-10-23 实测一天撞了 37 万次 502/403。

并发：两条线（run_local.py 主管线 / paper_loop.py 论文线）可能同时跑，所以
「读-改-写」用 msvcrt 文件锁串行化，落盘走临时文件 + os.replace —— 别的进程
读不到半截 JSON。读状态不加锁：写端是原子替换，读到的要么旧的一整份、要么新的一整份。

状态文件（默认 C:\\Users\\86130\\rss_key_state.json）：
    {"active": "main", "consecutive_fail": 0, "last_switch": "...", "last_reason": ""}

对外三个函数：
    current_key()          当前该用的 key（只读，无副作用）
    note(ok, reason='')    记一次模型调用的结果，内部处理计数 / 切 key / 90 分钟退避
    status()               读状态（不存在就初始化一份），给 --status 和排障用

本模块不往外抛异常：状态文件不可用时退化成「读环境变量里的 OPENAI_API_KEY、
不记账」，管线行为与接入前一致。控制台是 GBK，所有打印强制 ASCII。
"""
import contextlib
import io
import json
import os
import shutil
import threading
import time
from datetime import datetime

try:
    import msvcrt
except ImportError:  # 非 Windows：没有文件锁就别记账（退化成老路子）
    msvcrt = None

KEY_MAIN = '33c9f5dc1f0578ac5199282ce65f11fe8ab8'
KEY_BACKUP = 'c33fbe9a85db4a0c6bb93f87a252b931a13f'
KEYS = {'main': KEY_MAIN, 'backup': KEY_BACKUP}

FAIL_LIMIT = 10
# 副 key 也打穿后的等待秒数。验证时用 RSS_KEY_BACKOFF_SECONDS 缩短，
# 生产不设这个变量就是 5400。
BACKOFF_SECONDS = float(os.environ.get('RSS_KEY_BACKOFF_SECONDS', '5400'))

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.environ.get('RSS_KEY_ENV_FILE') or os.path.join(HERE, '.env')
STATE_PATH = os.environ.get('RSS_KEY_STATE') or os.path.join(r'C:\Users\86130',
                                                            'rss_key_state.json')
LOCK_PATH = STATE_PATH + '.lock'
LOCK_TIMEOUT = 60.0

# 同进程内的线程互斥：main.py 的后台回填用线程池，多线程同时记账会抢同一把文件锁。
# threading.Lock 不可重入，所以模块内部绝不在持锁时再调 _locked()。
_IO_LOCK = threading.Lock()
_ENABLED = None


def _log(msg):
    line = '[key_rotator %s] %s' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg)
    print(line.encode('ascii', 'replace').decode('ascii'), flush=True)


def _ascii(text, limit=200):
    return (text or '').encode('ascii', 'replace').decode('ascii')[:limit]


def _now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _enabled():
    """状态文件目录能用、且有文件锁手段，才启用轮换。判断结果缓存。"""
    global _ENABLED
    if _ENABLED is None:
        try:
            folder = os.path.dirname(STATE_PATH) or '.'
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            _ENABLED = msvcrt is not None
            if not _ENABLED:
                _log('no msvcrt on this platform; rotation disabled')
        except Exception as e:
            _log('state dir unusable (%s); rotation disabled' % _ascii(e))
            _ENABLED = False
    return _ENABLED


def _initial_state():
    return {'active': 'main', 'consecutive_fail': 0,
            'last_switch': _now(), 'last_reason': 'init'}


def _read_state():
    """读状态文件；不存在 / 坏了 / 字段不合法都返回 None。不加锁。"""
    try:
        with io.open(STATE_PATH, 'r', encoding='utf-8') as f:
            st = json.load(f)
    except Exception:
        return None
    if not isinstance(st, dict) or st.get('active') not in KEYS:
        return None
    try:
        st['consecutive_fail'] = int(st.get('consecutive_fail') or 0)
    except Exception:
        st['consecutive_fail'] = 0
    if not isinstance(st.get('last_switch'), str):
        st['last_switch'] = ''
    if not isinstance(st.get('last_reason'), str):
        st['last_reason'] = ''
    return {'active': st['active'], 'consecutive_fail': st['consecutive_fail'],
            'last_switch': st['last_switch'], 'last_reason': st['last_reason']}


def _write_state(st):
    """原子落盘：先写 .tmp 再 os.replace，别的进程读不到半截 JSON。"""
    tmp = STATE_PATH + '.tmp'
    data = json.dumps(st, ensure_ascii=False, separators=(', ', ': '))
    with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(data + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)


@contextlib.contextmanager
def _locked():
    """跨进程文件锁（msvcrt.locking 锁 1 字节）。拿不到锁最多等 LOCK_TIMEOUT 秒。"""
    if not _enabled():
        yield False
        return
    with _IO_LOCK:
        handle = io.open(LOCK_PATH, 'a+b')
        try:
            deadline = time.time() + LOCK_TIMEOUT
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.time() > deadline:
                        raise
                    time.sleep(0.05)
            try:
                yield True
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        finally:
            handle.close()


def _load_or_init():
    """读状态；文件还没有就初始化一份 active=main（加锁，只初始化一次）。"""
    if not _enabled():
        return _initial_state()
    st = _read_state()
    if st is not None:
        return st
    with _locked():
        st = _read_state()
        if st is None:
            st = _initial_state()
            _write_state(st)
            _log('state file created: %s (active=main)' % STATE_PATH)
    return st


def _write_env(key):
    """把 .env 的 OPENAI_API_KEY 改成 key。

    read -> 改那一行 -> write，其余行原样保留；改前备份 .env.bak-<日期>
    （同一天已有备份就不覆盖它，另存一份带时刻的，保证留着的确实是改前原件）。
    """
    try:
        with io.open(ENV_PATH, 'rb') as f:
            raw = f.read()
    except OSError as e:
        _log('env read failed (%s)' % _ascii(e))
        return False

    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith('OPENAI_API_KEY='):
            out.append('OPENAI_API_KEY=' + key)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append('OPENAI_API_KEY=' + key)

    backup = ENV_PATH + '.bak-' + time.strftime('%Y%m%d')
    if os.path.exists(backup):
        backup = ENV_PATH + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
    try:
        shutil.copy2(ENV_PATH, backup)
    except OSError as e:
        _log('env backup failed (%s)' % _ascii(e))
        return False

    tmp = ENV_PATH + '.tmp'
    try:
        with io.open(tmp, 'wb') as f:
            if bom:
                f.write(b'\xef\xbb\xbf')
            f.write((newline.join(out) + newline).encode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ENV_PATH)
        _log('env updated: OPENAI_API_KEY=%s... (backup %s)'
             % (key[:6], os.path.basename(backup)))
        return True
    except OSError as e:
        _log('env write failed (%s)' % _ascii(e))
        return False


def current_key():
    """当前该用的 key（只读）。取不到状态就按初始态 main。"""
    if not _enabled():
        return (os.environ.get('OPENAI_API_KEY') or '').strip()
    try:
        st = _load_or_init()
    except Exception as e:
        _log('state read failed (%s); using main key' % _ascii(e))
        return KEY_MAIN
    return KEYS.get(st.get('active'), KEY_MAIN)


def status():
    """状态文件内容（不存在就初始化）。"""
    try:
        return _load_or_init()
    except Exception as e:
        _log('status failed (%s)' % _ascii(e))
        return {}


def note(ok, reason=''):
    """记一次模型调用的结果。

    返回 'ok' / 'counted' / 'switch-backup' / 'backoff-main' / 'disabled' / 'error'。
    副 key 打穿时会**阻塞** 90 分钟（BACKOFF_SECONDS）再返回 —— 调用方不用自己等。
    """
    try:
        return _note(bool(ok), reason)
    except Exception as e:
        _log('note failed (%s: %s)' % (type(e).__name__, _ascii(e)))
        return 'error'


def _note(ok, reason):
    if not _enabled():
        return 'disabled'

    with _locked():
        st = _read_state()
        if st is None:
            st = _initial_state()
            _write_state(st)

        if ok:
            if st['consecutive_fail']:
                _log('OK: consecutive_fail %d -> 0 (key=%s)'
                     % (st['consecutive_fail'], st['active']))
            st['consecutive_fail'] = 0
            _write_state(st)
            return 'ok'

        st['consecutive_fail'] += 1
        n = st['consecutive_fail']
        if n < FAIL_LIMIT:
            _log('FAIL %d/%d key=%s %s' % (n, FAIL_LIMIT, st['active'], _ascii(reason)))
            _write_state(st)
            return 'counted'

        if st['active'] == 'main':
            st['active'] = 'backup'
            st['consecutive_fail'] = 0
            st['last_switch'] = _now()
            st['last_reason'] = ('main hit %d consecutive failures (%s); switched to backup'
                                 % (n, _ascii(reason, 120)))
            _write_state(st)
            written = _write_env(KEY_BACKUP)
            _log('SWITCH main -> backup after %d consecutive failures; env_written=%s'
                 % (n, written))
            return 'switch-backup'

        st['last_reason'] = ('backup hit %d consecutive failures (%s); 90-minute backoff'
                             % (n, _ascii(reason, 120)))
        _write_state(st)
        _log('BACKOFF: backup key exhausted after %d consecutive failures; sleeping %d s'
             % (n, BACKOFF_SECONDS))

    # 90 分钟退避在锁外面睡：睡着的时候别的进程照样要能读写状态。
    time.sleep(BACKOFF_SECONDS)

    with _locked():
        st = _read_state() or _initial_state()
        if st['active'] == 'backup':
            st['active'] = 'main'
            st['consecutive_fail'] = 0
            st['last_switch'] = _now()
            st['last_reason'] = 'backoff %d s done; switched back to main' % BACKOFF_SECONDS
            _write_state(st)
            written = _write_env(KEY_MAIN)
            _log('BACKOFF done: SWITCH backup -> main; env_written=%s' % written)
        else:
            _log('BACKOFF done: another process already switched (active=%s)'
                 % st['active'])
    return 'backoff-main'
