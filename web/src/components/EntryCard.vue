<script setup>
import { computed, ref } from 'vue'
import { formatDate } from '../format.js'
import { tagLabel } from '../i18n.js'
import { paperId } from '../paperId.js'
import { isPaperSource } from '../paperSources.js'
import { sanitizeSummary, safeLink } from '../sanitize.js'
import { ui } from '../store.js'

const props = defineProps({
  entry: { type: Object, required: true },
})
// 2026-10-08：整卡原来直接跳原文。改成进站内阅读页（双语分段），
// 卡片右下角留一个次要的「原文 ↗」出口，想直接去原文的人不用绕。
const emit = defineEmits(['open'])

// The stored summary starts with '<br><br>总结:' (an RSS-facing paragraph
// marker); for the card we strip the leading line breaks and the marker text
// and render a styled 导读 label instead. Summary HTML is LLM output fed by
// external feed content, so it must be sanitized before v-html (T-004 V-01).
const guideText = computed(() => {
  let s = props.entry.summary || ''
  s = s.replace(/^(<br\s*\/?>\s*)+/, '')
  // 2026-09-11：模型偶尔输出重复标记（"总结:总结: 正文"），要循环剥掉
  s = s.replace(/^((总结|Summary)\s*[:：]\s*)+/, '')
  return sanitizeSummary(s.trim())
})
const entryLink = computed(() => safeLink(props.entry.link))
const date = computed(() => formatDate(props.entry.published))

// 2026-10-09：「复制链接」按钮。
// 复制的是「点开这张卡会去哪」的那个地址 —— 论文复制站内阅读页（对方能直接
// 看到中英对照），其余源复制原文。跟点击行为一致，不用猜自己复制到了什么。
const shareUrl = computed(() => {
  const link = entryLink.value
  if (!link) return ''
  if (!isPaperSource(props.entry)) return link
  return `${location.origin}${import.meta.env.BASE_URL}#/read/${paperId(props.entry.link)}`
})

const copyState = ref('idle')
let copyTimer = 0

// 非安全上下文（手机走 http://192.168.x.x 那种地址）里 navigator.clipboard
// 是禁用的，那条路要退回 execCommand + 临时 textarea。两条都失败才算没复制成。
async function writeClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (e) {
    /* 掉到兜底那条路 */
  }
  try {
    const ta = document.createElement('textarea')
    ta.setAttribute('readonly', '')
    ta.value = text
    // 放到视口内（display:none 的节点选不上），再用 1px 透明藏起来
    ta.style.position = 'fixed'
    ta.style.top = '0'
    ta.style.left = '0'
    ta.style.width = '1px'
    ta.style.height = '1px'
    ta.style.padding = '0'
    ta.style.border = '0'
    ta.style.outline = '0'
    ta.style.boxShadow = 'none'
    ta.style.background = 'transparent'
    ta.style.opacity = '0'
    ta.style.zIndex = '-1'
    document.body.appendChild(ta)
    const ok = (() => {
      // iOS Safari 用 readonly textarea 时 select() 圈不到内容，要先自己造 range
      const isiOS = /ipad|iphone|ipod/i.test(navigator.userAgent)
      if (isiOS) {
        const range = document.createRange()
        range.selectNodeContents(ta)
        const sel = window.getSelection()
        sel.removeAllRanges()
        sel.addRange(range)
        ta.setSelectionRange(0, 999999)
      } else {
        ta.select()
        ta.setSelectionRange(0, text.length)
      }
      return document.execCommand('copy')
    })()
    document.body.removeChild(ta)
    return ok
  } catch (e) {
    return false
  }
}

async function copyLink() {
  const url = shareUrl.value
  if (!url) return
  // 复制不成也要让按钮说话 —— 点了毫无反应是最糟的反馈
  copyState.value = (await writeClipboard(url)) ? 'done' : 'fail'
  window.clearTimeout(copyTimer)
  copyTimer = window.setTimeout(() => { copyState.value = 'idle' }, 1800)
}

