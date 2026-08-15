<script setup>
// T-033 轮播 coverflow 化重做（round-2，包工头呈现反馈修订）：主显示 1000×520 居中 + 左右各 3 预览卡等比缩小 + 切换滑动替换动画。
// 移动端只留主卡满宽+导航（不渲染预览卡叠放）。常量/几何定案见契约 A（全具名常量便于微调）。
// sanitize 口径：title/up_name 一律文本插值（禁 v-html），链接一律过 safeLink()。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { safeLink } from '../sanitize.js'
import { formatShort } from '../format.js'

const props = defineProps({
  // 合流时间倒序前 10 条（App.vue top10 computed 传入；不足 10 按实际）
  items: { type: Array, required: true },
})

// ---- 契约 A — 常量与几何定案（round-2 施工定值）----
const INTERVAL_MS = 4000 // 自动轮播间隔 4 秒
const MAIN_W = 1000 // 主显示宽
const MAIN_H = 520 // 主显示高
const CARD_W = 500 // 预览卡基准宽（2 卡宽 = 1000）
const CARD_H = 346.67 // 预览卡基准高（1.5 卡高 ≈ 520）
const SCALE_STEP = 0.78 // 相邻级缩放比
const SIDE_COUNT = 3 // 左右各 3 预览卡
const PEEK = [110, 70, 40] // rel1/2/3 相对内一张卡露出的可见宽度 px（round-2 重算，1440 全露）
const Z_BASE = 10 // 主卡 z，|rel| 每加 1 减 1

const current = ref(0)
let timer = null

// 裂图兜底：cover 加载失败改渲染占位块，不显示浏览器裂图图标。按 bvid 记录。
const broken = ref({})
function onCoverError(item) {
  broken.value = { ...broken.value, [item.bvid]: true }
}

const currentItem = computed(() => props.items[current.value] || null)

// 几何：hw(k)=|rel|=k 卡视觉半宽；sc(k)=缩放比；ox(k)=右侧中心偏移（左侧取负）
function hw(k) {
  return k === 0 ? MAIN_W / 2 : (CARD_W / 2) * SCALE_STEP ** (k - 1)
}
function sc(k) {
  return k === 0 ? 1 : SCALE_STEP ** (k - 1)
}
function ox(k) {
  if (k === 0) return 0
  return ox(k - 1) + hw(k - 1) + PEEK[k - 1] - hw(k)
}

// visible：以 current 为中心，rel ∈ [-SIDE_COUNT..+SIDE_COUNT] 取模循环；不足 7 条按实际渲染
const visible = computed(() => {
  const n = props.items.length
  if (!n) return []
  const half = Math.min(SIDE_COUNT, Math.floor((n - 1) / 2))
  const out = []
  for (let rel = -half; rel <= half; rel++) {
    out.push({ item: props.items[((current.value + rel) % n + n) % n], rel })
  }
  return out
})
const mainCard = computed(() => visible.value.find((c) => c.rel === 0) || null)
const previews = computed(() => visible.value.filter((c) => c.rel !== 0))

// 桌面卡样式：origin:center 下 translateX 补 -50% 自身宽，卡中心才落 ox（round-1 实测修正）
function cardStyle(c) {
  if (c.rel === 0) {
    return {
      width: `${MAIN_W}px`,
      height: `${MAIN_H}px`,
      transform: 'translateX(-50%) translateY(-50%)',
      zIndex: Z_BASE,
    }
  }
  const sign = c.rel < 0 ? -1 : 1
  const k = Math.abs(c.rel)
  return {
    width: `${CARD_W}px`,
    height: `${CARD_H}px`,
    transform: `translateX(calc(${sign * ox(k)}px - 50%)) translateY(-50%) scale(${sc(k)})`,
    zIndex: Z_BASE - k,
  }
}

// 桌面绑内联 transform；移动端不绑（只留主卡满宽，不渲染预览卡）
const isDesktop = ref(window.matchMedia('(min-width: 700px)').matches)
let mql = null
function syncMql() {
  isDesktop.value = mql.matches
}

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

onMounted(() => {
  mql = window.matchMedia('(min-width: 700px)')
  mql.addEventListener('change', syncMql)
  syncMql()
  startTimer()
})
onBeforeUnmount(() => {
  if (mql) mql.removeEventListener('change', syncMql)
  stopTimer()
})
</script>

