<script setup>
import { computed, onMounted, ref } from 'vue'
import Fuse from 'fuse.js'
import { SOURCES, fetchAllEntries, fetchBiliVideos } from './api.js'
import { parseDate, formatDate, isToday } from './format.js'
import { ui, toggleTheme, toggleZh } from './store.js'
import { TAG_ZH, tagLabel } from './i18n.js'
import EntryCard from './components/EntryCard.vue'
import BiliCarousel from './components/BiliCarousel.vue'
import SourceCard from './components/SourceCard.vue'
import BiliDetailItem from './components/BiliDetailItem.vue'
import PlayerOverlay from './components/PlayerOverlay.vue'

const PAGE_SIZE = 50
const CARD_LIST_SIZE = 20

const entries = ref([])
const errors = ref([])
const loading = ref(true)
const view = ref('home') // 'home' | 'list' | 'bili'
const activeSource = ref('all')
const activeCategory = ref('all')
const search = ref('')
const shown = ref(PAGE_SIZE)
// T-026：B站轮播数据。fetch 失败或为空 → 轮播模块整体不渲染（不留空壳）。
const bili = ref([])

onMounted(async () => {
  // bili 与主列表并行（allSettled 口径）：bili 失败不影响主列表。
  const [main, biliResult] = await Promise.allSettled([fetchAllEntries(), fetchBiliVideos()])
  if (main.status === 'fulfilled') {
    const { entries: list, errors: errs } = main.value
    for (const e of list) e.category_zh = TAG_ZH[e.category] || ''
    entries.value = list.sort((a, b) => (parseDate(b.published) || 0) - (parseDate(a.published) || 0))
    errors.value = errs
  } else {
    errors.value = [`主列表加载失败：${main.reason.message}`]
  }
  if (biliResult.status === 'fulfilled') bili.value = biliResult.value
  else console.warn(`bilibili 加载失败：${biliResult.reason.message}`)
  loading.value = false
})

// 轮播播放栏总量：合流时间倒序前 10 条（不足 10 按实际）
const biliTop10 = computed(() =>
  [...bili.value].sort((a, b) => (parseDate(b.published) || 0) - (parseDate(a.published) || 0)).slice(0, 10),
)

// B站详情页全量：时间倒序，数量=实际 bili 数据（T-035）
const biliList = computed(() =>
  [...bili.value].sort((a, b) => (parseDate(b.published) || 0) - (parseDate(a.published) || 0)),
)

// B站详情页裂图兜底记录（与轮播同口径，按 bvid；实际渲染由 BiliDetailItem 局部 err 管理，契约 C）
const biliBroken = ref({})
function biliCoverError(v) {
  biliBroken.value = { ...biliBroken.value, [v.bvid]: true }
}

const lastUpdate = computed(() => (entries.value[0] ? formatDate(entries.value[0].published) : ''))

// Per-source stats for the league cards (with latest-entry preview).
const sourceStats = computed(() =>
  SOURCES.map((s) => {
    const list = entries.value.filter((e) => e.source === s.name)
    return { ...s, total: list.length, latest: list.slice(0, CARD_LIST_SIZE), todayCount: list.filter((e) => isToday(e.published)).length }
  }),
)

// Tag counts scoped to the currently selected source (list view filter).
const bySource = computed(() =>
  activeSource.value === 'all' ? entries.value : entries.value.filter((e) => e.source === activeSource.value),
)

const categories = computed(() => {
  const counts = {}
  for (const e of bySource.value) {
    if (e.category) counts[e.category] = (counts[e.category] || 0) + 1
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count }))
})

const fuse = computed(
  () =>
    new Fuse(bySource.value, {
      keys: ['title', 'title_zh', 'summary', 'category', 'category_zh'],
      threshold: 0.3,
      ignoreLocation: true,
    }),
)

const filtered = computed(() => {
  const kw = search.value.trim()
  let list = bySource.value
  if (kw) list = fuse.value.search(kw).map((r) => r.item)
  if (activeCategory.value !== 'all') list = list.filter((e) => e.category === activeCategory.value)
  return list
})

