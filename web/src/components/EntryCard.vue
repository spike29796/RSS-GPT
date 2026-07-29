<script setup>
import { computed } from 'vue'
import { formatDate } from '../format.js'

const props = defineProps({
  entry: { type: Object, required: true },
})

// Official-site card hierarchy: uppercase tag -> title -> date -> one-line guide.
// Summary HTML is produced by our own pipeline (model output with <br> markers),
// so v-html is acceptable here; external article HTML is never rendered.
const summaryHtml = computed(() => props.entry.summary || '')
const date = computed(() => formatDate(props.entry.published))
</script>

<template>
  <a class="card" :href="entry.link" target="_blank" rel="noopener">
    <span class="tag">{{ entry.category }}</span>
    <h3 class="title">{{ entry.title }}</h3>
    <span class="date">{{ date }}</span>
    <div v-if="summaryHtml" class="summary" v-html="summaryHtml"></div>
  </a>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #242e40;
  border: 1px solid #33405a;
  border-radius: 8px;
  padding: 16px 18px;
  text-decoration: none;
  color: inherit;
  transition: background 0.15s;
}
.card:hover {
  background: #2b3850;
}
.tag {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: #7fd4a8;
}
.title {
  margin: 0;
  font-size: 17px;
  line-height: 1.4;
}
.date {
  font-size: 12px;
  color: #7c8798;
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
  border-top: 1px solid #2c3850;
  padding-top: 8px;
}
</style>