<template>
  <section class="section bili" @mouseenter="onEnter" @mouseleave="onLeave">
    <h2 class="section-title">哔哩哔哩 · 精选投稿 <span class="count">{{ items.length }}</span></h2>
    <div class="cf-stage">
      <!-- 主显示：1000×520 居中，含滑键的整块行为保留；移动端走满宽 CSS -->
      <div v-if="mainCard" class="cf-main" :style="isDesktop ? cardStyle(mainCard) : undefined">
        <a
          v-if="mainCard.item"
          class="bc-cover"
          :href="safeLink(mainCard.item.link)"
          target="_blank"
          rel="noopener"
        >
          <div v-if="broken[mainCard.item.bvid]" class="bc-fallback">{{ mainCard.item.title }}</div>
          <img
            v-else
            :src="mainCard.item.cover"
            :alt="mainCard.item.title"
            referrerpolicy="no-referrer"
            @error="onCoverError(mainCard.item)"
          />
          <span class="bc-caption">
            <span class="bc-title">{{ mainCard.item.title }}</span>
            <span class="bc-meta">{{ mainCard.item.up_name }} · {{ formatShort(mainCard.item.published) }}</span>
          </span>
        </a>
        <span class="bc-zone left"><button class="bc-nav" aria-label="上一条" @click="go(-1)">‹</button></span>
        <span class="bc-zone right"><button class="bc-nav" aria-label="下一条" @click="go(1)">›</button></span>
      </div>

      <!-- 预览卡：桌面绝对定位等比排列；移动端不渲染（验收 5 只留主卡） -->
      <div v-if="isDesktop && previews.length" class="cf-deck">
        <div
          v-for="p in previews"
          :key="p.item.bvid"
          class="cf-card"
          :style="cardStyle(p)"
        >
          <button class="cf-peek" :title="p.item.title" @click="jump(p.item)">
            <span v-if="broken[p.item.bvid]" class="bc-thumb-fallback">{{ p.item.title }}</span>
            <img
              v-else
              :src="p.item.cover"
              :alt="p.item.title"
              referrerpolicy="no-referrer"
              @error="onCoverError(p.item)"
            />
            <span class="bc-thumb-title">{{ p.item.title }}</span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 轨道：100vw 满宽突破 .page 24px 内边距，主显示视口水平居中；卡组溢出由本容器裁剪，页面零横向滚动 */
.cf-stage {
  width: 100vw;
  margin-left: calc(50% - 50vw);
  height: 520px;
  overflow: hidden;
  position: relative;
}

/* 主显示：绝对居中，尺寸/偏移由内联 cardStyle 给定 */
.cf-main {
  position: absolute;
  left: 50%;
  top: 50%;
  transform-origin: center;
  border-radius: 12px;
  overflow: hidden;
  background: var(--card-2);
}

/* 预览卡：绝对定位 + 内联 transform 等比排列，切换 transform 0.5s 滑动替换 */
.cf-card {
  position: absolute;
  left: 50%;
  top: 50%;
  transform-origin: center;
  width: 500px;
  height: 346.67px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--card-2);
  transition: transform 0.5s cubic-bezier(0.25, 0.1, 0.25, 1);
}
.cf-card:hover {
  filter: brightness(1.08);
  cursor: pointer;
}

/* 预览卡点击区：撑满卡面 */
.cf-peek {
  display: block;
  width: 100%;
  height: 100%;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  position: relative;
}
.cf-peek img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* 主卡封面/标题压底/滑键：样式自 T-027 原样迁移，仅换宿主 .cf-main */
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

/* 预览卡标题压底 + 裂图占位 */
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
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  pointer-events: none;
}

/* 移动端（对齐 .list 的 700px 断点）：只留主卡满宽+滑键，不渲染预览卡；页面零横向滚动 */
@media (max-width: 699px) {
  .cf-stage {
    width: auto;
    margin-left: 0;
    height: auto;
    overflow: visible;
  }
  .cf-main {
    position: relative;
    left: auto;
    top: auto;
    width: 100%;
    height: auto;
    aspect-ratio: 25 / 13;
    transform: none;
  }
  .bc-title {
    font-size: 14px;
  }
}
</style>
