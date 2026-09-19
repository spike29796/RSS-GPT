// RSS-GPT service worker —— network-first
// 目标：内容永远拿最新的（他 push 完就生效），只在断网时用缓存兜底。
const CACHE = 'rss-gpt-v1';

// 只预缓存"壳"（图标 + manifest）。数据（*.jsonl / *.xml）不预缓存，
// 因为它们是每天更新的内容，缓存了反而会看到旧数据。
const SHELL = [
  '/RSS-GPT/manifest.json',
  '/RSS-GPT/icon-192.png',
  '/RSS-GPT/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // 第三方请求不掺和

  // 数据文件：纯网络，不缓存（保证永远是最新的）
  if (/\.(jsonl|xml|log)$/i.test(url.pathname)) {
    return; // 交给浏览器默认行为
  }

  // 页面和静态资源：network-first，失败回落到缓存
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200 && res.type === 'basic') {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match('/RSS-GPT/')))
  );
});