const visible = computed(() => filtered.value.slice(0, shown.value))

function openList(source = 'all', category = 'all') {
  activeSource.value = source
  activeCategory.value = category
  search.value = ''
  shown.value = PAGE_SIZE
  view.value = 'list'
}

// B站源卡入口（T-035）：B站不是 SOURCES，不重设 activeSource
function openBili() {
  view.value = 'bili'
}

// T-037：B站视频就地播放——playerBvid 非空时挂官方 iframe 遮罩。
// 契约 B2/C2 emit('play', item) 传条目对象，此处抽 item.bvid 字符串给遮罩（白名单校验入口）
const playerBvid = ref(null)
function openPlayer(item) {
  playerBvid.value = item.bvid
}
function closePlayer() {
  playerBvid.value = null
}

function goHome() {
  view.value = 'home'
}

function selectSource(name) {
  activeSource.value = name
  activeCategory.value = 'all'
  shown.value = PAGE_SIZE
}

function selectCategory(name) {
  activeCategory.value = name
  shown.value = PAGE_SIZE
}
// ===== T-038：意图标注 =====
// 判据不是"这条讲什么"，而是"我读完下一步会做什么"
const INTENTS = [
  { id: 'use', label: '能马上用', color: '#46d17a' },
  { id: 'save', label: '该存档', color: '#4d9ef7' },
  { id: 'know', label: '只需知道', color: '#9aa4b2' },
  { id: 'noise', label: '与我无关', color: '#6b7280' },
]
const MARKS_KEY = 'rss_intent_marks_v1'
const marks = ref({})

onMounted(() => {
  try {
    const raw = localStorage.getItem(MARKS_KEY)
    if (raw) marks.value = JSON.parse(raw)
  } catch (e) {
    console.warn('标注读取失败', e)
  }
})

function mark(entry, intent) {
  const cur = marks.value[entry.link]
  const next = { ...marks.value }
  if (cur && cur.intent === intent) {
    delete next[entry.link] // 再点一次 = 取消
  } else {
    next[entry.link] = {
      link: entry.link,
      title: entry.title || '',
      title_zh: entry.title_zh || '',
      source: entry.source || '',
      category: entry.category || '',
      intent,
      ts: new Date().toISOString(),
    }
  }
  marks.value = next
  try {
    localStorage.setItem(MARKS_KEY, JSON.stringify(next))
  } catch (e) {
    console.warn('标注写入失败', e)
  }
}

const markedCount = computed(() => Object.keys(marks.value).length)

const intentStats = computed(() =>
  INTENTS.map((it) => ({
    ...it,
    n: Object.values(marks.value).filter((m) => m.intent === it.id).length,
  })),
)

// 今日更新；今日无更新则退回最近一批（避免空框）
const todayEntries = computed(() => {
  const today = entries.value.filter((e) => isToday(e.published))
  return today.length ? today : entries.value.slice(0, 20)
})
const todayIsFallback = computed(() => !entries.value.some((e) => isToday(e.published)))

// 摘要清洗：jsonl 里存着 HTML 标签（<br>）和重复的"总结:"前缀
// 实测原始值形如 "<br><br>总结:总结: xxx" —— 前缀会重复，必须循环剥
function cleanText(s) {
  if (!s) return ''
  let t = String(s).replace(/<[^>]*>/g, ' ')
  t = t.replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
  for (let i = 0; i < 5; i++) {
    const n = t.replace(/^\s*(总结|摘要)\s*[：:]\s*/, '')
    if (n === t) break
    t = n
  }
  t = t.replace(/\s+/g, ' ').trim()
  // 剥完只剩"总结:"这种残渣 → 视为没有摘要
  return /^(总结|摘要)\s*[：:]?$/.test(t) ? '' : t
}

