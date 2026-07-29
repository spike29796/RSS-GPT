<script setup>
import { computed, onMounted, ref } from 'vue'
import { SOURCES, fetchAllEntries } from './api.js'
import { parseDate, formatDate } from './format.js'
import EntryCard from './components/EntryCard.vue'

const PAGE_SIZE = 50

const entries = ref([])
const errors = ref([])
const loading = ref(true)
const view = ref('home') // 'home' | 'list'
const activeCategory = ref('all')
const search = ref('')
const shown = ref(PAGE_SIZE)

onMounted(async () => {
  const { entries: list, errors: errs } = await fetchAllEntries()
  entries.value = list.sort((a, b) => (parseDate(b.published) || 0) - (parseDate(a.published) || 0))
  errors.value = errs
  loading.value = false
})

const lastUpdate = computed(() => (entries.value[0] ? formatDate(entries.value[0].published) : ''))

// Per-source stats for the league cards and the top-classes grid.
const sourceStats = computed(() =>
  SOURCES.map((s) => {
    const list = entries.value.filter((e) => e.source === s.name)
    const counts = {}
    for (const e of list) {
      if (e.category) counts[e.category] = (counts[e.category] || 0) + 1
    }
    const top = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([category, count]) => ({ category, count, pct: list.length ? Math.round((count / list.length) * 100) : 0 }))
    return { ...s, total: list.length, top }
  }),
)

// Official OpenAI News tags with counts, most-used first (list view filter).
const categories = computed(() => {
  const counts = {}
  for (const e of entries.value) {
    if (e.category) counts[e.category] = (counts[e.category] || 0) + 1
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count }))
})

const filtered = computed(() => {
  const kw = search.value.trim().toLowerCase()
  return entries.value.filter((e) => {
    if (activeCategory.value !== 'all' && e.category !== activeCategory.value) return false
    if (kw && !(e.title || '').toLowerCase().includes(kw) && !(e.summary || '').toLowerCase().includes(kw)) return false
    return true
  })
})

const visible = computed(() => filtered.value.slice(0, shown.value))

function openList(category = 'all') {
  activeCategory.value = category
  search.value = ''
  shown.value = PAGE_SIZE
  view.value = 'list'
}

function goHome() {
  view.value = 'home'
}

function selectCategory(name) {
  activeCategory.value = name
  shown.value = PAGE_SIZE
}
</script>

<template>
  <div class="page">
    <header class="header">
      <h1 @click="goHome">OpenAI News 聚合</h1>
      <span v-if="lastUpdate" class="updated">更新于 {{ lastUpdate }}</span>
    </header>

    <p v-if="loading" class="hint">加载中…</p>
    <p v-for="e in errors" :key="e" class="hint error">{{ e }}</p>

    <!-- 首页：赛季（资讯源）卡片 + 热门流派（官方标签） -->
    <template v-if="!loading && view === 'home'">
      <section class="section">
        <h2 class="section-title">资讯源 <span class="count">{{ sourceStats.length }}</span></h2>
        <div class="leagues">
          <button
            v-for="s in sourceStats"
            :key="s.name"
            class="league-card"
            :style="{ borderLeftColor: s.accent }"
            @click="openList()"
          >
            <span class="league-letter" :style="{ background: s.accent }">{{ s.league }}</span>
            <span class="league-body">
              <span class="league-name">{{ s.label }}</span>
              <span class="league-total">{{ s.total }} 条</span>
            </span>
            <span class="chevron">›</span>
          </button>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">热门分类</h2>
        <div class="classes">
          <div v-for="s in sourceStats" :key="s.name" class="class-col">
            <div class="class-head">
              <span class="class-source" :style="{ color: s.accent }">{{ s.label }}</span>
              <button class="see-all" @click="openList()">查看全部 ›</button>
            </div>
            <button
              v-for="t in s.top"
              :key="t.category"
              class="class-row"
              @click="openList(t.category)"
            >
              <span class="class-name">{{ t.category }}</span>
              <span class="class-pct" :style="{ color: s.accent }">{{ t.count }} 条 · {{ t.pct }}%</span>
            </button>
            <p v-if="s.top.length === 0" class="class-empty">暂无数据</p>
          </div>
        </div>
      </section>
    </template>

    <!-- 列表视图：官方标签筛选 + 搜索 + 卡片 -->
    <template v-if="view === 'list'">
      <div class="toolbar">
        <button class="home-btn" @click="goHome">‹ 首页</button>
        <div class="chips">
          <button :class="{ active: activeCategory === 'all' }" @click="selectCategory('all')">
            全部 <span class="n">{{ entries.length }}</span>
          </button>
          <button
            v-for="c in categories"
            :key="c.name"
            :class="{ active: activeCategory === c.name }"
            @click="selectCategory(c.name)"
          >
            {{ c.name }} <span class="n">{{ c.count }}</span>
          </button>
        </div>
        <input v-model="search" class="search" type="search" placeholder="搜索标题或导读…" @input="shown = PAGE_SIZE" />
      </div>

      <main class="list">
        <p v-if="filtered.length === 0" class="hint">没有匹配的条目</p>
        <EntryCard v-for="e in visible" :key="e.link" :entry="e" />
        <button v-if="filtered.length > shown" class="more" @click="shown += PAGE_SIZE">
          加载更多（{{ filtered.length - shown }} 条剩余）
        </button>
      </main>
    </template>

    <footer class="footer">
      <span>RSS 订阅：</span>
      <a v-for="s in SOURCES" :key="s.name" :href="`${s.name}.xml`">{{ s.label }}</a>
      <a href="feeds.html">全部源</a>
    </footer>
  </div>
