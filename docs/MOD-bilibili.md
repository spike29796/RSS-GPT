# MOD-bilibili：B站订阅源管线与数据契约（T-025/T-026 沉淀）

B站 up 主正式投稿的采集、数据格式与首页轮播消费链路。零 LLM（不翻译/不摘要/不分类）。

## 采集层

- 脚本 `RSS-GPT/bilibili_collect.py`（独立自包含，不 import main.py——main.py 无
  `__main__` 护栏，import 即跑全管线）。依赖仅 stdlib + requests。
- 配置 `RSS-GPT/bilibili.ini`（**不进 config.ini**：main.py 会把 config.ini 每个
  新段当 LLM 管线源处理）。字段：`api_base`（默认 https://api.bilibili.com，可切换）、
  `uids`（14 个，源清单在共享区 uid.txt）、`per_uid_per_run_max`（5）、
  `request_interval_sec`（1，防风控）。
- 数据源：B站官方 API `GET {api_base}/x/space/wbi/arc/search`（包工头拍板弃 RSSHub——
  三公共实例全灭：rsshub.app CF IP 封锁、两镜像 Playwright 残缺）。
  - WBI 签名：`x/web-interface/nav` 取 wbi_img keys（未登录 code -101 也照给）→
    64 值置换表重排取前 32 = mixin_key → 参数排序 urlencode + wts → md5 得 w_rid。
  - **必带 dm 指纹四件套**（dm_img_list/dm_img_str/dm_cover_img_str/dm_img_inter，
    写死常量）+ 会话 cookie 引导（GET www.bilibili.com 收 buvid3）+ Referer
    space.bilibili.com/{uid}/video；缺 dm 必 -352 风控。
  - 风控降级：HTTP 非 200（412）或 code≠0（-352）→ 该 uid 记日志跳过，全挂 exit 0
    不拖垮构建；多轮累积收敛（每日 cron 增量）。登录 cookie 属包工头级决策，禁用。
- 抓取纪律沿用 V-03 口径：固定浏览器 UA、stream 分块、解压后字节超 feed_max_bytes
  （读 config.ini [cfg]，默认 50MB）即中止。
- 每日 Auto Build 集成：`.github/workflows/cron-job.yml` 单步 `python bilibili_collect.py`
  （无 LLM env），产出由既有 `git add docs/` 提交。

## 数据契约（前后端唯一接口）

文件 `RSS-GPT/docs/bilibili.jsonl`（随 Pages 发布），一行一个 JSON，按 published
全局倒序。七字段，缺一不入库：

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| bvid | vlist.bvid | BV 号 |
| link | 规范化重建 | `https://www.bilibili.com/video/{bvid}` |
| title | vlist.title | 原文，零 LLM |
| cover | vlist.pic | http→https 升级，限 `i[0-9].hdslb.com` 域，CDN 直链不转存 |
| up_name | vlist.author | |
| uid | 请求 mid | 字符串 |
| published | vlist.created | unix 秒 → RFC 2822 GMT |

禁止字段：summary / title_zh / category / content（独属格式，验收 grep 证明）。
`is_charge_video` 为真（充电专属）不入库；动态/直播/合集由端点本身排除。
日志 `RSS-GPT/docs/bilibili.log`（每 uid 一行计数 + `bilibili: ok X/14, new N`）。

## 前端消费（T-026）

- `web/src/api.js` `fetchBiliVideos()`：独立拉取 bilibili.jsonl，逐行容错 parse；
  **不进 SOURCES**（B站不是资讯源，不出现在资讯源/分类/搜索）。
- `web/src/components/BiliCarousel.vue`：首页轮播（App.vue home 视图顶部，
  `v-if="biliTop10.length"` 空数据不渲染）。合流倒序前 10 条；自动轮播 4s、
  悬停暂停；两侧隐形滑键 hover 显现；标题深色压底；侧边缩略区点击切换。
- 安全口径：标题/up 名文本插值禁 v-html；链接过 `web/src/sanitize.js` `safeLink()`；
  封面 `<img referrerpolicy="no-referrer">`（B站 CDN 防盗链）；裂图占位块兜底。

## 溯源

工单 `docs/T-025.md`、`docs/T-026.md`（含 WBI 签名全参数契约与组长实测记录）；
证据 `D:\vibe-coding\factory-shared\artifacts\T-025\`、`T-026\`。