function exportMarks() {
  const rows = Object.values(marks.value)
  if (!rows.length) {
    alert('还没标注任何条目')
    return
  }
  const body = rows.map((r) => JSON.stringify(r)).join('\n')
  const blob = new Blob([body + '\n'], { type: 'application/x-ndjson' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `intent-marks-${new Date().toISOString().slice(0, 10)}.jsonl`
  a.click()
  URL.revokeObjectURL(a.href)
}

function clearMarks() {
  if (!confirm('清空全部标注？此操作不可撤销')) return
  marks.value = {}
  try {
    localStorage.removeItem(MARKS_KEY)
  } catch (e) {
    console.warn(e)
  }
}
</script>

<template>
  <div class="page">
    <!-- ============================================================
         T-038 新 UI：今日更新大框 + 每条意图标注
         旧 UI 已停用，保留在下方 <div v-if="false"> 内备查
         ============================================================ -->
    <div class="today-box">
      <div class="today-head">
        <div class="today-head-left">
          <h2 class="today-title">今日更新</h2>
          <p class="today-sub">
            <b>{{ todayEntries.length }}</b> 条
            <span v-if="todayIsFallback" class="fallback">（今日无更新，显示最近一批）</span>
            ｜ 已标注 <b>{{ markedCount }}</b> 条
          </p>
        </div>
        <div class="today-actions">
          <button class="mini" :class="{ on: ui.showZh }" title="中英切换" @click="toggleZh">
            {{ ui.showZh ? '中' : 'En' }}
          </button>
          <button class="mini" title="主题" @click="toggleTheme">
            {{ ui.theme === 'dark' ? '☀️' : '🌙' }}
          </button>
          <button class="mini primary" @click="exportMarks">导出标注</button>
          <button class="mini" @click="clearMarks">清空</button>
        </div>
      </div>

      <p v-if="loading" class="hint">加载中…</p>
      <p v-for="e in errors" :key="e" class="hint error">{{ e }}</p>

      <ul class="entry-list">
        <li v-for="e in todayEntries" :key="e.link" class="entry-row">
          <div class="entry-main">
            <a class="entry-title" :href="e.link" target="_blank" rel="noopener">
              {{ ui.showZh ? e.title_zh || e.title : e.title }}
            </a>
            <div class="entry-meta">
              <span class="src">{{ e.source }}</span>
              <span v-if="e.category_zh" class="cat">{{ e.category_zh }}</span>
              <span class="time">{{ formatDate(e.published) }}</span>
            </div>
            <p v-if="cleanText(e.summary)" class="entry-sum">{{ cleanText(e.summary) }}</p>
          </div>
          <div class="intents">
            <button
              v-for="it in INTENTS"
              :key="it.id"
              class="intent-btn"
              :class="{ on: marks[e.link] && marks[e.link].intent === it.id }"
              @click="mark(e, it.id)"
            >
              {{ it.label }}
            </button>
          </div>
        </li>
      </ul>
    </div>

    <div class="stat-bar">
      <span class="stat-label">我的标注</span>
      <span v-for="s in intentStats" :key="s.id" class="stat-item">
        <i class="dot" :style="{ background: s.color }"></i>{{ s.label }} <b>{{ s.n }}</b>
      </span>
      <span v-if="!markedCount" class="stat-empty">还没开始 —— 每条点一个按钮就行</span>
    </div>

    <!-- ↓↓↓ 旧 UI 已停用（v-if="false" = 不渲染，代码保留备查） ↓↓↓ -->
    <div v-if="false" class="legacy-ui">
    <header class="header">
      <h1 @click="goHome">OpenAI News 聚合</h1>
      <span v-if="lastUpdate" class="updated">更新于 {{ lastUpdate }}</span>
      <span class="header-actions">
        <button class="icon-btn" :class="{ on: ui.showZh }" title="翻译标题和标签" @click="toggleZh">译</button>
        <button class="icon-btn" :title="ui.theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'" @click="toggleTheme">
          {{ ui.theme === 'dark' ? '☀️' : '🌙' }}
        </button>
      </span>
    </header>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-for="e in errors" :key="e" class="hint error">{{ e }}</p>

    <!-- 首页：B站轮播（数据为空不渲染） + 赛季（资讯源）卡片（含最新消息小窗） -->
    <template v-if="!loading && view === 'home'">
      <BiliCarousel v-if="biliTop10.length" :items="biliTop10" @play="openPlayer" />

      <section class="section">
        <h2 class="section-title">资讯源 <span class="count">{{ sourceStats.length }}</span></h2>
        <div class="leagues">
          <SourceCard v-for="s in sourceStats" :key="s.name" :s="s" @open="openList" />
          <button v-if="bili.length" class="bili-source-card" @click="openBili">
            <span class="league-letter" style="background: #00a1d6">B</span>
            <span class="league-body">
              <span class="league-name">哔哩哔哩</span>
              <span class="league-total">{{ bili.length }} 条</span>
            </span>
            <span class="chevron">›</span>
          </button>
        </div>
      </section>

    </template>

    <!-- 列表视图：两列卡片 + 右侧标签控制面板 -->
    <template v-if="view === 'list'">
      <div class="list-layout">
        <aside class="panel">
          <button class="home-btn" @click="goHome">‹ 首页</button>
          <input v-model="search" class="search" type="search" placeholder="模糊搜索（中英文都行）…" @input="shown = PAGE_SIZE" />
          <h3 class="panel-title">资讯源</h3>
          <div class="panel-tags">
            <button :class="{ active: activeSource === 'all' }" @click="selectSource('all')">
              <span>全部源</span><span class="n">{{ entries.length }}</span>
            </button>
            <button
              v-for="s in SOURCES"
              :key="s.name"
              :class="{ active: activeSource === s.name }"
              @click="selectSource(s.name)"
            >
              <span><i class="dot" :style="{ background: s.accent }"></i>{{ s.label }}</span>
              <span class="n">{{ sourceStats.find((x) => x.name === s.name)?.total || 0 }}</span>
            </button>
          </div>
          <h3 class="panel-title">标签</h3>
          <div class="panel-tags">
            <button :class="{ active: activeCategory === 'all' }" @click="selectCategory('all')">
              <span>全部</span><span class="n">{{ bySource.length }}</span>
            </button>
            <button
              v-for="c in categories"
              :key="c.name"
              :class="{ active: activeCategory === c.name }"
              @click="selectCategory(c.name)"
            >
              <span>{{ tagLabel(c.name, ui.showZh) }}</span><span class="n">{{ c.count }}</span>
            </button>
          </div>
        </aside>

        <main class="list">
          <p v-if="filtered.length === 0" class="hint">没有匹配的条目</p>
          <EntryCard v-for="e in visible" :key="e.link" :entry="e" />
          <button v-if="filtered.length > shown" class="more" @click="shown += PAGE_SIZE">
            加载更多（{{ filtered.length - shown }} 条剩余）
          </button>
        </main>
      </div>
    </template>

    <!-- B站详情页：标题原文 + 150×100 封面，无导读无翻译 -->
    <template v-if="view === 'bili'">
      <button class="home-btn" @click="goHome">‹ 首页</button>
      <h2 class="section-title">哔哩哔哩 · 精选投稿 <span class="count">{{ biliList.length }}</span></h2>
      <div class="bili-grid">
        <BiliDetailItem v-for="v in biliList" :key="v.bvid" :item="v" @play="openPlayer" />
      </div>
    </template>

    <footer class="footer">
      <span>RSS 订阅：</span>
      <a v-for="s in SOURCES" :key="s.name" :href="`${s.name}.xml`">{{ s.label }}</a>
      <a href="feeds.html">全部源</a>
    </footer>

    <!-- T-037：B站视频就地播放遮罩（fixed，不受布局影响） -->
    <PlayerOverlay v-if="playerBvid" :bvid="playerBvid" @close="closePlayer" />
    </div>
    <!-- ↑↑↑ 旧 UI 停用区结束 ↑↑↑ -->
  </div>
</template>

<style>
:root {
  --bg: #1a2230;
  --card: #242e40;
  --card-hover: #2b3850;
  --card-2: #1f2839;
  --border: #33405a;
  --border-2: #2c3850;
  --text: #d7dee9;
  --text-2: #9fb0c8;
  --dim: #7c8798;
  --dim-2: #8fa0b8;
  --accent: #7fd4a8;
  --accent-contrast: #141a26;
  --error: #ff7a7a;
}
[data-theme='light'] {
  --bg: #f6f7f9;
  --card: #ffffff;
  --card-hover: #f0f2f5;
  --card-2: #f3f4f6;
  --border: #e2e6ec;
  --border-2: #e5e7eb;
  --text: #1a2230;
  --text-2: #4b5563;
  --dim: #6b7280;
  --dim-2: #9ca3af;
  --accent: #0f9d63;
  --accent-contrast: #ffffff;
  --error: #dc2626;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  transition: background 0.2s, color 0.2s;
}
.page {
  max-width: 1600px;
  margin: 0 auto;
  padding: 20px 24px 48px;
}
.header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 4px 16px;
}
.header h1 {
  font-size: 22px;
  margin: 0;
  cursor: pointer;
}
.updated {
  font-size: 12px;
  color: var(--dim);
}
.header-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.icon-btn.on {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-contrast);
  font-weight: 700;
}

