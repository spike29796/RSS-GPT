<script setup>
import { computed, ref } from 'vue'
import { formatDate, extractImage } from '../format.js'

const props = defineProps({
  entry: { type: Object, required: true },
})

// Summary HTML is produced by our own pipeline (model output with <br> markers),
// so v-html is acceptable here; external article HTML is never rendered.
const summaryHtml = computed(() => props.entry.summary || '')
const image = computed(() => extractImage(props.entry.content))
const date = computed(() => formatDate(props.entry.published))
// Broken thumbnail: hide it entirely (alt text would duplicate the title).
const imageFailed = ref(false)
</script>

<template>
  <a class="card" :style="{ borderLeftColor: entry.accent || '#7c8798' }" :href="entry.link" target="_blank" rel="noopener">
    <img
      v-if="image && !imageFailed"
      class="thumb"
      :src="image"
      alt=""
      loading="lazy"
      @error="imageFailed = true"
    />
    <div class="body">
      <div class="meta">
        <span class="league" :style="{ background: entry.accent || '#7c8798' }">{{ entry.league }}</span>
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
  background: #242e40;
  border: 1px solid #33405a;
  border-left: 4px solid #7c8798;
  border-radius: 8px;
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  transition: background 0.15s;
}
.card:hover {
  background: #2b3850;
}
.thumb {
  width: 100%;
  max-height: 200px;
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
  color: #7c8798;
  margin-bottom: 6px;
}
.league {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  color: #141a26;
  font-weight: 700;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.badge {
  background: #1f2839;
  border: 1px solid #2c3850;
  color: #7fd4a8;
  border-radius: 4px;
  padding: 1px 8px;
  font-weight: 600;
}
.date {
  margin-left: auto;
}
.title {
  margin: 0 0 6px;
  font-size: 15px;
  line-height: 1.4;
}
.summary {
  font-size: 13px;
  color: #9fb0c8;
  line-height: 1.6;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
