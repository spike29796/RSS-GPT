<script setup>
// 双语阅读页（产物二）。
//
// 数据来自 paper_translate.py 预生成的静态文件 docs/paper/<id>.json ——
// 站点没有后端、浏览器里跑不了模型，所以译文不能「点开时才翻」。
// 这里只读文件：译文已经在文件里，点某段当场显示，零等待。
import { computed, onMounted, ref, watch } from 'vue'
import { formatDate } from '../format.js'
import { safeLink } from '../sanitize.js'
import { ui } from '../store.js'

const props = defineProps({
  id: { type: String, required: true },
  // 从列表点进来时带上条目快照：即便 docs/paper/<id>.json 还没生成，
  // 也能显示标题和原文链接，而不是一个空白页
  entry: { type: Object, default: null },
})
const emit = defineEmits(['back', 'open'])

const META_KEY = 'rss_paper_meta_v1'

// 直链 / 刷新后 props.entry 就没了（hash 路由只带 id），把进入阅读页时的
// 条目快照记在本机，刷新时补回来 —— 否则「译文未生成」那一屏给不出原文链接。
function cachedMeta(id) {
  try {
    const all = JSON.parse(localStorage.getItem(META_KEY) || '{}')
    return all[id] || null
  } catch (e) {
    return null
  }
}

function remember(entry) {
  if (!entry || !entry.link) return
  try {
    const all = JSON.parse(localStorage.getItem(META_KEY) || '{}')
    all[props.id] = {
      link: entry.link,
      title: entry.title || '',
      title_zh: entry.title_zh || '',
      source: entry.source || entry.sourceLabel || '',
      published: entry.published || '',
    }
    // 只留最近 200 条，别把 localStorage 撑爆
    const keys = Object.keys(all)
    if (keys.length > 200) for (const k of keys.slice(0, keys.length - 200)) delete all[k]
    localStorage.setItem(META_KEY, JSON.stringify(all))
  } catch (e) {
    /* 存不下就算了，不影响阅读 */
  }
}

const state = ref('loading') // 'loading' | 'ok' | 'missing'
const paper = ref(null)
const openSet = ref({}) // en 段下标 → 是否展开

const meta = computed(() => {
  if (paper.value) return paper.value
  return props.entry || cachedMeta(props.id) || null
})

const originalLink = computed(() => safeLink((meta.value && meta.value.link) || ''))
const hasCjk = (s) => /[一-鿿]/.test(String(s || ''))

// title_zh 是管线产出的，质量不齐（实测 arxiv 论文里出现过 "BOTTLED" 这种
// 抽风结果）。判据跟 EntryCard 一致：含中文、短、不带句末标点才算译名。
const titleZh = computed(() => {
  const t = String((meta.value && meta.value.title_zh) || '').trim()
  if (!t || !hasCjk(t)) return ''
  if (/[。！？；!?;]\s*$/.test(t)) return ''
  if (t.length > 60) return ''
  return t
})
const titleEn = computed(() => (meta.value && meta.value.title) || '')

// 主标题跟着「译」开关走，另一语言退成副标题 —— 中英文都要露出来
const titlePrimary = computed(() => {
  if (ui.showZh && titleZh.value) return titleZh.value
  return titleEn.value || titleZh.value || '（无标题）'
})
const titleSecondary = computed(() => {
  const zh = titleZh.value
  const en = titleEn.value
  if (!zh) return '' // 没有中文时主标题就是原文，不用副标题
  if (!en || zh === en) return '' // 中文源（标题本身就是中文）别把同一句显示两遍
  return titlePrimary.value === zh ? en : zh
})

const paragraphs = computed(() => (paper.value && paper.value.paragraphs) || [])
const translatedCount = computed(() => paragraphs.value.filter((p) => p.zh).length)

function toggle(i) {
  openSet.value = { ...openSet.value, [i]: !openSet.value[i] }
}

const allOpen = computed(() => paragraphs.value.length > 0 && paragraphs.value.every((_, i) => openSet.value[i]))
function toggleAll() {
  const next = {}
  if (!allOpen.value) paragraphs.value.forEach((_, i) => { next[i] = true })
  openSet.value = next
}

