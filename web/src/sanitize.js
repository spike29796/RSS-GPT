// Rendering defenses for pipeline data. The summary is LLM output whose input
// includes attacker-controllable feed content, and entry.link comes straight
// from the feed; neither is trusted (T-004 V-01/V-02).
import DOMPurify from 'dompurify'

// Real pipeline summaries only ever contain <br> (verified against all
// published jsonl), so the allowlist is br-only with no attributes.
export function sanitizeSummary(html) {
  return DOMPurify.sanitize(html || '', { ALLOWED_TAGS: ['br'], ALLOWED_ATTR: [] })
}

export function safeLink(url) {
  return /^https?:\/\//i.test(url || '') ? url : '#'
}
