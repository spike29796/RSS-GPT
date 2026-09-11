<script setup>
import { computed } from 'vue'
import { formatDate } from '../format.js'
import { ui } from '../store.js'
import { tagLabel } from '../i18n.js'
import { sanitizeSummary, safeLink } from '../sanitize.js'

const props = defineProps({
  entry: { type: Object, required: true },
})

// The stored summary starts with '<br><br>总结:' (an RSS-facing paragraph
// marker); for the card we strip the leading line breaks and the marker text
// and render a styled 导读 label instead. Summary HTML is LLM output fed by
// external feed content, so it must be sanitized before v-html (T-004 V-01).
const guideText = computed(() => {
  let s = props.entry.summary || ''
  s = s.replace(/^(<br\s*\/?>\s*)+/, '')
  // 2026-09-11：模型偶尔输出重复标记（"总结:总结: 正文"），要循环剥掉
  s = s.replace(/^((总结|Summary)\s*[:：]\s*)+/, '')
  return sanitizeSummary(s.trim())
})
const entryLink = computed(() => safeLink(props.entry.link))
const date = computed(() => formatDate(props.entry.published))

const hasCjk = (s) => /[\u4e00-\u9fff]/.test(String(s || ''))

// 2026-09-11：光"含中文"不够 —— producthunt/simonwillison 的 title_zh
// 是整句中文描述（"xxx是一款……的集成开发环境，旨在……。"），照样蒙混过关，
// 显示到标题位就成了摘要。译名必须"像标题"：短、无句末标点。
const looksLikeTitle = (tz, title) => {
  const s = String(tz || '').trim()
  if (!s || !hasCjk(s)) return false
  if (/[。！？；!?;]\s*$/.test(s)) return false
  if (s.length > Math.max(40, String(title || '').length * 3)) return false
  return true
}

// 原题已是中文时永远显示原题（中文标题不需要"翻译版"）
const title = computed(() => {
  const e = props.entry
  if (!ui.showZh) return e.title
  if (hasCjk(e.title)) return e.title
  if (looksLikeTitle(e.title_zh, e.title)) return e.title_zh
  return e.title
})
const tag = computed(() => tagLabel(props.entry.category, ui.showZh))
</script>

<template>
  <a class="card" :href="entryLink" target="_blank" rel="noopener">
    <span class="tag">{{ tag }}</span>
    <h3 class="title">{{ title }}</h3>
    <span class="date">{{ date }}</span>
    <div v-if="guideText" class="summary"><span class="guide-label">导读</span><span v-html="guideText"></span></div>
  </a>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
  text-decoration: none;
  color: inherit;
  transition: background 0.15s;
}
.card:hover {
  background: var(--card-hover);
}
.tag {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: var(--accent);
}
.title {
  margin: 0;
  font-size: 17px;
  line-height: 1.4;
}
.date {
  font-size: 12px;
  color: var(--dim);
}
.summary {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.6;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  border-top: 1px solid var(--border-2);
  padding-top: 8px;
}
.guide-label {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-contrast);
  background: var(--accent);
  border-radius: 3px;
  padding: 0 5px;
  margin-right: 6px;
  vertical-align: 1px;
}
</style>
