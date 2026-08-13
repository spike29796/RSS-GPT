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
  s = s.replace(/^(总结|Summary)[:：]/, '')
  return sanitizeSummary(s)
})
const entryLink = computed(() => safeLink(props.entry.link))
const date = computed(() => formatDate(props.entry.published))
const title = computed(() => (ui.showZh ? props.entry.title_zh || props.entry.title : props.entry.title))
const tag = computed(() => tagLabel(props.entry.category, ui.showZh))

// 分类底条配色：五个全局分类（RSS-GPT/main.py DEFAULT_CATEGORIES）固定色；
// 开放词表分类用 djb2 哈希确定性取色，同一分类字符串任何会话同色。
const CATEGORY_PALETTE = ['#0f9d63', '#2563eb', '#d97757', '#8b5cf6', '#dc2626']
const CATEGORY_COLORS = {
  '模型发布': CATEGORY_PALETTE[0],
  '行业动态': CATEGORY_PALETTE[1],
  '政策法规': CATEGORY_PALETTE[2],
  '开源项目': CATEGORY_PALETTE[3],
  '产品应用': CATEGORY_PALETTE[4],
}
const tagColor = computed(() => {
  const key = props.entry.category || ''
  if (CATEGORY_COLORS[key]) return CATEGORY_COLORS[key]
  let h = 5381
  for (let i = 0; i < key.length; i++) h = ((h << 5) + h + key.charCodeAt(i)) | 0
  return CATEGORY_PALETTE[Math.abs(h) % CATEGORY_PALETTE.length]
})
</script>

<template>
  <a class="card" :href="entryLink" target="_blank" rel="noopener">
    <span class="tag" :style="{ background: tagColor }">{{ tag }}</span>
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
  break-inside: avoid;
  margin-bottom: 12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
  text-decoration: none;
  color: inherit;
  transition: background 0.15s, transform 0.15s, box-shadow 0.15s;
}
.card:hover {
  background: var(--card-hover);
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
}
.tag {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: #fff;
  border-radius: 4px;
  padding: 2px 8px;
  display: inline-block;
  align-self: flex-start;
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
