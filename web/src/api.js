// Data access: fetch the pipeline's JSONL files published alongside the app.
// Record shape: {link, title, published, updated, category, summary, content}

export const SOURCES = [
  { name: 'qbitai', label: '量子位 QbitAI', league: 'A', accent: '#4f46e5' },
  { name: 'geekpark', label: '极客公园 GeekPark', league: 'B', accent: '#ef4444' },
  // T-040 2026-09-14：IT之家下线 —— 大卫用意图标注判定「99% 是垃圾信息」，
  // 数据佐证：120 条里含 AI 词仅 20.8%（半数还是伪 AI），消费电子/汽车占 45%。
  // { name: 'ithome', label: 'IT之家 ITHome', league: 'C', accent: '#f59e0b' },
  { name: 'producthunt', label: 'Product Hunt', league: 'D', accent: '#da552f' },
  { name: 'infoq', label: 'InfoQ 中文', league: 'E', accent: '#0ea5e9' },
  { name: 'simonwillison', label: 'Simon Willison', league: 'F', accent: '#22c55e' },
  { name: 'nvidia-blog', label: 'NVIDIA Blog', league: 'G', accent: '#76b900' },
  { name: 'openai-news', label: 'OpenAI News', league: 'H', accent: '#7fd4a8' },
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
