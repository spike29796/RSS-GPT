# REQ-七源扩展：AI 主流厂商资讯全覆盖

## 背景
双源（openai-news + claude-blog）跑通后，用户拍板扩展到 AI 主流厂商：
Google / DeepSeek / Kimi / Microsoft / Apple / SpaceX / NVIDIA 共 7 个新源。
昨天（07-29）采集器与配置写完、7 源实测能抓，断在种子数据写入前；
本轮（07-30）补齐收尾并修复实测暴露的三个 bug。

## 需求
1. 新源配置（config.ini source004–010），分类策略按源能力分三档：
   - 官方 tag 直用：google-blog / microsoft-blog / nvidia-blog 开放词表取首个
     有效 tag；apple-newsroom 写死 PRESS RELEASE/UPDATE
   - 源级分类集：spacex-updates（星舰计划/火箭与发动机/星链/航天任务/公司动态）
   - 全局五类 LLM 分类：deepseek-news / kimi-blog（无官方 tag）
   - microsoft-blog 用新键 `ignore_tags` 滤 WordPress 噪声标签（Featured 等）
2. 采集器（collectors.py）：deepseek_news（Docusaurus 侧边栏+正文页）、
   kimi_blog（Next.js SSR 卡片）、spacex_updates（公开 JSON API）；
   共享 helper `_fetch_text` / `_parse_slash_date`。
3. 种子数据：本地无 API key 播种（摘要留空），每日 Actions 按源级
   backfill 预算回填；spacex-updates 本地被 Cloudflare 区域封锁（403），
   本地不播种，由 Actions（美国 IP）首轮自动播种。
4. 前端：SOURCES 加 7 源（league C–I，品牌色 accent）；TAG_ZH 补 Apple
   两个标签映射；开放词表源走英文回退。

## 实测暴露并修复的 bug
- `splitlines()` 把内容里的 U+2028/U+0085 当换行截断 JSONL 记录
  （deepseek/nvidia 真实内容触发）→ e2e_verify + 4 个维护脚本统一改
  `split('\n')`
- main.py 抓取失败且无存量时会写出空 JSONL 并尝试渲染 → 提前 return，
  不留空产物
- microsoft-blog 的 CDN 偶发超时/403 → 重试即恢复，未改码

## 验收（DoD）
- e2e 全绿（mock LLM + 9 源真实抓取；spacex 本地 403 走容错路径）
- 6 源种子 XML/JSONL 入库，validate_categories 通过
  （spacex 未播种显示 SKIPPED，不算失败）
- 前端 9 源卡片/分类面板正常，构建产物进 RSS-GPT/docs
- 线上 Actions 首轮后 spacex-updates 自动播种、各源摘要开始回填

## 边界
- 每源 max_items=3，只抓首页/最新，不翻历史分页
- spacex 本地永不抓（Cloudflare 区域封锁），更新全靠 Actions
- 开放词表源的中文翻译不做映射表（词条不可枚举）
