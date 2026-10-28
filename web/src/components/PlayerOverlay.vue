<script setup>
// T-037 B站视频就地播放（A 方案）：官方 iframe 播放器遮罩，可关闭（按钮/ESC/点遮罩）。
// 安全：bvid 白名单 BVID_RE + encodeURIComponent 拼装 iframe src；不合规则不渲染 iframe。
//
// 2026-10-28：同一个交互壳加 YouTube 分支（youtubeId prop 优先）。
// 遮罩、ESC、点外部关闭全部沿用；B 站那条路的 src / 兜底链接原样保留。
// YouTube 走 youtube-nocookie 隐私嵌入；墙内连不上时 iframe 不会触发 load，
// 6 秒后盖一层明确说明（不在这里探测网络：CSP 拦着，探测也不准）。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  bvid: { type: String, default: '' },
  youtubeId: { type: String, default: '' },
})
const emit = defineEmits(['close'])

// bvid 白名单：BV + 6~20 位字母数字，防污染数据注入 iframe src
const BVID_RE = /^BV[0-9A-Za-z]{6,20}$/
const biliSrc = computed(() =>
  BVID_RE.test(props.bvid)
    ? `https://player.bilibili.com/player.html?bvid=${encodeURIComponent(props.bvid)}&page=1&high_quality=1&danmaku=0`
    : null,
)

// 2026-09-25：B站播放器在手机上会跳转到 www.bilibili.com/blackboard/webplayer/mbplayer.html
// （官方 player.html 里的 isMobileDevice 脚本干的）。原来 CSP 只放行 player.bilibili.com，
// 手机端 iframe 一律被拦 → 白屏。CSP 已放行 www.bilibili.com（见 index.html），
// 这里再补一个「在B站打开」的兜底入口，万一某台设备仍然播不了也能一键过去。
const biliUrl = computed(() =>
  BVID_RE.test(props.bvid) ? `https://www.bilibili.com/video/${props.bvid}` : null,
)

// YouTube videoId 白名单：11 位 [A-Za-z0-9_-]。调用方已经用 youtubeId()
// 取过一遍，这里再校验一次 —— 这个值会进 iframe src，不能只信上游。
const YT_RE = /^[A-Za-z0-9_-]{11}$/
const ytId = computed(() => (YT_RE.test(props.youtubeId) ? props.youtubeId : null))
const ytSrc = computed(() =>
  ytId.value ? `https://www.youtube-nocookie.com/embed/${ytId.value}?autoplay=1&rel=0` : null,
)
const ytWatchUrl = computed(() => (ytId.value ? `https://www.youtube.com/watch?v=${ytId.value}` : null))

// 'youtube' 优先；给错/不给 youtubeId 时退回 B 站老路径
const kind = computed(() => (ytId.value ? 'youtube' : biliSrc.value ? 'bili' : null))

// YouTube 加载超时：6 秒内没有确证「真的加载成功」就显示说明层。
// 只看 load 事件不够：连接被拒/重置时 Chrome 会立刻落到自己的错误页并照样
// 触发 load，用户看到的还是白框。这里再用浏览器自己记的 iframe 导航耗时
// 复核一次（不额外发任何请求）：成功导航通常几百毫秒，错误页 ~10ms。
// ytNonce 变一次 = 重挂一次 iframe（重试）。
const YT_TIMEOUT_MS = 6000
const YT_MIN_LOAD_MS = 150
const ytTimedOut = ref(false)
const ytLoaded = ref(false)
const ytNonce = ref(0)
let ytTimer = 0
let ytLoadCheck = 0
let ytAttemptStart = 0

