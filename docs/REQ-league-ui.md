# REQ-赛季/流派 UI + 一句话导读 + Awwwards 分类体系

## 背景
前端首版验收反馈：摘要太长像小正文、openai/awwwards 基本无摘要、
awwwards 没有自己的分类、布局不符合预期。用户指定参照 poe.ninja
（布局.png：Available Leagues + Top Classes Per League）重做信息架构：
**资讯源 ↔ 赛季（字母徽章 A/C/D，B 预留），分类 ↔ 赛季流派**。

## 需求（用户决策已确认）
1. 深色游戏风复刻：首页 = 赛季分组卡片（徽章+源名+条目数）+ 各源热门分类
   （top3 计数+占比，点击进过滤列表）；列表视图沿用筛选/搜索/卡片/分页。
2. 摘要改一句话导读（≤50 字，不分点，保留 `<br><br>总结:` 标记）；
   摘要输入带标题（采集器源正文只有 Tags，必须给标题）。
3. 已有长摘要逐步重生成：一次性脚本把窗口内旧长摘要/失效分类重置为
   待摘要状态，每日回填换血。
4. Awwwards 启用独立分类集（榜单发布/优秀工作室/技术展示/视觉风格/行业资讯），
   条目走 LLM 分类+导读（max_items=5，backfill 30天/10条覆盖存量 31 条）。
5. openai-news 开回填（7天/5条，档案不碰）。
6. 源字母映射：openai-news=A、awwwards-sotd=C、qbitai/ithome=D（主流平台），
   B 预留给未来新源；本轮不加源。

## 验收标准（DoD）
- e2e_verify 全绿（mock 自适应源分类集，awwwards 摘要链路可验）
- refresh 后 validate_categories：awwwards 旧「设计灵感」清零
  （qbitai/ithome 摘要短暂清零属预期，回填恢复）
- build + Pages 静态模拟资源 200；线上复核深色首页与一句话导读

## 边界
- 不加新源；不做趋势箭头/真实涨跌（占比是静态计数）
- openai-news 超窗档案永不回填；长摘要不保留（直接换格式）
