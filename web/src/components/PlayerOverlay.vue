<script setup>
// T-037 B站视频就地播放（A 方案）：官方 iframe 播放器遮罩，可关闭（按钮/ESC/点遮罩）。
// 安全：bvid 白名单 BVID_RE + encodeURIComponent 拼装 iframe src；不合规则不渲染 iframe。
import { computed, onBeforeUnmount, onMounted } from 'vue'

const props = defineProps({
  bvid: { type: String, required: true },
})
const emit = defineEmits(['close'])

// bvid 白名单：BV + 6~20 位字母数字，防污染数据注入 iframe src
const BVID_RE = /^BV[0-9A-Za-z]{6,20}$/
const src = computed(() =>
  BVID_RE.test(props.bvid)
    ? `https://player.bilibili.com/player.html?bvid=${encodeURIComponent(props.bvid)}&page=1&high_quality=1&danmaku=0`
    : null,
)

// ESC 关闭
function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="player-overlay" @click.self="emit('close')">
    <div class="player-box">
      <button class="player-close" aria-label="关闭" @click="emit('close')">✕</button>
      <iframe
        v-if="src"
        :src="src"
        allowfullscreen
        allow="autoplay; fullscreen; encrypted-media"
        referrerpolicy="no-referrer"
        title="B站视频播放"
      ></iframe>
      <p v-else class="player-invalid">视频地址无效</p>
    </div>
  </div>
</template>

<style scoped>
.player-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
  padding: 24px;
}
.player-box {
  position: relative;
  width: min(960px, 100%);
  aspect-ratio: 16 / 9;
}
.player-box iframe {
  display: block; /* iframe 默认 inline 会有 descender 空隙，block 消除使 box 严格 16:9 */
  width: 100%;
  height: 100%;
  border: 0;
  border-radius: 8px;
  background: #000;
}
.player-close {
  position: absolute;
  top: -40px;
  right: 0;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
.player-close:hover {
  background: rgba(0, 0, 0, 0.75);
}
.player-invalid {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #111;
  color: #9fb0c8;
  margin: 0;
}
</style>
