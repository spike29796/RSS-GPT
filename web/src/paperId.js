// paper_translate.py 的 id 口径：sha1(link)[:16]（link 按 UTF-8 编码）。
// 前端必须能自己算出同一个 id，条目卡才能直接指向 docs/paper/<id>.json，
// 不必再等一个索引文件（站点是纯静态的，没有后端能查）。
//
// 用纯 JS 实现而不是 crypto.subtle：subtle.digest 是异步的，条目卡在渲染期
// 就要拿到 id（:key / 链接 href），异步会逼出一堆中间状态。链接都很短，
// 同步实现的成本可以忽略。

function utf8Bytes(str) {
  const out = []
  for (let i = 0; i < str.length; i++) {
    let c = str.charCodeAt(i)
    if (c < 0x80) {
      out.push(c)
    } else if (c < 0x800) {
      out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f))
    } else if (c >= 0xd800 && c <= 0xdbff) {
      // 代理对 → 4 字节
      const c2 = str.charCodeAt(++i)
      c = 0x10000 + ((c - 0xd800) << 10) + (c2 - 0xdc00)
      out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f))
    } else {
      out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f))
    }
  }
  return out
}

function sha1Hex(bytes) {
  const ml = bytes.length * 8
  const msg = bytes.slice()
  msg.push(0x80)
  while (msg.length % 64 !== 56) msg.push(0)
  const hi = Math.floor(ml / 4294967296)
  const lo = ml >>> 0
  msg.push((hi >>> 24) & 0xff, (hi >>> 16) & 0xff, (hi >>> 8) & 0xff, hi & 0xff)
  msg.push((lo >>> 24) & 0xff, (lo >>> 16) & 0xff, (lo >>> 8) & 0xff, lo & 0xff)

  let h0 = 0x67452301
  let h1 = 0xefcdab89
  let h2 = 0x98badcfe
  let h3 = 0x10325476
  let h4 = 0xc3d2e1f0
  const w = new Array(80)

  for (let i = 0; i < msg.length; i += 64) {
    for (let j = 0; j < 16; j++) {
      w[j] = (msg[i + 4 * j] << 24) | (msg[i + 4 * j + 1] << 16) | (msg[i + 4 * j + 2] << 8) | msg[i + 4 * j + 3]
    }
    for (let j = 16; j < 80; j++) {
      const x = w[j - 3] ^ w[j - 8] ^ w[j - 14] ^ w[j - 16]
      w[j] = ((x << 1) | (x >>> 31)) >>> 0
    }
    let a = h0
    let b = h1
    let c = h2
    let d = h3
    let e = h4
    for (let j = 0; j < 80; j++) {
      let f
      let k
      if (j < 20) {
        f = (b & c) | (~b & d)
        k = 0x5a827999
      } else if (j < 40) {
        f = b ^ c ^ d
        k = 0x6ed9eba1
      } else if (j < 60) {
        f = (b & c) | (b & d) | (c & d)
        k = 0x8f1bbcdc
      } else {
        f = b ^ c ^ d
        k = 0xca62c1d6
      }
      const t = ((((a << 5) | (a >>> 27)) + f + e + k + w[j]) | 0) >>> 0
      e = d
      d = c
      c = ((b << 30) | (b >>> 2)) >>> 0
      b = a
      a = t
    }
    h0 = (h0 + a) >>> 0
    h1 = (h1 + b) >>> 0
    h2 = (h2 + c) >>> 0
    h3 = (h3 + d) >>> 0
    h4 = (h4 + e) >>> 0
  }
  const hex = (n) => (n >>> 0).toString(16).padStart(8, '0')
  return hex(h0) + hex(h1) + hex(h2) + hex(h3) + hex(h4)
}

// 与 paper_translate.py 的 sha1_16() 对齐：取前 16 位十六进制。
export function paperId(link) {
  if (!link) return ''
  return sha1Hex(utf8Bytes(String(link))).slice(0, 16)
}