const hasCjk = (s) => /[\u4e00-\u9fff]/.test(String(s || ''))

// 2026-09-11：光"含中文"不够 —— producthunt/simonwillison 的 title_zh
// 是整句中文描述（"xxx是一款……的集成开发环境，旨在……。"），照样蒙混过关，
// 显示到标题位就成了摘要。译名必须"像标题"：短、无句末标点。
const looksLikeTitle = (tz, title) => {
  const s = String(tz || '').trim()
  if (!s || !hasCjk(s)) return false
  if (/[。！？；!?;]\s*$/.test(s)) return false
  if (s.length > Math.max(40, String(title || '').length * 3)) return false
  return true
}

// 原题已是中文时永远显示原题（中文标题不需要"翻译版"）
const title = computed(() => {
  const e = props.entry
  if (!ui.showZh) return e.title
  if (hasCjk(e.title)) return e.title
  if (looksLikeTitle(e.title_zh, e.title)) return e.title_zh
  return e.title
})
const tag = computed(() => tagLabel(props.entry.category, ui.showZh))
</script>

<template>
  <div
    class="card"
    role="link"
    tabindex="0"
    @click="emit('open', entry)"
    @keydown.enter.prevent="emit('open', entry)"
  >
    <div class="meta">
      <span class="tag">{{ tag }}</span>
      <span class="date">{{ date }}</span>
    </div>
    <h3 class="title">{{ title }}</h3>
    <div v-if="guideText" class="summary"><span class="guide-label">导读</span><span v-html="guideText"></span></div>
    <div class="actions">
      <button
        class="act"
        type="button"
        :class="{ done: copyState === 'done', fail: copyState === 'fail' }"
        :title="shareUrl"
        @click.stop="copyLink"
        @keydown.enter.stop.prevent="copyLink"
        @keydown.space.stop.prevent="copyLink"
      >{{ copyState === 'done' ? '已复制 ✓' : copyState === 'fail' ? '复制失败' : '复制链接' }}</button>
      <a class="orig" :href="entryLink" target="_blank" rel="noopener" @click.stop>原文 ↗</a>
    </div>
  </div>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  transition: background 0.15s;
}
.card:hover {
  background: var(--card-hover);
}
.card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
/* 底部动作条：「复制链接」+「原文 ↗」，贴右下角，别跟标题抢注意力 */
.actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: auto;
}
.act,
.orig {
  font-size: 12px;
  color: var(--dim);
  text-decoration: none;
  padding: 3px 9px;
  border: 1px solid var(--border-2);
  border-radius: 999px;
}
.act {
  background: none;
  font-family: inherit;
  line-height: inherit;
  cursor: pointer;
}
.act:hover,
.orig:hover {
  color: var(--accent);
  border-color: var(--accent);
}
/* 复制成功那一刻给个正向反馈，不然点完不知道成没成 */
.act.done {
  color: var(--accent);
  border-color: var(--accent);
}
/* 复制不成也得说一声，不能点了没反应 */
.act.fail {
  color: #d9534f;
  border-color: #d9534f;
}
/* 手机上手指点：把动作条的点击区撑高（原来 24px 太小点不准） */
@media (max-width: 700px) {
  .act,
  .orig {
    padding: 8px 16px;
    font-size: 13px;
  }
}
/* 2026-09-25：原来 tag / title / date 各占一整行（flex column），
   一行只放一个词很浪费。改成「标签+日期」同一行，标签做成小胶囊。 */
.meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: 1px 8px;
  line-height: 1.6;
  white-space: nowrap;
}
.title {
  margin: 0;
  font-size: 17px;
  line-height: 1.4;
}
.date {
  font-size: 12px;
  color: var(--dim);
  margin-left: auto;
}
.summary {
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.6;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  border-top: 1px solid var(--border-2);
  padding-top: 8px;
}
.guide-label {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-contrast);
  background: var(--accent);
  border-radius: 3px;
  padding: 0 5px;
  margin-right: 6px;
  vertical-align: 1px;
}
</style>
