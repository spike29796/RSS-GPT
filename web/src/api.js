// Data access: fetch the pipeline's JSONL files published alongside the app.
// Record shape: {link, title, published, updated, category, summary, content}

export const SOURCES = [
  { name: 'qbitai', label: '量子位 QbitAI', league: 'A', accent: '#4f46e5' },
  { name: 'geekpark', label: '极客公园 GeekPark', league: 'B', accent: '#ef4444' },
  { name: 'infoq', label: 'InfoQ 中文', league: 'E', accent: '#0ea5e9' },
  { name: 'nvidia-blog', label: 'NVIDIA Blog', league: 'G', accent: '#76b900' },
  // T-040 2026-09-14：IT之家下线 —— 大卫用意图标注判定「99% 是垃圾信息」，
  // 数据佐证：120 条里含 AI 词仅 20.8%（半数还是伪 AI），消费电子/汽车占 45%。
  // { name: 'ithome', label: 'IT之家 ITHome', league: 'C', accent: '#f59e0b' },
  // T-047 2026-09-14：Simon Willison（7/7 标「与我无关」，多为版本号更新/纯引用帖）
  // { name: 'simonwillison', label: 'Simon Willison', league: 'F', accent: '#22c55e' },
  // T-047 2026-09-14：Product Hunt（12/12 标「与我无关」，冷门小工具发布页）
  // { name: 'producthunt', label: 'Product Hunt', league: 'D', accent: '#da552f' },

  // T-044 2026-09-14：OpenAI News 下线 —— 1000 条把页面淹了（别的源 20-60 条），
  // 且多为公司宣传（合作/政策/人事/发布）而非技术实操。
  // { name: 'openai-news', label: 'OpenAI News', league: 'H', accent: '#7fd4a8' },

  // T-041 2026-09-14：补「能直接动手」的源类型（新闻源拿不到"能马上用"）
  { name: 'github-trending', label: 'GitHub 日榜', league: 'I', accent: '#8b5cf6' },
  { name: 'hackernews', label: 'Hacker News', league: 'J', accent: '#ff6600' },
  { name: 'reddit-localllama', label: 'r/LocalLLaMA', league: 'K', accent: '#ff4500' },
  { name: 'lilianweng', label: 'Lilian Weng', league: 'L', accent: '#06b6d4' },
  { name: 'gradient', label: 'The Gradient', league: 'M', accent: '#ec4899' },
  { name: 'lobsters', label: 'Lobsters', league: 'N', accent: '#b0232a' },
  // T-048 2026-09-14：HuggingFace Blog（862 条压倒全部源 + 只有 3 条有摘要）
  // { name: 'hf-blog', label: 'HuggingFace', league: 'O', accent: '#ffd21e' },
  // T-048 2026-09-14：arXiv cs.AI（两轮抓取都是 0 条；arxiv-ro 那栏是好的）
  // { name: 'arxiv-ai', label: 'arXiv cs.AI', league: 'P', accent: '#b31b1b' },
  { name: 'arxiv-ro', label: 'arXiv 机器人', league: 'Q', accent: '#c2410c' },
  { name: 'sspai', label: '少数派', league: 'R', accent: '#d71a1b' },
]

async function fetchSource(source) {
  const url = `${import.meta.env.BASE_URL}${source.name}.jsonl`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${source.name}: HTTP ${resp.status}`)
  const text = await resp.text()
  // Per-line tolerance: one malformed line only drops that line (with a
  // console.warn), instead of failing the whole source into the errors map.
  const entries = []
  text
    .split('\n')
    .filter((line) => line.trim())
    .forEach((line, i) => {
      try {
        entries.push({ ...JSON.parse(line), source: source.name, sourceLabel: source.label })
      } catch (e) {
        console.warn(`${source.name}: line ${i + 1} skipped, bad JSON: ${e.message}`)
      }
    })
  return entries
}

// Fetch all sources in parallel; a failing source yields an empty list and is
// reported through the errors map instead of breaking the whole app.
export async function fetchAllEntries() {
  const results = await Promise.allSettled(SOURCES.map(fetchSource))
  const entries = []
  const errors = []
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') entries.push(...r.value)
    else errors.push(`${SOURCES[i].label} 加载失败：${r.reason.message}`)
  })
  return { entries, errors }
}

// T-043：推荐区数据 —— 由本地打分器 RSS-GPT/score_local.py 产出。
// 打分器读大卫的意图标注（本机导出，不进仓库）当 few-shot，
// 给最近条目打分，把 ≥2 分的写进 docs/recommended.jsonl。
// Record shape: {link, title, title_zh, source, category, published, summary, score, why}
// 文件不存在（还没跑过打分器）→ 抛错，调用方按「推荐区暂无数据」处理。
export async function fetchRecommended() {
  const url = `${import.meta.env.BASE_URL}recommended.jsonl`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`recommended: HTTP ${resp.status}`)
  const text = await resp.text()
  const out = []
  text
    .split('\n')
    .filter((line) => line.trim())
    .forEach((line, i) => {
      try {
        out.push(JSON.parse(line))
      } catch (e) {
        console.warn(`recommended: line ${i + 1} skipped, bad JSON: ${e.message}`)
      }
    })
  return out
}

// B站轮播数据（T-026 消费侧口径，T-025 产出）。 Record shape:
// {bvid, link, title, cover, up_name, uid, published}（全 string，published RFC 2822）。
// 不进 SOURCES：B站不是资讯源。 Per-line tolerance same as fetchSource;
// fetch/parse failure throws so the caller can treat it as "module hidden".
export async function fetchBiliVideos() {
  const url = `${import.meta.env.BASE_URL}bilibili.jsonl`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`bilibili: HTTP ${resp.status}`)
  const text = await resp.text()
  const entries = []
  text
    .split('\n')
    .filter((line) => line.trim())
    .forEach((line, i) => {
      try {
        entries.push(JSON.parse(line))
      } catch (e) {
        console.warn(`bilibili: line ${i + 1} skipped, bad JSON: ${e.message}`)
      }
    })
  return entries
}
