// Rendering defenses for pipeline data. The summary is LLM output whose input
// includes attacker-controllable feed content, and entry.link comes straight
// from the feed; neither is trusted (T-004 V-01/V-02).
import DOMPurify from 'dompurify'

// Real pipeline summaries only ever contain <br> (verified against all
// published jsonl), so the allowlist is br-only with no attributes.
// Note: DOMPurify allows data-* attributes by default even with an empty
// ALLOWED_ATTR, so ALLOW_DATA_ATTR is pinned to false explicitly. No JS in
// this app reads dataset, so tightening this is side-effect free.
export function sanitizeSummary(html) {
  return DOMPurify.sanitize(html || '', { ALLOWED_TAGS: ['br'], ALLOWED_ATTR: [], ALLOW_DATA_ATTR: false })
}

export function safeLink(url) {
  return /^https?:\/\//i.test(url || '') ? url : '#'
}