.section {
  margin-bottom: 28px;
}
.section-title {
  font-size: 13px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--dim-2);
  border-bottom: 1px solid var(--border);
  padding: 0 4px 8px;
}
.count {
  color: var(--accent);
  margin-left: 4px;
}

.leagues {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 24px;
  margin-top: 12px;
}
@media (max-width: 700px) {
  .leagues {
    grid-template-columns: 1fr;
  }
}

/* T-035 B站源卡（.leagues grid 内，仿 T-031 SourceCard 卡头视觉；内部类名带前缀限定，不碰 SourceCard scoped） */
.bili-source-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  font-size: 14px;
  color: inherit;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 14px;
}
.bili-source-card:hover {
  background: var(--card-hover);
}
.bili-source-card .league-letter {
  width: 30px;
  height: 30px;
  border-radius: 4px;
  background: var(--dim);
  color: var(--accent-contrast);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.bili-source-card .league-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.bili-source-card .league-name {
  font-weight: 600;
}
.bili-source-card .league-total {
  font-size: 12px;
  color: var(--dim);
}
.bili-source-card .chevron {
  margin-left: auto;
  color: var(--dim);
  font-size: 18px;
}

/* T-035 B站详情页网格 */
.bili-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
@media (max-width: 699px) {
  .bili-grid {
    grid-template-columns: 1fr;
  }
  .bili-source-card {
    width: 100%;
  }
}

/* 列表视图：左卡片两列 + 右侧控制面板 */
.list-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  align-items: start;
}
@media (min-width: 1000px) {
  .list-layout {
    grid-template-columns: minmax(0, 1fr) 280px;
  }
  .list-layout > .panel {
    grid-column: 2;
    grid-row: 1;
    position: sticky;
    top: 16px;
    max-height: calc(100vh - 32px);
    overflow-y: auto;
  }
  .list-layout > .list {
    grid-column: 1;
    grid-row: 1;
  }
}
.panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.home-btn {
  border: 1px solid var(--accent);
  color: var(--accent);
  background: none;
  border-radius: 999px;
  padding: 5px 14px;
  font-size: 13px;
  cursor: pointer;
  align-self: flex-start;
}
.search {
  width: 100%;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--card-2);
  color: var(--text);
  font-size: 13px;
}
.search::placeholder {
  color: var(--dim);
}
.panel-title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--dim-2);
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
}
.panel-tags {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.panel-tags button {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  border: 1px solid var(--border-2);
  background: var(--card-2);
  color: var(--text);
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.panel-tags button:hover {
  background: var(--card-hover);
}
.panel-tags button .n {
  color: var(--dim);
  font-size: 11px;
}
.panel-tags button.active {
  background: var(--accent);
  color: var(--accent-contrast);
  border-color: var(--accent);
}
.panel-tags button.active .n {
  color: var(--accent-contrast);
}
.panel-tags .dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}
@media (min-width: 700px) {
  .list {
    grid-template-columns: repeat(2, 1fr);
  }
}
.list > .hint,
.list > .more {
  grid-column: 1 / -1;
}
.hint {
  color: var(--dim);
  font-size: 14px;
  text-align: center;
  padding: 24px 0;
}
.hint.error {
  color: var(--error);
}
.more {
  display: block;
  width: 100%;
  padding: 10px;
  margin: 8px 0 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
  color: var(--text);
  font-size: 14px;
  cursor: pointer;
}
.footer {
  border-top: 1px solid var(--border);
  margin-top: 24px;
  padding-top: 12px;
  font-size: 12px;
  color: var(--dim);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.footer a {
  color: var(--accent);
}
/* ============================================================
   T-038：今日更新大框 + 意图标注（新 UI）
   ============================================================ */
.legacy-ui { display: none; }

.today-box {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px 8px;
  margin: 20px 0 14px;
}

.today-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-2);
}
.today-title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
}
.today-sub {
  margin: 0;
  font-size: 12.5px;
  color: var(--dim);
}
.today-sub b { color: var(--accent); }
.today-sub .fallback { color: var(--dim-2); }

