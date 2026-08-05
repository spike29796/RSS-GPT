// UI screenshot review: serves the built app statically and captures the home
// and list views across themes and viewport widths.
// Usage: node scripts/ui_shots.mjs [docsDir] [outDir] [port]
// Port also configurable via UI_SHOTS_PORT env; defaults to 8931.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { existsSync, mkdirSync } from 'node:fs'
import { join, extname, resolve } from 'node:path'
import { chromium } from 'playwright'

const DOCS = resolve(process.argv[2] || '../RSS-GPT/docs')
const OUT = resolve(process.argv[3] || 'test-shots')
const PORT = Number(process.argv[4] || process.env.UI_SHOTS_PORT || 8931)
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.jsonl': 'application/json', '.xml': 'text/xml', '.png': 'image/png' }

const server = createServer(async (req, res) => {
  let path = decodeURIComponent(new URL(req.url, 'http://x').pathname)
  if (path.endsWith('/')) path += 'index.html'
  const file = join(DOCS, path.replace(/^\/RSS-GPT\/?/, ''))
  try {
    const data = await readFile(file)
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream' })
    res.end(data)
  } catch {
    res.writeHead(404); res.end('nf')
  }
})
await new Promise((r) => server.listen(PORT, r))

mkdirSync(OUT, { recursive: true })
const browser = await chromium.launch()

async function shot(name, { width = 1600, height = 950, theme = 'dark', zh = false, page: pageFn } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: theme })
  const page = await ctx.newPage()
  await page.goto(`http://localhost:${PORT}/RSS-GPT/`, { waitUntil: 'networkidle' })
  if (theme) await page.evaluate((t) => { localStorage.setItem('theme', t); document.documentElement.dataset.theme = t }, theme)
  if (zh) await page.evaluate(() => localStorage.setItem('showZh', '1'))
  await page.reload({ waitUntil: 'networkidle' })
  if (pageFn) await pageFn(page)
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: false })
  console.log('shot:', name)
  await ctx.close()
}

const clickLeague = async (page) => {
  await page.click('.league-head')
  await page.waitForTimeout(600)
}
const clickSecondLeague = async (page) => {
  await page.click('.league-card:nth-child(2) .league-head')
  await page.waitForTimeout(600)
}

await shot('home-dark-1600')
await shot('home-light-1600', { theme: 'light' })
await shot('home-dark-390', { width: 390, height: 844 })
await shot('list-dark-1600', { page: clickLeague })
await shot('list-light-1600', { theme: 'light', page: clickLeague })
await shot('list-dark-1600-zh', { zh: true, page: clickLeague })
await shot('list-claude-dark-1600', { page: clickSecondLeague })
await shot('list-dark-390', { width: 390, height: 844, page: clickLeague })

await browser.close()
server.close()
console.log('done ->', OUT)
