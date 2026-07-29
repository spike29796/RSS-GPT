// Data access: fetch the pipeline's JSONL files published alongside the app.
// Record shape: {link, title, published, updated, category, summary, content}

export const SOURCES = [
  { name: 'qbitai', label: '量子位', league: 'D', accent: '#5ea8ff' },
  { name: 'ithome', label: 'IT之家', league: 'D', accent: '#5ea8ff' },
  { name: 'openai-news', label: 'OpenAI News', league: 'A', accent: '#7fd4a8' },
  { name: 'awwwards-sotd', label: 'Awwwards SOTD', league: 'C', accent: '#e2b96f' },
]

async function fetchSource(source) {
  const url = `${import.meta.env.BASE_URL}${source.name}.jsonl`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${source.name}: HTTP ${resp.status}`)
  const text = await resp.text()
  return text
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => ({
      ...JSON.parse(line),
      source: source.name,
      sourceLabel: source.label,
      league: source.league,
      accent: source.accent,
    }))
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