</template>

<style>
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: #1a2230;
  color: #d7dee9;
  font-family: -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
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
  color: #7c8798;
}

.section {
  margin-bottom: 28px;
}
.section-title {
  font-size: 13px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #8fa0b8;
  border-bottom: 1px solid #33405a;
  padding: 0 4px 8px;
}
.count {
  color: #7fd4a8;
  margin-left: 4px;
}

.leagues {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.league-card {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #242e40;
  border: 1px solid #33405a;
  border-left: 4px solid #7c8798;
  border-radius: 6px;
  padding: 14px 16px;
  color: inherit;
  cursor: pointer;
  text-align: left;
  font-size: 14px;
  transition: background 0.15s;
}
.league-card:hover {
  background: #2b3850;
}
.league-letter {
  width: 30px;
  height: 30px;
  border-radius: 4px;
  background: #7c8798;
  color: #141a26;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.league-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.league-name {
  font-weight: 600;
}
.league-total {
  font-size: 12px;
  color: #7c8798;
}
.chevron {
  margin-left: auto;
  color: #7c8798;
  font-size: 18px;
}

.classes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.class-col {
  background: #242e40;
  border: 1px solid #33405a;
  border-radius: 6px;
  padding: 12px 14px;
}
.class-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.class-source {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.see-all {
  background: none;
  border: none;
  color: #7fd4a8;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}
.class-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  background: #1f2839;
  border: 1px solid #2c3850;
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 6px;
  color: inherit;
  font-size: 13px;
  cursor: pointer;
}
.class-row:hover {
  background: #28334a;
}
.class-pct {
  font-size: 12px;
}
.class-empty {
  color: #7c8798;
  font-size: 12px;
  margin: 4px 0;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 8px 4px;
  position: sticky;
  top: 0;
  background: #1a2230;
  z-index: 1;
}
.home-btn {
  border: 1px solid #7fd4a8;
  color: #7fd4a8;
  background: #242e40;
  border-radius: 999px;
  padding: 5px 14px;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}
.chips {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  flex: 1;
  padding-bottom: 2px;
}
.chips button {
  border: 1px solid #33405a;
  background: #242e40;
  color: #d7dee9;
  border-radius: 999px;
  padding: 5px 14px;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}
.chips button .n {
  color: #7c8798;
  font-size: 11px;
  margin-left: 2px;
}
.chips button.active {
  background: #7fd4a8;
  color: #141a26;
  border-color: #7fd4a8;
}
.chips button.active .n {
  color: #141a26;
}
.search {
  flex: 0 1 260px;
  min-width: 160px;
  padding: 6px 12px;
  border: 1px solid #33405a;
  border-radius: 999px;
  background: #242e40;
  color: #d7dee9;
  font-size: 13px;
}
.search::placeholder {
  color: #7c8798;
}
.list {
  padding-top: 8px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  align-items: start;
}
@media (min-width: 900px) {
  .list {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (min-width: 1400px) {
  .list {
    grid-template-columns: repeat(3, 1fr);
  }
}
.list > .hint,
.list > .more {
  grid-column: 1 / -1;
}
.hint {
  color: #7c8798;
  font-size: 14px;
  text-align: center;
  padding: 24px 0;
}
.hint.error {
  color: #ff7a7a;
}
.more {
  display: block;
  width: 100%;
  padding: 10px;
  margin: 8px 0 16px;
  border: 1px solid #33405a;
  border-radius: 10px;
  background: #242e40;
  color: #d7dee9;
  font-size: 14px;
  cursor: pointer;
}
.footer {
  border-top: 1px solid #33405a;
  margin-top: 24px;
  padding-top: 12px;
  font-size: 12px;
  color: #7c8798;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.footer a {
  color: #7fd4a8;
}
</style>
