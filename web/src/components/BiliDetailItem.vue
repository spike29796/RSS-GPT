<script setup>
import { ref } from 'vue'
import { safeLink } from '../sanitize.js'

const props = defineProps({
  item: { type: Object, required: true },
})
const emit = defineEmits(['play']) // T-037：条目点击就地弹播放器

// 单条裂图兜底：封面加载失败渲染占位块（居中标题），不显示浏览器裂图图标
const err = ref(false)

// 2026-09-25：大卫反馈「B站的标题翻译和摘要也没有」——
// 后端已补 summary(视频简介)/duration/play 三个字段，这里把它们显示出来。
import { computed } from 'vue'
const durText = computed(() => {
  const s = Number(props.item.duration) || 0
  if (!s) return ''
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
})
const playText = computed(() => {
  const n = Number(props.item.play) || 0
  if (!n) return ''
  if (n >= 100000000) return (n / 100000000).toFixed(1) + ' 亿播放'
  if (n >= 10000) return (n / 10000).toFixed(1) + ' 万播放'
  return n + ' 播放'
})
</script>

<template>
  <a class="bili-item" :href="safeLink(item.link)" @click.prevent="emit('play', item)">
    <span class="bili-thumb">
      <img
        v-if="!err"
        :src="item.cover"
        :alt="item.title"
        referrerpolicy="no-referrer"
        @error="err = true"
      />
      <span v-else class="bili-fallback">{{ item.title }}</span>
      <span v-if="durText" class="bili-dur">{{ durText }}</span>
    </span>
    <span class="bili-body">
      <span class="bili-title">{{ item.title }}</span>
      <span v-if="item.summary" class="bili-summary">{{ item.summary }}</span>
      <span class="bili-meta">
        <span class="bili-up">{{ item.up_name }}</span>
        <span v-if="playText" class="bili-stat">{{ playText }}</span>
      </span>
    </span>
  </a>
</template>

<style scoped>
.bili-item {
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
.bili-item:hover {
  background: var(--card-hover);
}
.bili-thumb {
  position: relative;
  width: 150px;
  height: 100px;
  overflow: hidden;
  border-radius: 6px;
  background: var(--card-2);
  flex: 0 0 auto;
}
.bili-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.bili-fallback {
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
.bili-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  flex: 1 1 auto;
}
.bili-title {
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.bili-summary {
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}
.bili-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-2);
  margin-top: auto;
}
.bili-up {
  opacity: 0.85;
}
.bili-stat {
  opacity: 0.7;
}
.bili-dur {
  position: absolute;
  right: 4px;
  bottom: 4px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  font-size: 11px;
  line-height: 1.5;
}
</style>
