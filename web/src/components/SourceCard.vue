<script setup>
import { ui } from '../store.js'
import { formatShort, isToday } from '../format.js'
import { safeLink } from '../sanitize.js'

defineProps({
  s: { type: Object, required: true },
})

defineEmits(['open'])

function title(e) {
  return ui.showZh ? e.title_zh || e.title : e.title
}
</script>

<template>
  <div class="league-card" :style="{ borderLeftColor: s.accent }">
    <button class="league-head" @click="$emit('open', s.name)">
      <span class="league-letter" :style="{ background: s.accent }">{{ s.league }}</span>
      <span class="league-body">
        <span class="league-name">{{ s.label }}</span>
        <span class="league-total">{{ s.total }} 条</span>
      </span>
      <span class="today-badge" :class="{ zero: s.todayCount === 0 }">
        {{ s.todayCount > 0 ? `今天 +${s.todayCount}` : '今天无新消息' }}
      </span>
      <span class="chevron">›</span>
    </button>
    <div class="preview sc-scroll">
      <a
        v-for="e in s.latest"
        :key="e.link"
        class="preview-item"
        :href="safeLink(e.link)"
        target="_blank"
        rel="noopener"
      >
        <span class="preview-date">
          <em v-if="isToday(e.published)" class="new-dot">NEW</em>{{ formatShort(e.published) }}
        </span>
        <span class="preview-title">{{ title(e) }}</span>
      </a>
    </div>
  </div>
</template>

<style scoped>
.league-card {
  display: flex;
  flex-direction: column;
  height: 500px;
  background: var(--card);
  border: 1px solid var(--border);
  border-left: 4px solid var(--dim);
  border-radius: 12px;
  overflow: hidden;
}
.league-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  background: none;
  border: none;
  padding: 14px 16px;
  color: inherit;
  cursor: pointer;
  text-align: left;
  font-size: 14px;
  transition: background 0.15s;
  flex-shrink: 0;
}
.league-head:hover {
  background: var(--card-hover);
}
.league-letter {
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
  color: var(--dim);
}
.today-badge {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-contrast);
  background: var(--accent);
  border-radius: 999px;
  padding: 3px 10px;
}
.today-badge.zero {
  background: none;
  border: 1px solid var(--border);
  color: var(--dim);
  font-weight: 400;
}
.chevron {
  color: var(--dim);
  font-size: 18px;
}
.preview {
  border-top: 1px solid var(--border);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sc-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-width: none;
}
.sc-scroll::-webkit-scrollbar {
  display: none;
}
.preview-item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 7px 8px;
  border-radius: 4px;
  text-decoration: none;
  color: inherit;
  line-height: 1.5;
}
.preview-item:hover {
  background: var(--card-hover);
}
.preview-date {
  flex-shrink: 0;
  width: 108px;
  font-size: 11px;
  color: var(--dim);
  font-variant-numeric: tabular-nums;
}
.new-dot {
  display: inline-block;
  font-style: normal;
  font-size: 10px;
  font-weight: 700;
  color: var(--accent-contrast);
  background: var(--accent);
  border-radius: 3px;
  padding: 0 4px;
  margin-right: 5px;
}
.preview-title {
  color: var(--text);
  font-size: 13px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
