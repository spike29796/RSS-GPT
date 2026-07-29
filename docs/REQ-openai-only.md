# REQ-单源 OpenAI：复用官方分类标签 + 官网风卡片

## 背景
用户决定收缩战线：源只保留 OpenAI News，分类直接复用官网 NEWS 标签体系，
卡片信息层级参照 openai.com/news。实测官方 feed（1052 item）每条自带一个
CDATA `<category>`（20 个官方词汇：Company 194 / Research 193 / Product 144 /
Global Affairs 101 / Story 66 / Safety & Alignment 61 / Safety 47 /
OpenAI Academy 30 / Publication 29 / Security 21 / Engineering 16 / API 14 /
AI Adoption 7 / Release 7 / Startup 6 / ChatGPT 5 / Guides 4 / Applied AI 3 /
Webinar 3 / OpenAI on OpenAI 1；最老约 100 条无 tag，兜底为 default_category）。
注：用户本轮已自行更换 CUSTOM_MODEL。

## 需求（用户决策已确认）
1. config 只留 openai-news；qbitai/ithome/awwwards-sotd 段及其 docs/ 数据文件
   （jsonl/xml/log）一并删除，Pages 不再可访问。
2. 条目分类优先采用 feed 自带官方 tag（覆盖 LLM 分类与默认兜底；无 tag 用
   `default_category="Company"`）；LLM 只写一句话中文导读。
   `[source002] categories` 写死 20 个官方词汇作为允许集。
3. 存量 1000 条一次性按官方 feed 重打标（test/retag_official_categories.py），
   LLM 时代五类值全部退役。
4. 前端单源化：去掉赛季/多源概念，顶部导航 = 官方标签 chips（带计数）+ 搜索；
   卡片 = 小号大写 tag → 标题 → 日期 → 中文导读（官网信息层级，纯文本无图，
   深色主题保留）。
5. 回填路径保护已有合法分类（官方 tag 不被 LLM 改写）。

## 验收标准（DoD）
- retag 后 validate_categories 全绿（1000 条全部官方 tag）
- e2e_verify 单源全绿（backfill 5/轮、链接序列稳定、已摘要条目零改写）
- build + 静态模拟 200；线上复核卡片与标签筛选

## 边界
- 不抓 og:image/详情页；官方 description 不入库
- collectors.py 保留（未来源复用），配置不再引用
- 旧三源删除不可逆（git 历史可查）；字母徽章概念废弃
