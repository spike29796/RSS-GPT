<script setup>
// YouTube 条目卡：版式照 BiliDetailItem（封面 + 标题 + 摘要 + 频道），
// 差别只有两处 —— 摘要长（200~300 字）所以默认折 3 行可展开；没有时长/播放量
// （频道 RSS 不提供），角标位置改成「▶ 站内播放」。
import { computed, ref } from 'vue'

const props = defineProps({
  item: { type: Object, required: true },
})
const emit = defineEmits(['play'])

const err = ref(false)
const expanded = ref(false)

// 后端写进 summary 的是 "<br><br>总结:正文" 这个格式，卡片上只要正文。
const summary = computed(() => {
  const raw = String(props.item.summary || '')
  return raw
    .replace(/^\s*(<br\s*\/?>\s*)*总结[:：]\s*/i, '')
    .replace(/<br\s*\/?>/gi, ' ')
    .trim()
})
const long = computed(() => summary.value.length > 90)

const dateText = computed(() => {
  const raw = props.item.published || props.item.updated
  if (!raw) return ''
  const d = new Date(raw)
  if (isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
})

const channel = computed(() => props.item.author || props.item.uploader || '')
</script>

<template>
  <a class="yt-item" :href="item.link" @click.prevent="emit('play', item)">
    <span class="yt-thumb">
      <img
        v-if="!err && item.cover"
        :src="item.cover"
        :alt="item.title"
        referrerpolicy="no-referrer"
        loading="lazy"
        @error="err = true"
      />
      <span v-else class="yt-fallback">{{ item.title }}</span>
      <span class="yt-play">▶</span>
    </span>
    <span class="yt-body">
      <span class="yt-title">{{ item.title }}</span>
      <span v-if="summary" class="yt-summary" :class="{ open: expanded }">{{ summary }}</span>
      <button
        v-if="long"
        type="button"
        class="yt-toggle"
        @click.stop.prevent="expanded = !expanded"
      >{{ expanded ? '收起' : '展开全文' }}</button>
      <span class="yt-meta">
        <span v-if="channel" class="yt-ch">{{ channel }}</span>
        <span v-if="dateText" class="yt-date">{{ dateText }}</span>
      </span>
    </span>
  </a>
</template>

<style scoped>
.yt-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  text-decoration: none;
  color: inherit;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
}
.yt-item:hover {
  background: var(--card-hover);
}
.yt-thumb {
  position: relative;
  width: 150px;
  height: 100px;
  overflow: hidden;
  border-radius: 6px;
  background: var(--card-2);
  flex: 0 0 auto;
}
.yt-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.yt-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  text-align: center;
  background: var(--card-2);
  color: var(--text-2);
  font-size: 12px;
}
.yt-play {
  position: absolute;
  right: 4px;
  bottom: 4px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  font-size: 11px;
  line-height: 1.5;
}
.yt-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  flex: 1 1 auto;
}
.yt-title {
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.yt-summary {
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.55;
  word-break: break-all;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.yt-summary.open {
  -webkit-line-clamp: unset;
  display: block;
  overflow: visible;
}
.yt-toggle {
  align-self: flex-start;
  background: none;
  border: 0;
  padding: 0;
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
}
.yt-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-2);
  margin-top: auto;
}
.yt-ch {
  opacity: 0.85;
}
.yt-date {
  opacity: 0.7;
}
</style>
