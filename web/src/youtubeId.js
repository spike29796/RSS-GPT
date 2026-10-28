// YouTube 链接 → videoId。
//
// 条目卡点开就地播放（PlayerOverlay），需要从 entry.link 里认出 YouTube 并
// 取到 11 位 videoId。feed 里的链接有这三种形态：
//
//   https://www.youtube.com/watch?v=<ID>[&t=..]
//   https://youtu.be/<ID>[?t=..]
//   https://www.youtube.com/shorts/<ID>
//
// 认不出来就返回 null —— 调用方据此走原来的「开原文」路径，不做猜测。
//
// 只认白名单主机（youtube.com / youtu.be / youtube-nocookie.com）和 11 位
// 合法字符的 ID：这个值会拼进 iframe src，和 PlayerOverlay 里 bvid 白名单
// 是同一条防线，宁可返回 null 也不放行可疑串。

const ID_RE = /^[A-Za-z0-9_-]{11}$/

function pick(id) {
  return id && ID_RE.test(id) ? id : null
}

export function youtubeId(link) {
  if (!link) return null
  let u
  try {
    u = new URL(String(link))
  } catch (e) {
    return null
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null

  // www. / m. / music. 都归一到同一台主机；其余子域（如 notyoutube.com 的伪装）
  // 不在白名单里，直接拒。
  const host = u.hostname.toLowerCase().replace(/^(www|m|music)\./, '')

  if (host === 'youtu.be') {
    return pick(u.pathname.split('/')[1])
  }
  if (host !== 'youtube.com' && host !== 'youtube-nocookie.com') return null

  // watch?v= 必须点名参数；顺便兼容带 app=desktop 等前置参数的链接。
  const v = u.searchParams.get('v')
  if (v) return pick(v)

  // /shorts/<ID>、/embed/<ID>、/live/<ID>、/v/<ID>
  const m = u.pathname.match(/^\/(?:shorts|embed|live|v)\/([^/?#]+)/)
  return m ? pick(m[1]) : null
}