async function load(id) {
  state.value = 'loading'
  paper.value = null
  openSet.value = {}
  if (!id) {
    state.value = 'missing'
    return
  }
  try {
    const resp = await fetch(`${import.meta.env.BASE_URL}paper/${id}.json`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    paper.value = await resp.json()
    state.value = 'ok'
  } catch (e) {
    console.warn(`阅读页：paper/${id}.json 读取失败（${e.message}）`)
    state.value = 'missing'
  }
}

onMounted(() => {
  remember(props.entry)
  load(props.id)
})
watch(() => props.id, (id) => {
  remember(props.entry)
  load(id)
})
</script>

<template>
  <div class="reader">
    <div class="topbar">
      <button class="back" @click="emit('back')">‹ 返回</button>
      <a v-if="originalLink" class="orig" :href="originalLink" target="_blank" rel="noopener">读原文 ↗</a>
    </div>

    <header v-if="meta" class="head">
      <h1 class="title">{{ titlePrimary }}</h1>
      <p v-if="titleSecondary" class="title-alt">{{ titleSecondary }}</p>
      <div class="meta">
        <span v-if="meta && meta.source" class="src">{{ meta.source }}</span>
        <span v-if="meta && meta.published" class="date">{{ formatDate(meta.published) }}</span>
        <span v-if="state === 'ok'" class="cnt">已译 {{ translatedCount }}/{{ paragraphs.length }} 段</span>
      </div>
    </header>

    <p v-if="state === 'loading'" class="hint">加载中…</p>

    <div v-else-if="state === 'missing'" class="empty">
      <p class="empty-title">译文未生成</p>
      <p class="empty-sub">这篇还没跑过 <code>paper_translate.py</code>，站内暂无中文译文。</p>
      <a v-if="originalLink" class="empty-btn" :href="originalLink" target="_blank" rel="noopener">去读原文 ↗</a>
      <p v-else class="empty-sub dim">请从列表页点进来，这样才有原文链接。</p>
    </div>

    <template v-else>
      <div class="toolbar">
        <button class="mini" @click="toggleAll">{{ allOpen ? '全部收起' : '全部展开' }}</button>
        <span class="toolbar-hint">点段落展开中文，再点收起</span>
      </div>
      <article class="paras">
        <section
          v-for="(p, i) in paragraphs"
          :key="i"
          class="para"
          :class="{ open: openSet[i], zhless: !p.zh }"
        >
          <button class="para-en" @click="toggle(i)">
            <span class="para-text">{{ p.en }}</span>
            <span class="para-tag">{{ p.zh ? (openSet[i] ? '收起中文 ▾' : '看中文 ▸') : '无译文' }}</span>
          </button>
          <div v-if="openSet[i] && p.zh" class="para-zh">{{ p.zh }}</div>
        </section>
      </article>
    </template>
  </div>
</template>

<style scoped>
.reader {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 2px 48px;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0 12px;
}
.back {
  border: 1px solid var(--accent);
  color: var(--accent);
  background: none;
  border-radius: 999px;
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
}
.orig {
  margin-left: auto;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text-2);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  text-decoration: none;
}
.orig:hover {
  background: var(--card-hover);
  color: var(--text);
}
.head {
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
  margin-bottom: 4px;
}
.title {
  margin: 0 0 6px;
  font-size: 21px;
  line-height: 1.35;
}
.title-alt {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--dim-2);
}
.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--dim);
}
.meta .src {
  padding: 1px 8px;
  border-radius: 4px;
  background: var(--card-2);
  border: 1px solid var(--border-2);
  color: var(--text-2);
}
.meta .cnt {
  color: var(--accent);
}
.hint {
  color: var(--dim);
  font-size: 14px;
  text-align: center;
  padding: 40px 0;
}
.empty {
  text-align: center;
  padding: 48px 16px;
}
.empty-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 8px;
}
.empty-sub {
  font-size: 13px;
  color: var(--text-2);
  margin: 0 0 18px;
  line-height: 1.7;
}
.empty-sub code {
  background: var(--card-2);
  border: 1px solid var(--border-2);
  border-radius: 4px;
  padding: 1px 6px;
}
.empty-sub.dim {
  color: var(--dim);
}
.empty-btn {
  display: inline-block;
  border: 1px solid var(--accent);
  color: var(--accent);
  border-radius: 999px;
  padding: 8px 22px;
  font-size: 14px;
  text-decoration: none;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0 6px;
}
.mini {
  padding: 5px 12px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--card-2);
  color: var(--text-2);
  font-size: 12px;
  cursor: pointer;
}
.mini:hover {
  background: var(--card-hover);
  color: var(--text);
}
.toolbar-hint {
  font-size: 11.5px;
  color: var(--dim);
}
.paras {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.para {
  border-left: 3px solid transparent;
  border-radius: 6px;
  transition: background 0.15s, border-color 0.15s;
}
.para.open {
  border-left-color: var(--accent);
  background: var(--card-2);
}
/* 整段是点击区 —— 手机上手指点的目标越大越好 */
.para-en {
  display: block;
  width: 100%;
  text-align: left;
  font-family: inherit;
  font-size: 15.5px;
  line-height: 1.7;
  color: var(--text);
  background: none;
  border: none;
  padding: 12px 12px;
  cursor: pointer;
}
.para-en:hover {
  background: var(--card);
}
.para-text {
  display: block;
}
.para-tag {
  display: inline-block;
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--dim);
}
.para.open .para-tag {
  color: var(--accent);
}
.para.zhless .para-tag {
  color: var(--dim);
}
.para-zh {
  padding: 2px 12px 14px;
  font-size: 15.5px;
  line-height: 1.8;
  color: var(--text-2);
  border-top: 1px dashed var(--border);
  margin: 0 12px;
  padding-left: 0;
  padding-right: 0;
}
@media (max-width: 700px) {
  .title {
    font-size: 19px;
  }
  .para-en,
  .para-zh {
    font-size: 16px;
  }
}
</style>
