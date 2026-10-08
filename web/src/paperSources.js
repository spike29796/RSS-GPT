// 论文源白名单。
//
// 只有这几个源的条目会进站内阅读页（#/read/<id>），因为只有它们有
// paper_translate.py 预生成的 docs/paper/<id>.json。其余源没有译文，
// 点进去是「译文未生成」空页，复制原文地址更实在。
//
// 两处消费：
//   App.vue     openReader  —— 决定点卡片去哪（阅读页 or 原文）
//   EntryCard   copyLink    —— 决定「复制链接」复制哪一个
//
// 改这个集合 = 改「哪些条目走站内阅读页」，别处不用动。
export const PAPER_SOURCES = new Set([
  'arxiv-agent',
  'arxiv-t2i',
  'arxiv-video',
  'arxiv-llm-eng',
])

// 条目 → 是不是论文源。entry.source 是源 id（api.js 注入），
// sourceLabel 是显示名，兼容一下旧快照里只存了 label 的情况。
export function isPaperSource(entry) {
  const src = (entry && (entry.source || entry.sourceLabel)) || ''
  return PAPER_SOURCES.has(src)
}
