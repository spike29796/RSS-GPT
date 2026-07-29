# REQ-Claude Blog 源接入（采集器 + 官方标签复用）

## 背景
用户指定新增 https://claude.com/blog 作为第二源（B 徽章位）。实测：无 RSS
（rss.xml/feed 全 404），但 Webflow 服务端渲染，卡片 `.card_blog_wrap`
含标题/日期/链接/官方 tag/封面插画，裸 GET 可解析，无需 headless。

## 需求
1. `collectors.py` 新增 `collect_claude_blog`（bs4 解析卡片，dedupe by link
   ——Webflow grid+list 双渲染同卡两遍；日期 "Jul 28, 2026" 手工月份表解析，
   避开 Windows 中文 locale 的 strptime 陷阱）；卡片 tag 写入 entry.tags，
   复用 main.py「官方 tag 优先」分类逻辑。
2. config `[source003]`：name=claude-blog、collector=claude_blog、max_items=3、
   categories 写死首页实测的 5 个官方标签（Product announcements / Enterprise
   AI / Claude Code / Agents / eBook）、default=Product announcements、
   backfill 30天/10条。
3. 前端：SOURCES 加 Claude Blog（league B，accent 品牌橙 #d97757）；
   TAG_ZH 补 5 词映射。
4. 摘要与译题走三行格式 LLM（与 openai-news 同链路）；正文=插画+Tags 文本。

## 验收（DoD）
- 采集器单测：解析 15 条去重正确（标题/日期/tag/链接/插画）
- e2e 双源全绿（claude-blog 15/15 带摘要、官方 tag 入库、openai 无回归）
- 首页双源卡片并排不错位（截图验证）；生产种子数据 15 条已入库
  （无 API key 播种，摘要留空待回填）

## 边界
- 只抓博客首页（约 15 篇），不翻历史分页；归档靠每日增量累积
- 卡片不显示封面插画（与 OpenAI 卡片风格一致），content 里保留备用
- "3 板块"分组面板不做（用户拍板就用扁平 5 标签）