function clearYtTimer() {
  if (ytTimer) {
    clearTimeout(ytTimer)
    ytTimer = 0
  }
}
function clearYtLoadCheck() {
  if (ytLoadCheck) {
    clearTimeout(ytLoadCheck)
    ytLoadCheck = 0
  }
}
function ytTimingOk() {
  if (!ytLoaded.value || !ytSrc.value) return false
  const entries =
    typeof performance.getEntriesByType === 'function' ? performance.getEntriesByType('resource') : []
  const sameSrc = entries.filter((e) => e.name === ytSrc.value)
  // 浏览器不记录跨域 iframe 导航的计时（部分 Safari）→ 退回只看 load，
  // 宁可漏报也不要对着能播的画面盖一层「连不上」。
  if (!entries.length || !sameSrc.length) return true
  // 只认本轮打开/重试的导航记录，避免上一次打开留下的旧条目干扰。
  // 留 500ms 余量：iframe 请求可能比 onMounted 早一个 tick 发出。
  return sameSrc.some((e) => e.startTime >= ytAttemptStart && e.duration >= YT_MIN_LOAD_MS)
}
function decideYt() {
  ytTimedOut.value = !ytTimingOk()
  ytTimer = 0
}
function armYtTimer() {
  clearYtTimer()
  clearYtLoadCheck()
  ytTimedOut.value = false
  ytLoaded.value = false
  ytAttemptStart = performance.now() - 500
  ytTimer = window.setTimeout(decideYt, YT_TIMEOUT_MS)
}
function onYtLoad() {
  ytLoaded.value = true
  // load 之后计时条目可能还没落盘，400ms 后再复核一次
  clearYtLoadCheck()
  ytLoadCheck = window.setTimeout(() => {
    ytLoadCheck = 0
    if (ytTimingOk()) {
      ytTimedOut.value = false
      clearYtTimer()
    }
  }, 400)
}
function retryYt() {
  ytNonce.value += 1
  armYtTimer()
}

// ESC 关闭
function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  if (kind.value === 'youtube') armYtTimer()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  clearYtTimer()
  clearYtLoadCheck()
})
</script>

<template>
  <div class="player-overlay" @click.self="emit('close')">
    <div class="player-box">
      <button class="player-close" aria-label="关闭" @click="emit('close')">✕</button>

      <!-- B 站：T-037 原样 -->
      <template v-if="kind === 'bili'">
        <iframe
          :src="biliSrc"
          allowfullscreen
          allow="autoplay; fullscreen; encrypted-media; picture-in-picture"
          referrerpolicy="strict-origin-when-cross-origin"
          title="B站视频播放"
        ></iframe>
        <p v-if="biliUrl" class="player-fallback">
          播不出来？
          <a :href="biliUrl" target="_blank" rel="noopener noreferrer">在B站打开 ↗</a>
        </p>
      </template>

      <!-- YouTube：隐私嵌入 + 超时说明层 -->
      <template v-else-if="kind === 'youtube'">
        <iframe
          :key="ytNonce"
          :src="ytSrc"
          allowfullscreen
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          referrerpolicy="strict-origin-when-cross-origin"
          title="YouTube 视频播放"
          @load="onYtLoad"
        ></iframe>
        <div v-if="ytTimedOut" class="player-timeout" role="alert">
          <strong>YouTube 需要代理，当前网络连不上</strong>
          <span>播放器 6 秒内没有加载完成。挂上代理后点「重试」，或直接去 YouTube 看。</span>
          <span class="player-timeout-actions">
            <a :href="ytWatchUrl" target="_blank" rel="noopener noreferrer">在 YouTube 打开 ↗</a>
            <button type="button" @click="retryYt">重试</button>
          </span>
        </div>
      </template>

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
.player-fallback {
  margin: 10px 0 0;
  text-align: center;
  color: #9fb0c8;
  font-size: 13px;
}
.player-fallback a {
  color: #7fd4ff;
  text-decoration: none;
  border-bottom: 1px solid rgba(127, 212, 255, 0.4);
  padding-bottom: 1px;
}
.player-fallback a:hover {
  color: #a8e3ff;
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
/* 超时说明层：盖在 iframe 上（不卸载 iframe —— 它晚一点连上仍会自己显示） */
.player-timeout {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 28px;
  border-radius: 8px;
  background: #111;
  color: #9fb0c8;
  text-align: center;
  font-size: 13px;
  line-height: 1.6;
}
.player-timeout strong {
  color: #e8eef7;
  font-size: 16px;
}
.player-timeout-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}
.player-timeout-actions a,
.player-timeout-actions button {
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  padding: 5px 14px;
  border-radius: 999px;
  cursor: pointer;
}
.player-timeout-actions a {
  color: #7fd4ff;
  border: 1px solid rgba(127, 212, 255, 0.55);
  text-decoration: none;
}
.player-timeout-actions a:hover {
  color: #a8e3ff;
  border-color: #a8e3ff;
}
.player-timeout-actions button {
  color: #9fb0c8;
  background: none;
  border: 1px solid rgba(159, 176, 200, 0.45);
}
.player-timeout-actions button:hover {
  color: #e8eef7;
  border-color: #e8eef7;
}
</style>
