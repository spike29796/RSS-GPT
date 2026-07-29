// Data access: fetch the pipeline's JSONL files published alongside the app.
// Record shape: {link, title, published, updated, category, summary, content}

export const SOURCES = [
  { name: 'openai-news', label: 'OpenAI News', league: 'A', accent: '#7fd4a8' },
  { name: 'claude-blog', label: 'Claude Blog', league: 'B', accent: '#d97757' },
]

async function fetchSource(source) {
  const url = `${import.meta.env.BASE_URL}${source.name}.jsonl`
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${source.name}: HTTP ${resp.status}`)
  const text = await resp.text()
  return text
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => ({ ...JSON.parse(line), source: source.name, sourceLabel: source.label }))
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
