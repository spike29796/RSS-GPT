// 论文阅读三态：没点开 / 点开过 / 读完。
//
// 站点是纯静态托管（GitHub Pages），没有后端，所以三态只能落在浏览器
// localStorage 里 —— 同一浏览器、同一站点（同源）有效，不跨设备。
// key 用 paperId（sha1(link)[:16]，与阅读页 #/read/<id> 同口径），
// 带版本前缀，以后换存储格式只改前缀、老数据不会被误读。
//
// 读写一律 try/catch：隐私模式 / 禁用存储 / 配额满时静默降级 ——
// 三态是锦上添花，读不到就当「没点开」，不许抛错更不许白屏。
import { ref } from 'vue'

const KEY_PREFIX = 'rssgpt:v1:paper:'

export const PAPER_OPENED = 'opened'
export const PAPER_READ = 'read'

function isKnown(state) {
  return state === PAPER_OPENED || state === PAPER_READ
}

// 启动时一次性把本机的三态全捞进内存（之后列表渲染不再逐个读 localStorage）。
function loadAll() {
  const out = {}
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key || !key.startsWith(KEY_PREFIX)) continue
      const v = localStorage.getItem(key)
      if (isKnown(v)) out[key.slice(KEY_PREFIX.length)] = v
    }
  } catch (e) {
    return {}
  }
  return out
}

// id -> 'opened' | 'read'。组件里读它才有响应性：写入后整体替换，卡片自动重渲染。
export const paperStates = ref(loadAll())

export function getPaperState(id) {
  if (!id) return ''
  return paperStates.value[id] || ''
}

function persist(id, state) {
  try {
    if (state) localStorage.setItem(KEY_PREFIX + id, state)
    else localStorage.removeItem(KEY_PREFIX + id)
  } catch (e) {
    /* 存不下就只在内存里生效（隐私模式），不影响阅读 */
  }
}

function commit(id, state) {
  if (state) {
    paperStates.value = { ...paperStates.value, [id]: state }
  } else {
    const next = { ...paperStates.value }
    delete next[id]
    paperStates.value = next
  }
  persist(id, state)
}

// 点开 = 「点开过」。只升不降：已经「读完」的不许被降回「点开过」。
export function markPaperOpened(id) {
  if (!id || getPaperState(id) === PAPER_READ) return
  commit(id, PAPER_OPENED)
}

export function markPaperRead(id) {
  if (!id) return
  commit(id, PAPER_READ)
}

// 取消「读完」→ 退回「点开过」（不是退回「没点开」，那篇毕竟看过）
export function unmarkPaperRead(id) {
  if (!id) return
  commit(id, PAPER_OPENED)
}
