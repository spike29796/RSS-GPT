<script setup>
import { ref } from 'vue'
import { safeLink } from '../sanitize.js'

defineProps({
  item: { type: Object, required: true },
})

// 单条裂图兜底：封面加载失败渲染占位块（居中标题），不显示浏览器裂图图标
const err = ref(false)
</script>

<template>
  <a class="bili-item" :href="safeLink(item.link)" target="_blank" rel="noopener">
    <span class="bili-thumb">
      <img
        v-if="!err"
        :src="item.cover"
        :alt="item.title"
        referrerpolicy="no-referrer"
        @error="err = true"
      />
      <span v-else class="bili-fallback">{{ item.title }}</span>
    </span>
    <span class="bili-title">{{ item.title }}</span>
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
.bili-title {
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
