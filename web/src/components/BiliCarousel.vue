<script setup>
// T-027 B站轮播紧凑化：主区无边框封面大图自动轮播（高 ≤320px）+ 两侧隐形滑动键 + 标题压底 +
// 右侧缩略区 9 条（当前条目之后 9 条，取模循环，主区 1 + 侧窗 9 = top10 全露）。
// sanitize 口径：title/up_name 一律文本插值（禁 v-html），链接一律过 safeLink()。
// 主题：只用既有 CSS 变量，不加新主题。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { safeLink } from '../sanitize.js'
import { formatShort } from '../format.js'

const props = defineProps({
  // 合流时间倒序前 10 条（App.vue top10 computed 传入；不足 10 按实际）
  items: { type: Array, required: true },
})

const INTERVAL_MS = 4000 // 自动轮播间隔 4 秒（验收 1 要求 3-5s 区间，取 4s）
const THUMB_COUNT = 9 // 侧边缩略区条数（主区 1 + 侧窗 9 = top10 全露）

const current = ref(0)
let timer = null

// 裂图兜底：cover 加载失败的条目改渲染占位块（var(--card-2) 底 + 居中标题），
// 不显示浏览器裂图图标。按 bvid 记录，样例/真实数据通用。
const broken = ref({})
function onCoverError(item) {
  broken.value = { ...broken.value, [item.bvid]: true }
}

const currentItem = computed(() => props.items[current.value] || null)

// 当前条目之后 THUMB_COUNT 条，取模循环
const thumbs = computed(() => {
  const n = props.items.length
  const out = []
  for (let k = 1; k <= Math.min(THUMB_COUNT, n - 1); k++) {
    out.push(props.items[(current.value + k) % n])
  }
  return out
})

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function startTimer() {
  stopTimer()
  if (props.items.length > 1) timer = setInterval(() => go(1), INTERVAL_MS)
}

// 手动切换后重置自动轮播计时
function go(step) {
  const n = props.items.length
  if (!n) return
  current.value = (current.value + step + n) % n
  startTimer()
}

function jump(item) {
  const i = props.items.indexOf(item)
  if (i >= 0) {
    current.value = i
    startTimer()
  }
}

// 悬停模块暂停自动轮播，离开恢复
function onEnter() {
  stopTimer()
}
function onLeave() {
  startTimer()
}

onMounted(startTimer)
onBeforeUnmount(stopTimer)
</script>

<template>
  <section class="section bili" @mouseenter="onEnter" @mouseleave="onLeave">
    <h2 class="section-title">哔哩哔哩 · 精选投稿 <span class="count">{{ items.length }}</span></h2>
    <div class="bc-row">
      <!-- 主区：封面无边框撑满 + 两侧隐形滑动键 + 标题压底，整块可点跳 bvid -->
      <div class="bc-main">
        <a
          v-if="currentItem"
          class="bc-cover"
          :href="safeLink(currentItem.link)"
          target="_blank"
          rel="noopener"
        >
          <div v-if="broken[currentItem.bvid]" class="bc-fallback">{{ currentItem.title }}</div>
          <img
            v-else
            :src="currentItem.cover"
            :alt="currentItem.title"
            referrerpolicy="no-referrer"
            @error="onCoverError(currentItem)"
          />
          <span class="bc-caption">
            <span class="bc-title">{{ currentItem.title }}</span>
            <span class="bc-meta">{{ currentItem.up_name }} · {{ formatShort(currentItem.published) }}</span>
          </span>
        </a>
        <span class="bc-zone left"><button class="bc-nav" aria-label="上一条" @click="go(-1)">‹</button></span>
        <span class="bc-zone right"><button class="bc-nav" aria-label="下一条" @click="go(1)">›</button></span>
      </div>

      <!-- 侧边缩略区：当前条目之后 9 条，点击切换主区 -->
      <div v-if="thumbs.length" class="bc-thumbs">
        <button
          v-for="t in thumbs"
          :key="t.bvid"
          class="bc-thumb"
          :title="t.title"
          @click="jump(t)"
        >
          <span v-if="broken[t.bvid]" class="bc-thumb-fallback">{{ t.title }}</span>
          <img
            v-else
            :src="t.cover"
            :alt="t.title"
            referrerpolicy="no-referrer"
            @error="onCoverError(t)"
          />
          <span class="bc-thumb-title">{{ t.title }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.bc-row {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  align-items: stretch;
}

/* 主区：桌面 16:9 且 ≤320px；宽度撑满剩余空间（容器全宽 = 首页四卡行宽） */
.bc-main {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  aspect-ratio: 16 / 9;
  max-height: 320px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--card-2);
}
.bc-cover {
  display: block;
  width: 100%;
  height: 100%;
  text-decoration: none;
}
.bc-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  border: none;
}
.bc-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  text-align: center;
  background: var(--card-2);
  color: var(--text-2);
  font-size: 15px;
}

/* 标题压底：深色半透明渐变 + 浅色字，最多两行截断；不依赖封面亮度 */
.bc-caption {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 40px 16px 12px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.72));
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: 4px;
  pointer-events: none;
}
.bc-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.bc-meta {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
}

/* 两侧隐形滑动键：默认不可见，悬停对应侧显现；点一次滑一张，左右循环 */
.bc-zone {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 22%;
  display: flex;
  align-items: center;
}
.bc-zone.left {
  left: 0;
  justify-content: flex-start;
}
.bc-zone.right {
  right: 0;
  justify-content: flex-end;
}
.bc-nav {
  opacity: 0;
  transition: opacity 0.2s;
  width: 40px;
  height: 56px;
  margin: 0 10px;
  border: none;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}
.bc-zone:hover .bc-nav,
.bc-nav:focus-visible {
  opacity: 1;
}

/* 侧边缩略区：紧邻主区右侧，9 格纵排均分主区高度 */
.bc-thumbs {
  flex: 0 0 160px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bc-thumb {
  position: relative;
  flex: 1 1 0;
  min-height: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--card-2);
  cursor: pointer;
}
.bc-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.bc-thumb-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  font-size: 12px;
  color: var(--text-2);
  text-align: center;
}
.bc-thumb-title {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 14px 8px 5px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.72));
  color: #fff;
  font-size: 11px;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}

/* 手机宽度（对齐 .list 的 700px 断点）：缩略区移至主区下方横排折行；任何宽度不横向滚动 */
@media (max-width: 699px) {
  .bc-row {
    flex-direction: column;
  }
  .bc-thumbs {
    flex: none;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .bc-thumb {
    flex: 1 1 60px;
    max-width: calc(25% - 4.5px);
    aspect-ratio: 16 / 9;
  }
  .bc-thumb-title {
    display: none;
  }
  .bc-title {
    font-size: 14px;
  }
}
</style>
