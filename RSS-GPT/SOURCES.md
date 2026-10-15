# RSS-GPT 源决策记录

这里放每个源的来龙去脉：为什么上、为什么下、参数改过什么、想恢复怎么恢复。
`config.ini` 只放生效的配置。理由写在那边会把配置文件变成编年史。

恢复任何一个下线的源：把下面那节的参数块整段复制回 `config.ini`，去掉前面的 `# `。

---

## 一、生效配置的调整记录

### backfill_max_minutes

- 2026-09-25：25 分钟改 40 分钟。原来 25 分钟只够处理约 130 条，英文源积压（arxiv-ro 995 条、hackernews 213 条）永远补不完。workflow 的 job 上限同步由 45 提到 90 分钟留余量。
- 2026-10-09：40 分钟改 0。大卫要求不再设上限，跑到全部处理完为止。

### 上限为 0 的含义

`max_items="0"` 和 `backfill_max_minutes="0"` 都是「不设上限」，不是「不抓」。

---

## 二、曾下线、现已恢复

### openai-news（`[source002]`）

**T-044（2026-09-14）下线判据**：大卫判定「1000 条感觉都没意义，直接不收录」。

实测数据（1000 条 / 年份分布）：
- 2026 年 407 条，2025 年 332，2024 年 164，2023 年 66，2022 年 31
- 不是「全是老数据」，而是两个问题叠加：
  1. **量**：一个源攒了 1000 条（别的源 20-60 条），把页面全淹了 —— 与 IT之家 同一个病：单源压倒全部。
  2. **性质**：内容多为公司宣传（合作 / 政策 / 人事 / 发布），非技术实操 —— 所以即便日期新，也拿不到「能马上用」。

根因：它的 `backfill_days="3650"`（10 年）→ 历史条目一路累积到 1000 上限。

**已知代价**：一手发布（GPT-6 Astra / Agents API 等）一度不再进站。

**现状**：已恢复启用，`backfill_days="3650"` 保留，靠上面的 `max_items="0"` 和每日增量控制量级。

---

## 三、已下线的源

### T-040 IT之家（2026-09-14）

**判据**：大卫用站点的意图标注系统给当日条目打分，结论「IT之家 99% 是垃圾信息」。

数据佐证（120 条抽样）：含 AI 关键词仅 20.8%，且其中半数是伪 AI（vivo 开发者大会 / 核电站造假 / 外交部表态 / 清洁机器人出货量）；消费电子、汽车、硬件类占 45%。对比 qbitai 90%、openai-news 94.3% 含 AI 词。

想恢复：数据可从 git 历史取回，参数块见下。

```ini
# [source007]
# name="ithome"
# url="https://www.ithome.com/rss/"
# max_items="5"
# default_category="行业动态"
# backfill_days="30"
# backfill_items="80"
```

### T-047 Simon Willison（2026-09-14）

**判据**：大卫的意图标注里，该源 7 条全部标「与我无关」（0 正例）。

内容性质：多为版本号更新（llm 0.35 / datasette 1.0a39）与纯引用帖（Quoting XXX），属于「能装但我不装」那一类。

**注意**：样本仅 7 条，是全站里样本量最小的下线决定。

```ini
# [source004]
# name="simonwillison"
# url="https://simonwillison.net/atom/everything/"
# max_items="5"
# default_category="行业动态"
# backfill_days="30"
# backfill_items="80"
```

### T-047 Product Hunt（2026-09-14）

**判据**：大卫的意图标注里，该源 12 条全部标「与我无关」（0 正例）。

内容性质：产品发布页（多为冷门小工具），既非技术实操，也非他关注的方向。

**这是样本量最充分的一次下线判断**（12 条 0 命中）。

```ini
# [source008]
# name="producthunt"
# url="https://www.producthunt.com/feed"
# max_items="5"
# categories="产品应用,开源项目,行业动态"
# default_category="产品应用"
# backfill_days="30"
# backfill_items="80"
```

### T-048 arXiv cs.AI（2026-09-14）

**判据**：两轮云端抓取都是 0 条（其余 9 个新源全部成功），大卫判定不要。

**注意**：arxiv-ro（cs.RO 机器人）当时是好的（93 条），只下线 cs.AI 这一栏。

```ini
# [source018]
# name="arxiv-ai"
# url="http://export.arxiv.org/rss/cs.AI"
# max_items="5"
# default_category="模型发布"
# backfill_days="30"
# backfill_items="80"
```

### T-048 HuggingFace Blog（2026-09-14）

**判据**：大卫判定不要。数据佐证：862 条（其余源 10-93 条）—— 单源条目量压倒全部，与 ithome / openai-news 同一种病；且 862 条里只有 3 条有摘要（backfill 时间预算只有 25 分钟，历史条目摘要不过来，按每天 5 条要补 172 天）。

想恢复：建议同时把 `backfill_items` 调小。

**编号说明**：该源原写作 `[source020]`，与现行的 `arxiv-agent` 撞号。已在此处改记为 `[source024]`（未占用编号），避免恢复时顶掉 arxiv-agent。

```ini
# [source024]
# name="hf-blog"
# url="https://huggingface.co/blog/feed.xml"
# max_items="5"
# default_category="模型发布"
# backfill_days="30"
# backfill_items="80"
```

### T-053 arXiv cs.RO 全量 RSS（2026-09-29）

**判据**：实测 1000 条顶格、988 条从未处理、日均新增 91 条、127 条在重试队列反复失败（bad_output 104 / api_error 23），三天净处理 3 条。

根因三条：
1. RSS 是全量推送，cs.RO 日均 90+ 篇；
2. `_llm_deadline()` 按剩余源数均分 40 分钟预算，它是第 11 个源 → 每轮仅约 3 分钟；
3. 上限 1000 条 → 每天挤掉约 90 条旧论文。

**处理方式**：换成 arXiv API 主题源（现行 `[source020]`~`[source023]`）。

```ini
# [source017]
# name="arxiv-ro"
# url="http://export.arxiv.org/rss/cs.RO"
# max_items="5"
# default_category="模型发布"
# backfill_days="30"
# backfill_items="300"
```

（`backfill_items` 2026-09-25 由 40 改 300：它一家占了缺口一半，995/1792 条，按每轮 40 条要补 25 天。）

---

## 四、T-053 arXiv 换源的设计（2026-09-29）

现行四个 arXiv 源的共同约定：

- **抓取**：`sortBy=submittedDate` 最新优先，`max_results=40`（抓 40 条）
- **处理**：`max_items="0"` 不设上限，靠每日增量控制
- **不做 backfill 抢预算**：`backfill_days="14"`、`backfill_items="500"`
- **ignore_tags**：挡掉 arXiv 的 cs.* 标签，否则会覆盖 LLM 挑的中文分类

---

## 五、T-041 源类型扩充（2026-09-14）

**依据**：大卫用意图标注跑出 84 条数据 → 「能马上用」0 条。

**根因不是他不用，是源全是新闻媒体** —— 新闻产出「发生了什么」，天然只能被标「只需知道 / 与我无关」，永远拿不到「能马上用」。

所以这一批加的是能直接动手的类型：代码（GitHub Trending）、论文（arXiv）、实操讨论（HN / Lobsters / r/LocalLLaMA）、技术博客（Lilian Weng / The Gradient）。

**每源限量**：ithome 的教训是它 120 条淹没了所有其他源，让人以为「整站都是垃圾」。所以新源都限量，保持各源量级均衡。
