<script setup>
// 双语阅读页（产物二）。
//
// 数据来自 paper_translate.py 预生成的静态文件 docs/paper/<id>.json ——
// 站点没有后端、浏览器里跑不了模型，所以译文不能「点开时才翻」。
// 这里只读文件：译文已经在文件里，点某段当场显示，零等待。
import { computed, onMounted, ref, watch } from 'vue'
import { formatDate } from '../format.js'
import { getPaperState, markPaperRead, unmarkPaperRead } from '../paperReadState.js'
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

// 中文默认显示。穿插版式的意义就是「读到哪里中文就在哪里」，
// 默认藏起来等于把上一版的点击展开又做了一遍。
const showZh = ref(true)

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

// 句级对照的段落 —— 后端切块 + 按索引配对，en 永远是原文，不会贴错
const hasSents = (p) => Array.isArray(p.sents) && p.sents.length > 0

async function load(id) {
  state.value = 'loading'
  paper.value = null
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

// 2026-10-10：第三态「读完」。正文末尾一个按钮，点了记读完；
// 再点一下取消 —— 退回「点开过」，不是退回「没点开」（那篇毕竟看过）。
// 存在浏览器本地（paperReadState.js），刷新/关掉再开仍在。
const isRead = computed(() => !!props.id && getPaperState(props.id) === 'read')

function toggleRead() {
  if (!props.id) return
  if (isRead.value) unmarkPaperRead(props.id)
  else markPaperRead(props.id)
}
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
        <button class="mini" @click="showZh = !showZh">{{ showZh ? '隐藏中文' : '显示中文' }}</button>
      </div>
      <article class="paras">
        <section
          v-for="(p, i) in paragraphs"
          :key="i"
          class="para"
          :class="{ zhless: !p.zh }"
        >
          <!-- 逐句穿插：英文句块后面紧跟它自己的中文，读到哪里中文在哪里 -->
          <!-- 同一组（英+中）共用同一色号，下划线颜色一一对应，逐组轮换 -->
          <div v-if="hasSents(p)" class="para-inline">
            <template v-for="(s, j) in p.sents" :key="j">
              <span class="sent-en" :class="'pair-' + (j % 6)">{{ s.en }}</span>
              <span v-if="showZh" class="sent-zh" :class="'pair-' + (j % 6)">{{ s.zh }}</span>
            </template>
          </div>
          <!-- 没有句级数据（短文/单句段/句级失败回退）：整段英文 + 整段中文 -->
          <template v-else>
            <p class="para-flat">{{ p.en }}</p>
            <p v-if="showZh && p.zh" class="para-zh">{{ p.zh }}</p>
          </template>
        </section>
      </article>
    </template>

    <!-- 2026-10-10：正文末尾的第三态 —— 点了记「读完」，再点取消回「点开过」。
         译文没生成（missing）时也留着，那篇同样是「读过了」。 -->
    <div v-if="state !== 'loading' && id" class="read-mark">
      <button class="done-btn" :class="{ done: isRead }" type="button" @click="toggleRead">
        {{ isRead ? '已标记读完' : '读完了' }}
      </button>
      <p class="done-hint">
        {{ isRead ? '点一下可取消「读完」标记' : '点一下标记为读完（只记在这台浏览器）' }}
      </p>
    </div>
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
  gap: 8px;
}
.para {
  border-radius: 6px;
}
/* 逐句穿插：英文句块 + 紧跟的中文句块，一组一组往下走 */
.para-inline {
  padding: 12px 12px 2px;
}
/* 配对色号：同一组英文句和它的中文句用同一色号，逐组轮换，相邻不同色 */
.pair-0 { --pair: var(--pair-0); }
.pair-1 { --pair: var(--pair-1); }
.pair-2 { --pair: var(--pair-2); }
.pair-3 { --pair: var(--pair-3); }
.pair-4 { --pair: var(--pair-4); }
.pair-5 { --pair: var(--pair-5); }
.sent-en,
.sent-zh {
  text-decoration-line: underline;
  text-decoration-color: var(--pair);
  text-decoration-thickness: 2px;
  text-underline-offset: 4px;
}
.sent-en {
  display: block;
  /* 衬线：长文阅读最省眼，和论文原文的排印气质一致 */
  font-family: "Iowan Old Style", "Charter", "Bitstream Charter", Georgia, "Sitka Text", Cambria, "Noto Serif", serif;
  font-size: 16px;
  line-height: 1.75;
  color: var(--en);
  letter-spacing: 0.005em;
}
.sent-zh {
  display: block;
  /* 无衬线：中文在屏上无衬线更清楚，和英文形成字体对比 */
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.8;
  color: var(--zh);
  margin: 2px 0 10px;
  padding-left: 10px;
  border-left: 2px solid var(--zh-rule);
}
/* 无句级数据时退回整段版式 */
.para-flat {
  margin: 0;
  padding: 12px 12px 0;
  font-family: "Iowan Old Style", "Charter", "Bitstream Charter", Georgia, "Sitka Text", Cambria, "Noto Serif", serif;
  font-size: 16px;
  line-height: 1.75;
  color: var(--en);
  letter-spacing: 0.005em;
}
.para-zh {
  margin: 6px 12px 12px;
  padding: 8px 0 0 10px;
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.85;
  color: var(--zh);
  border-top: 1px dashed var(--border);
  border-left: 2px solid var(--zh-rule);
}
/* 2026-10-10：正文末尾的「读完了」按钮。
   居中、定宽 —— 窄屏下 App 的两个悬浮球贴在屏幕下角，
   按钮留在中间就不会被球压住。 */
.read-mark {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  margin-top: 22px;
  padding: 26px 0 0;
  border-top: 1px solid var(--border);
}
.done-btn {
  display: block;
  width: fit-content;
  min-width: 180px;
  max-width: 100%;
  padding: 10px 24px;
  border-radius: 999px;
  border: 1px solid var(--accent);
  background: none;
  color: var(--accent);
  font-family: inherit;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.done-btn:hover {
  background: var(--card-hover);
}
.done-btn.done {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-contrast);
  font-weight: 600;
}
.done-hint {
  margin: 0;
  font-size: 11.5px;
  color: var(--dim);
  text-align: center;
}
@media (max-width: 700px) {
  .title {
    font-size: 19px;
  }
  .sent-en,
  .para-flat {
    font-size: 16.5px;
  }
  .sent-zh,
  .para-zh {
    font-size: 15.5px;
  }
  /* 悬浮球在窄屏贴在屏幕下角，正文末尾多留点空，别让最后一段压在球下 */
  .reader {
    padding-bottom: 72px;
  }
}
</style>
