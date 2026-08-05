// Data access: fetch the pipeline's JSONL files published alongside the app.
// Record shape: {link, title, published, updated, category, summary, content}

export const SOURCES = [
  { name: 'openai-news', label: 'OpenAI News', league: 'A', accent: '#7fd4a8' },
  { name: 'claude-blog', label: 'Claude Blog', league: 'B', accent: '#d97757' },
  { name: 'google-blog', label: 'Google Blog', league: 'C', accent: '#4285f4' },
  { name: 'deepseek-news', label: 'DeepSeek News', league: 'D', accent: '#06b6d4' },
  { name: 'kimi-blog', label: 'Kimi Blog', league: 'E', accent: '#8b5cf6' },
  { name: 'microsoft-blog', label: 'Microsoft Blog', league: 'F', accent: '#38bdf8' },
  { name: 'apple-newsroom', label: 'Apple Newsroom', league: 'G', accent: '#d4d4d8' },
  { name: 'spacex-updates', label: 'SpaceX Updates', league: 'H', accent: '#f43f5e' },
  { name: 'nvidia-blog', label: 'NVIDIA Blog', league: 'I', accent: '#76b900' },
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
