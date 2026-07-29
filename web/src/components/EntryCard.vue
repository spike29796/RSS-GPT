<script setup>
import { computed } from 'vue'
import { formatDate, extractImage } from '../format.js'

const props = defineProps({
  entry: { type: Object, required: true },
})

// Summary HTML is produced by our own pipeline (model output with <br> markers),
// so v-html is acceptable here; external article HTML is never rendered.
const summaryHtml = computed(() => props.entry.summary || '')
const image = computed(() => extractImage(props.entry.content))
const date = computed(() => formatDate(props.entry.published))
</script>

<template>
  <a class="card" :href="entry.link" target="_blank" rel="noopener">
    <img v-if="image" class="thumb" :src="image" :alt="entry.title" loading="lazy" />
    <div class="body">
      <div class="meta">
        <span class="badge">{{ entry.category }}</span>
        <span class="source">{{ entry.sourceLabel }}</span>
        <span class="date">{{ date }}</span>
      </div>
      <h3 class="title">{{ entry.title }}</h3>
      <div v-if="summaryHtml" class="summary" v-html="summaryHtml"></div>
    </div>
  </a>
</template>

<style scoped>
.card {
  display: block;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  margin-bottom: 12px;
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  transition: box-shadow 0.15s;
}
.card:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
}
.thumb {
  width: 100%;
  max-height: 220px;
  object-fit: cover;
  display: block;
}
.body {
  padding: 12px 16px 14px;
}
.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
}
.badge {
  background: #eef2ff;
  color: #4338ca;
  border-radius: 4px;
  padding: 1px 8px;
  font-weight: 600;
}
.date {
  margin-left: auto;
}
.title {
  margin: 0 0 6px;
  font-size: 16px;
  line-height: 1.4;
}
.summary {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.6;
  word-break: break-word;
}
</style>
