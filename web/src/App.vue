<script setup>
import { computed, onMounted, ref } from 'vue'
import { SOURCES, fetchAllEntries } from './api.js'
import { parseDate, formatDate } from './format.js'
import EntryCard from './components/EntryCard.vue'

const PAGE_SIZE = 50

const entries = ref([])
const errors = ref([])
const loading = ref(true)
const activeSource = ref('all')
const activeCategory = ref('all')
const search = ref('')
const shown = ref(PAGE_SIZE)

onMounted(async () => {
  const { entries: list, errors: errs } = await fetchAllEntries()
  entries.value = list.sort((a, b) => (parseDate(b.published) || 0) - (parseDate(a.published) || 0))
  errors.value = errs
  loading.value = false
})

const lastUpdate = computed(() => {
  const latest = entries.value[0]
  return latest ? formatDate(latest.published) : ''
})

const bySource = computed(() =>
  activeSource.value === 'all'
    ? entries.value
    : entries.value.filter((e) => e.source === activeSource.value),
)

const categories = computed(() => {
  const set = new Set(bySource.value.map((e) => e.category).filter(Boolean))
  return [...set]
})

const filtered = computed(() => {
  const kw = search.value.trim().toLowerCase()
  return bySource.value.filter((e) => {
    if (activeCategory.value !== 'all' && e.category !== activeCategory.value) return false
    if (kw && !(e.title || '').toLowerCase().includes(kw) && !(e.summary || '').toLowerCase().includes(kw)) return false
    return true
  })
})

const visible = computed(() => filtered.value.slice(0, shown.value))

function resetView() {
  shown.value = PAGE_SIZE
}

function selectSource(name) {
  activeSource.value = name
  activeCategory.value = 'all'
  resetView()
}

function selectCategory(name) {
  activeCategory.value = name
  resetView()
}
</script>

<template>
  <div class="page">
    <header class="header">
      <h1>AI 资讯聚合</h1>
      <span v-if="lastUpdate" class="updated">更新于 {{ lastUpdate }}</span>
    </header>

    <nav class="tabs">
      <button :class="{ active: activeSource === 'all' }" @click="selectSource('all')">全部</button>
      <button
        v-for="s in SOURCES"
        :key="s.name"
        :class="{ active: activeSource === s.name }"
        @click="selectSource(s.name)"
      >
        {{ s.label }}
      </button>
    </nav>

    <div class="toolbar">
      <div class="chips">
        <button :class="{ active: activeCategory === 'all' }" @click="selectCategory('all')">全部分类</button>
        <button
          v-for="c in categories"
          :key="c"
          :class="{ active: activeCategory === c }"
          @click="selectCategory(c)"
        >
          {{ c }}
        </button>
      </div>
      <input v-model="search" class="search" type="search" placeholder="搜索标题或摘要…" @input="resetView" />
    </div>

    <main class="list">
      <p v-if="loading" class="hint">加载中…</p>
      <p v-for="e in errors" :key="e" class="hint error">{{ e }}</p>
      <p v-if="!loading && filtered.length === 0" class="hint">没有匹配的条目</p>
      <EntryCard v-for="e in visible" :key="e.link" :entry="e" />
      <button v-if="filtered.length > shown" class="more" @click="shown += PAGE_SIZE">
        加载更多（{{ filtered.length - shown }} 条剩余）
      </button>
    </main>

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
  background: #f3f4f6;
  color: #111827;
  font-family: -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.page {
  max-width: 760px;
  margin: 0 auto;
  padding: 16px 12px 40px;
}
.header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 4px 12px;
}
.header h1 {
  font-size: 22px;
  margin: 0;
}
.updated {
  font-size: 12px;
  color: #9ca3af;
}
.tabs {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding: 4px;
  position: sticky;
  top: 0;
  background: #f3f4f6;
  z-index: 1;
}
.tabs button,
.chips button {
  border: 1px solid #d1d5db;
  background: #fff;
  border-radius: 999px;
  padding: 5px 14px;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}
.tabs button.active {
  background: #111827;
  color: #fff;
  border-color: #111827;
}
.chips button.active {
  background: #4338ca;
  color: #fff;
  border-color: #4338ca;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 8px 4px;
}
.chips {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  flex: 1;
}
.search {
  flex: 1;
  min-width: 160px;
  padding: 6px 12px;
  border: 1px solid #d1d5db;
  border-radius: 999px;
  font-size: 13px;
}
.list {
  padding-top: 8px;
}
.hint {
  color: #9ca3af;
  font-size: 14px;
  text-align: center;
  padding: 24px 0;
}
.hint.error {
  color: #dc2626;
}
.more {
  display: block;
  width: 100%;
  padding: 10px;
  margin: 8px 0 16px;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  background: #fff;
  font-size: 14px;
  cursor: pointer;
}
.footer {
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
  font-size: 12px;
  color: #6b7280;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.footer a {
  color: #4338ca;
}
</style>