.today-actions { display: flex; gap: 7px; flex-wrap: wrap; }
.mini {
  padding: 5px 11px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--card-2);
  color: var(--text-2);
  font-size: 12px;
  cursor: pointer;
  transition: all .12s;
}
.mini:hover { background: var(--card-hover); color: var(--text); }
.mini.on { background: var(--accent); border-color: var(--accent); color: var(--accent-contrast); }
.mini.primary { border-color: var(--accent); color: var(--accent); }
.mini.primary:hover { background: var(--accent); color: var(--accent-contrast); }

.entry-list { list-style: none; margin: 0; padding: 0; }

.entry-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 0;
  border-bottom: 1px solid var(--border-2);
}
.entry-row:last-child { border-bottom: none; }

.entry-main { flex: 1 1 auto; min-width: 0; }
.entry-title {
  display: block;
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--text);
  text-decoration: none;
  margin-bottom: 5px;
}
.entry-title:hover { color: var(--accent); }
.entry-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 11.5px;
  color: var(--dim);
}
.entry-meta .src {
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--card-2);
  border: 1px solid var(--border-2);
}
.entry-meta .cat { color: var(--accent); }
.entry-sum {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--text-2);
}

.intents {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: repeat(2, auto);
  gap: 5px;
}
.intent-btn {
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--dim-2);
  font-size: 11.5px;
  white-space: nowrap;
  cursor: pointer;
  transition: all .12s;
}
.intent-btn:hover { border-color: var(--text-2); color: var(--text); }
.intents .intent-btn:nth-child(1).on { background: #46d17a; border-color: #46d17a; color: #0b1220; font-weight: 600; }
.intents .intent-btn:nth-child(2).on { background: #4d9ef7; border-color: #4d9ef7; color: #0b1220; font-weight: 600; }
.intents .intent-btn:nth-child(3).on { background: #9aa4b2; border-color: #9aa4b2; color: #0b1220; font-weight: 600; }
.intents .intent-btn:nth-child(4).on { background: #6b7280; border-color: #6b7280; color: #fff; font-weight: 600; }

.stat-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 12px 18px;
  margin-bottom: 24px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 12.5px;
  color: var(--dim-2);
}
.stat-label { color: var(--dim); }
.stat-item { display: inline-flex; align-items: center; gap: 5px; }
.stat-item b { color: var(--text); }
.stat-item .dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.stat-empty { color: var(--dim); font-style: italic; }

@media (max-width: 720px) {
  .entry-row { flex-direction: column; gap: 9px; }
  .intents { grid-template-columns: repeat(4, 1fr); width: 100%; }
}
</style>
