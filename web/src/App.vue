<script setup>
import { computed, onMounted, ref } from 'vue'
import { SOURCES, fetchAllEntries } from './api.js'
import { parseDate, formatDate } from './format.js'
import EntryCard from './components/EntryCard.vue'

const PAGE_SIZE = 50

const entries = ref([])
const errors = ref([])
const loading = ref(true)
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

// Official OpenAI News tags with counts, most-used first.
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

function selectCategory(name) {
  activeCategory.value = name
  shown.value = PAGE_SIZE
}
</script>

<template>
  <div class="page">
    <header class="header">
      <h1>OpenAI News</h1>
      <span v-if="lastUpdate" class="updated">更新于 {{ lastUpdate }}</span>
    </header>

    <div class="toolbar">
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
}
.updated {
  font-size: 12px;
  color: #7c8798;
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
