# PROG-2026-07-28 RSS-GPT 部署

## 做了什么
- 调研上游 yinan-c/RSS-GPT（浅克隆到 `RSS-GPT/` 供参考，未改动）：
  - `main.py` 已是 openai 1.x SDK 写法，`requirements.txt` 已固定 `openai==1.56.2` → README 里 0.27.8 的说法过时，决定不动代码。
  - workflow 使用 `ubuntu-20.04`（已被 GitHub 下线）+ checkout@v3/setup-python@v4，且只剩手动触发 → 需要替换。
  - `main.py:30` 写死 Pages 地址为 `https://<U_NAME>.github.io/RSS-GPT/` → fork 不能改仓库名。
- 验证 RSS 源可用性：
  - 机器之心 `jiqizhixin.com/rss` 已下线（302 → 数据服务付费页），RSSHub 无该路由 → 用户确认用量子位 `qbitai.com/feed` 替代（已验证 200 + 合法 XML）。
  - OpenAI News `openai.com/news/rss.xml`、IT之家 `ithome.com/rss/` 均验证有效。
- 产出可直接粘贴的文件：`deploy/config.ini`（3 源、中文、200 字）、`deploy/cron-job.yml`（ubuntu-latest / checkout@v4 / setup-python@v5 / py3.12 / 每日 UTC 00:17 / commit 兜底）。
- 写部署手册 `README.md`：原理、手动清单（fork/PAT/5 个 secrets/Pages/触发，截图级路径）、10 条踩坑、重装与加源说明。

## 卡在哪
- 无阻塞。用户选择"其他兼容服务"的大模型 API，README 已按通用 OpenAI 兼容接口写，含 DeepSeek/Moonshot/智谱/OpenAI 示例。

## 下一步（用户在 GitHub 网页上执行）
1. 按 README 第 2 节完成 fork、启用 Actions、PAT、secrets、替换 config.ini 和 workflow、开 Pages。
2. 手动触发 cron_job，验证 DoD：Actions 绿色 + Pages 可访问 + 三源有中文摘要。
3. 验收后本阶段完成；后续阶段（前端 Vue3 + Supabase 等）另起 REQ。

---

# PROG-2026-07-28（追加）分类功能

## 做了什么（对应 REQ-category.md）
- 修改 `main.py`：
  - 摘要 prompt 改为"第一行只输出五类之一分类，第二行起 200 字内中文摘要"（中英文分支同步）。
  - 新增 `CATEGORIES` / `DEFAULT_CATEGORY` 常量和 `parse_category_and_summary()`：解析首行分类、剥离"分类："前缀、非法值兜底「行业动态」。
  - `gpt_summary` 返回值改为 `(category, summary)`，三个调用点同步更新并写日志。
  - 每个新条目保证有合法 category（未摘要的兜底默认类）。
  - 顺带修复：fetch UA 从 fake_useragent 随机改为固定 Chrome UA（量子位 403 随机 UA）。
- 修改 `template.xml`：新条目渲染 `entry.gpt_category` 为 `<category>`；旧条目从 `entry.tags` 回渲染，保证跨轮不丢。
- 本地端到端验证（mock OpenAI 服务 + 真实三源，跑两轮）：
  - 3 个 XML 全部 item 有 category 且取值合法；摘要含「总结:」正常生成；
  - 第二轮旧条目分类保留、新条目正常分类；非法分类（科技新闻）被正确兜底。
  - 校验脚本 `test/validate_categories.py`，mock 服务 `test/mock_llm.py`，可重复验证。
- `deploy/` 新增 `main.py`、`template.xml` 供粘贴到 fork；README 增加 2.6.1、2.10 节和踩坑 11-13。

## 踩过的坑（详见 README 踩坑 11-13）
- feedparser 的 FeedParserDict 点号赋值不写字典，`entry.get()` 永远 None → 必须用 getattr（开发中最大一个坑，导致所有分类被兜底覆盖）。
- OpenAI 源 feed 自带 `<category>`，会泄漏进输出 → 自定义属性改名 `gpt_category` 避让。
- 本机系统代理（127.0.0.1:7892）会被 httpx/requests 经 Windows 注册表读取，本地跑要设 NO_PROXY；GitHub Actions 无此问题。
- Windows GBK 默认编码：config.ini 保持纯 ASCII，本地运行需 PYTHONUTF8=1；Actions (Ubuntu) 无此问题。

## 下一步
- 用户在 fork 替换 main.py、template.xml 后重跑 Actions 验收（DoD 最后一项，依赖 secrets 已配置）。

---

# PROG-2026-07-28（追加）第一步：单副本 + JSONL 数据层 + 分类配置化

## 做了什么（对应 REQ-data-layer.md）
- 单副本：`RSS-GPT/` 换成 fork（spike29796/RSS-GPT）的克隆，旧上游克隆和
  `deploy/` 改名为 `.bak` 保留；外层 `.gitignore` 忽略 `RSS-GPT/`、`.venv/` 等。
- JSONL 数据层：`docs/<name>.jsonl` 为事实来源（字段见 REQ）；
  `migrate_xml_to_jsonl.py` 完成存量迁移（1051/73/11 条）；
  `load_entries()` JSONL 优先、XML 自动兜底迁移；先写 JSONL 再渲染 XML。
- 模板合并：`template.xml` 双循环改单循环，渲染字段统一。
- 分类配置化：`[cfg] categories` / `default_category`，支持源级覆盖；
  config.ini 显式 UTF-8 读取；`validate_categories.py` 改从 config 读分类表。
- 数据清理（用户拍板）：删掉无 category 的历史条目 1019 条
  （qbitai 10 / openai-news 949 / ithome 60），下一轮运行会被 feed 重新提供并
  以保证带分类的新条目身份入库。
- 验证（mock LLM + 真实三源，两轮，日志 test/logs/phase1-verify.log）：
  无新文章的源两轮输出逐字节一致；有 category 的旧条目与基线逐条一致；
  `validate_categories.py` 全绿；`compare_feeds.py` 新增为回归工具。
- 文档：README 的 deploy/ 引用全部改指 fork 克隆；新增 REQ-data-layer.md、
  BUG-conveyor-belt.md（传送带效应，上游既有，下一步修）。

## 重要发现
- 旧本地 XML 是 mock 测试产物，生产数据以 fork 为准（此前一次"验收通过"
  实际验的是 mock 数据，教训：验收必须对着 fork 克隆做）。
- 生产上用户自配模型不遵守"第一行只输出分类"的格式 → 真实摘要几乎全部
  落入兜底分类。不影响本阶段（行为保持），第二阶段选模型/prompt 时需正视。
- openai-news 传送带效应（详见 BUG-conveyor-belt.md）。

## 卡在哪
- 无阻塞。fork 仓库两个 commit（数据层、重构+清理）待用户 push
  （权限配置 deny 了 git push，由用户手动执行）。

## 下一步
1. 用户：`git -C RSS-GPT push`，然后在 fork 重跑 Actions 验收（线上 DoD）。
2. 第二步立项：采集器接口 + Awwwards SOTD 爬虫（先做反爬可行性验证）。

---

# PROG-2026-07-29 脏摘要清理 + 解析兜底修复

## 背景
线上验收发现 2026-07-29 Auto Build（4933964ac）生产的 9 条摘要中约 5 条是
垃圾内容：生产模型不遵守"首行分类+总结"格式，且旧兜底策略把整段原始输出
（prompt 回显、思维链、幻觉英文样例文章）原样存入 JSONL 并渲染到公开 XML。
（qbitai 2 条、ithome 3 条、openai-news 1 条传送带重抓旧文）

## 做了什么
- `main.py` `parse_category_and_summary`：解析失败/只有分类没有摘要时兜底返回
  `summary=None`（与摘要失败路径一致，渲染时无摘要 div），原始输出不再进数据层。
- 数据修复：`test/clean_dirty_summaries.py`（一次性）清掉 6 条脏 summary
  （summary→null，content 中同步剥离 `<div> summary <div>` 前缀）。
- `test/rerender_xml.py`：不抓 feed、不调 LLM，直接从 JSONL + template.xml
  重渲染 3 个 XML。验证：用脏 JSONL 重渲染结果与 HEAD 逐字节一致（幂等），
  再用干净 JSONL 重渲染，diff 恰好只触及 6 个 item（共删约 805 行垃圾）。
- 验证：`validate_categories.py` 全绿；parse 兜底单测断言通过；main.py 编译通过。

## 发现
- 脏输出含多轮对话痕迹（"上面这个总结是你上次生成的，请你重新生成"），
  疑似所用 OpenAI 兼容服务存在上下文串联，第二阶段选服务/模型时需验证。
- openai-news 已回到 1052 条（949 条无分类历史被 feed 全量重新提供，属清理时
  的预期行为）；传送带 BUG 依旧，第二阶段按 BUG 文档修。

## 下一步
- 提交并 push 后线上 XML 即恢复干净；之后正常进入第二阶段
  （调教模型输出格式 + 修传送带 + Awwwards 采集器）。

---

# PROG-2026-07-29（追加）第二阶段：传送带修复 + prompt 修复 + Awwwards 采集器

## 做了什么（对应 REQ-collector.md）
- **传送带修复**（BUG-conveyor-belt.md 关闭）：先按原建议只把截断移到合并后，
  e2e 第二轮 openai-news.jsonl 仍变（被截断的 51 条 2017 年旧文重抓置顶还抢了
  3 个 mock 摘要额度）——证明"合并后再截断"治不了本。加墓碑文件
  `docs/<name>.dropped` 记录被截断丢弃的链接、去重视为已见，才真正幂等。
- **gpt_summary**：格式指令从 assistant 消息挪到 system 消息（zh/en 同步）；
  解析失败重试 1 次再兜底 summary=None。
- **采集器接口**：新增 `collectors.py`（COLLECTORS 注册表，返回 feedparser
  兼容伪 feed）；`output()` 按源段 `collector` 键分流，主循环零改动。
- **Awwwards SOTD**：裸 GET + 解析 `data-collectable-model-value` 内嵌 JSON
  （31 条，slug/title/createdAt/tags/缩略图）；不调 LLM，源级分类/兜底
  「设计灵感」（`get_default_category` 扩展源级覆盖）。缩略图 CDN 两种尺寸
  均实测 200。
- `validate_categories.py`：allowed 并入源级 categories 覆盖；采集器源
  （读 config 的 collector 键）豁免"至少一条摘要"检查。
- 验证工具：`test/e2e_verify.py`（拷贝仓库到临时目录跑两轮，生产 docs/ 零接触）。

## 验证（e2e 全绿）
- run1 干净（无脏摘要），run2 逐字节幂等（传送带盖棺）；
  直接调 gpt_summary 7 次全覆盖 mock 周期，重试断言通过；
- validate_categories 四源全过（awwwards-sotd 31 条全「设计灵感」、summary 豁免）；
- 旧条目回归：HEAD 三源链接零丢失（openai-news 少的 52 条 == 墓碑集合）。

## 踩过的坑
- 本机 requests 不读系统代理：awwwards 直连超时，需显式 HTTPS_PROXY；
  mock LLM 需 NO_PROXY 保住（README 踩坑 14）。
- feed 抓取失败时 `feed=None` 会导致渲染被跳过（上游既有行为），首次部署
  采集器源务必保证首抓成功。

## 下一步
- 提交 RSS-GPT（main.py/collectors.py/config.ini）+ push；用户在 fork 手动
  触发 Actions 验收：绿色 + 四 feed 可访问 + awwwards 条目正确 +
  openai-news 一次性回落到 1000（预期）。
- 观察修复后首次真实模型输出格式遵从率（system 消息 + 重试的效果）。

### 线上热修（2026-07-29）：Actions 上 awwwards 抓取失败
- 现象：Actions 绿色但 awwwards-sotd 空 feed，log 报 `Errno 101 Network is
  unreachable`（TCP 层，非 403）。
- 根因：awwwards 有 AAAA 记录而 Actions runner 无 IPv6 路由，首个连接即
  ENETUNREACH。本机有 IPv6/代理所以 e2e 没暴露。
- 修复：`collectors.py` 强制 IPv4（AF_INET-only getaddrinfo 包住请求），
  b420de885 已 push；README 踩坑 16。

---

# PROG-2026-07-29（追加）第三阶段：Vue3 前端聚合页

## 做了什么（对应 REQ-frontend.md）
- 决策（用户）：纯静态无后端（弃 Supabase）、同 repo 同 Pages、首版浏览聚合、
  Vue 应用替换旧 RSS 链接列表首页。
- 管道让出入口：`main.py` 链接列表页改渲染 `docs/feeds.html`，index.html 留给
  前端产物（消除了"每日 Auto Build 覆盖应用入口"的冲突）。
- 新建 `web/`（Vite5 + Vue3 SFC，无 TS/router/UI 库）：
  - `vite.config.js` base `/RSS-GPT/`、outDir `../RSS-GPT/docs`（emptyOutDir=false
    保护数据文件）、dev proxy 到线上 Pages 取真数据；
  - `api.js` 并行 fetch 四源 JSONL、Promise.allSettled 单源容错；
  - `App.vue` 源 tabs + 动态分类 chips + 搜索 + 50 条/批加载更多 + RSS 订阅页脚；
  - `EntryCard.vue` 分类徽章/来源/时间/摘要(v-html)/Awwwards 缩略图。
- 构建产物（index.html + assets/）已写入 RSS-GPT/docs；本地用 template.html
  预生成 feeds.html 避免部署后页脚 404。
- 验证：build 成功（gzip js 27KB）；python http.server 模拟 Pages 五个关键
  资源全 200；e2e_verify.py 两轮全绿（管道改动无回归）。

## 踩过的坑
- `vite preview` 也会应用 server.proxy，本机直连 github.io 被重置导致 500，
  本地验收改用 python http.server 模拟 Pages 静态服务。
- node 在 `C:\Program Files\nodejs` 但不在 bash PATH（PATH 里的 /d/nodejs 是
  失效残留），用时要 `export PATH="/c/Program Files/nodejs:$PATH"`。

## 下一步
- 提交外层（web/ + 文档）与 RSS-GPT（main.py + 构建产物 + feeds.html）并 push；
  用户线上验收：Pages 首页即应用、筛选/搜索/缩略图/手机可用。

### 线上验收修复（2026-07-29）：前端三问题 + 摘要回填
- 用户验收反馈：①大部分卡片无摘要（数据现实：只有每天每源最新 3 条有），
  个别卡片显示 prompt 碎片；②图片加载失败时 alt 重复标题；③布局过窄拥挤。
- 数据：残留 3 条上游时代 prompt 碎片（前一轮清理的启发式没覆盖短碎片），
  `clean_dirty_summaries.py` 扩展指令正则后再清 3 条并重渲染 XML，diff 恰好 3 item。
- 前端：图片 `alt=""` + `@error` 隐藏；容器 760px→1600px，卡片流改
  auto-fill 多列网格（900px 两列 / 1400px 三列），移动端仍单列。
- 回填（用户决策，REQ-summary-backfill.md）：`backfill_days`/`backfill_items`
  源级配置，每轮独立预算为最近 N 天未摘要条目补摘要（最新优先、跳过不合规、
  不改条目集合与顺序）；qbitai 7天/5条、ithome 3天/10条，openai-news 不开。
- e2e 语义适配：链接序列两轮一致 + 已摘要条目零改写 + 无 backfill 源 XML
  逐字节一致 + backfill 源每轮新增摘要 >0。结果：run2 恰好回填 15 条
  （预算 5+10），qbitai 窗口内 12/12 全覆盖，全绿。

---

# PROG-2026-07-29（追加）第四轮：赛季/流派 UI + 一句话导读 + Awwwards 分类体系

## 做了什么（对应 REQ-league-ui.md）
- 管道：gpt_summary 改一句话导读（≤50字、不分点、保留 总结: 标记，zh/en 同步）；
  摘要输入 prepend 标题（新条目+回填两处）；summary_length 200→50。
- config：openai-news 开回填 7天/5条；awwwards-sotd max_items=5、独立五分类
  （榜单发布/优秀工作室/技术展示/视觉风格/行业资讯）、backfill 30天/10条。
- 一次性 refresh_summaries.py：窗口内旧长摘要置 null（qbitai 1、ithome 7）、
  awwwards 旧「设计灵感」31 条全部重置为「行业资讯」，XML 重渲染。
- mock_llm 重写：从请求 system 指令解析分类列表自适应返回，第 6/7 个响应
  仍测非法/前缀变体 → awwwards 摘要链路首次可被 e2e 覆盖。
- 前端深色游戏风双视图：首页=赛季卡片（A/C/D 徽章+条目数，B 预留）+
  各源热门分类（top3 计数+占比）；列表视图深色化、卡片加源字母徽章、
  导读最多两行截断（过渡期长摘要兜底）。rerender_xml 补 awwwards（此前漏了）。

## 验证
- e2e 全绿；validate：设计灵感清零（qbitai/ithome 摘要清零为预期过渡态，
  回填恢复）；build + 静态模拟 4 资源 200。
- 坑：Git Bash 的 ln -s 在某些环境是"复制"而非软链，静态模拟serve的是旧快照，
  重建链接后正常。

---

# PROG-2026-07-29（追加）第五轮：单源 OpenAI + 官方标签 + 官网风卡片

## 做了什么（对应 REQ-openai-only.md；用户已自行更换 CUSTOM_MODEL）
- 实测官方 feed：1052 item、952 条带 CDATA `<category>`（20 个官方词汇，
  分布已记入 REQ）、无图；最老约 100 条无 tag → default=Company。
- 管道：新条目分类官方 tag 优先（覆盖 LLM/兜底）；回填保护已有合法分类；
  config 单源化（删 source001/003/004）；旧三源数据文件 git rm。
- 一次性 retag_official_categories.py：1000 条全部重打官方标
  （900 直接映射 + 100 无 tag 兜底），validate 全绿。
- 前端：去赛季化单源列表；官方标签 chips（带计数）；卡片=大写 tag→标题→
  日期→中文导读；深色保留。rerender/validate 的 FEEDS 同步单源。
- e2e 单源全绿（run2 稳定、回填正常、validate 过）。

## 下一步
- 提交 push；用户线上复核 + 触发 Actions 观察新模型的导读格式遵从。

### 推送时冲突与新模型观察（2026-07-29 补）
- push 撞上 08:45 Auto Build（带新模型的一轮回填）：UD 冲突删旧三源、
  UU 取远端 jsonl 保留新摘要，重跑 retag+rerender 后 amend 推上。
- **新模型格式遵从 5/7**：两条脏摘要（prompt 碎片/示例回显）已清并留给
  回填重试；clean_dirty_summaries 正则补「除此之外|示例：」。
  观察：指令遵循仍是主要失败模式，兜底 None + 回填重试机制兜底有效。

---

# PROG-2026-07-29（追加）第六轮：档案全补齐 + 双语主题 + 一键翻译 + 模糊搜索

## 做了什么（对应 REQ-i18n-theme.md）
- 全补齐：backfill 3650天/50条（~20 天补完 990 条档案）。
- 三行格式：prompt 加"第三行标题中文翻译"；parse 返回三元组；记录加
  title_zh 字段；回填资格扩展为"无摘要或无 title_zh"（9 条存量随队补译）。
- 前端：CSS 变量双主题（首帧内联脚本跟随系统，☀️/🌙 记忆）；头部"译"按钮
  （title_zh 回退原文，标签内置 20 词映射）；Fuse.js 双语模糊搜索。
- e2e：三行断言 + title_zh 存在性 + 补译不算改写；全绿（3 轮补 91 条）。

## 本轮摘要问题排查链（存档）
- PAT 过期 → checkout 失败；api.kimi.com/v1 不存在（正确：api.moonshot.cn/.ai
  或 api.kimi.com/coding/v1）；模型名大小写敏感（kimi-k2.6）；kimi-for-coding
  是编程订阅专用。最终配置=api.moonshot.cn/v1 + kimi-k2.6。
- kimi-k2.6 实测格式遵从约 5/7 → 加标记归一化（尾部 总结: 前移/缺省补）
  后全部可用；前端卡片摘要以 <br><br> 开头吃掉 line-clamp 两行额度显示成
  "..."，改渲染时剥标记 + 绿色导读标签。

### UI 细调（2026-07-29 补，Playwright 截图驱动）
- 配置：~/.kimi-code/mcp.json 已写 Playwright MCP（重启或 /mcp 生效）；
  本轮调试用 web/scripts/ui_shots.mjs（本地静态服务 + chromium 截图，
  覆盖双主题 × 1600/390 宽 × 单/多源）。
- 多源模拟（git 历史恢复旧三源 jsonl + 临时 4 源构建）：首页赛季卡/热门分类
  网格自动换行不错位，验证通过。
- 修复：卡片大小不一（.list 误用 align-items:start → 改 stretch + 卡片
  height:100%，同行等高）；test-shots/ 加入 gitignore。
- 用户确认译题覆盖路径：backfill 临时 300/天（5d2639869），铺满后调回 50。

---

# PROG-2026-07-29（追加）Claude Blog 源接入（REQ-claude-source.md）
- 采集器：collectors.py 新增 collect_claude_blog（bs4 解析 Webflow 卡片，
  dedupe by link，手工月份表避 Windows locale 坑），单测 15 条通过。
- config source003（claude-blog，5 官方标签，backfill 30天/10条）；
  前端 B 徽章+品牌橙，TAG_ZH 补 5 词。
- 播种：本地无 API key 跑一轮 main.py 生成 15 条种子（summary 留空待回填），
  README/feeds.html 双源化（sed 修 U_NAME 缺省产生的 None.github.io）。
- e2e：预算限速（生产 300 配置会让 e2e 跑 900 次 mock 超 600s，临时改 5）+
  新源基线兼容（snap0 无 claude-blog.jsonl），双源全绿。
- 截图验证：首页双源卡片并排、热门分类双列、移动端正。

### 首页对齐与按源过滤修复（2026-07-29 补）
- 用户抓出两 bug：①热门分类网格（minmax 280）与源卡片网格（minmax 340）
  轨道不一致没对齐 → .classes 改同 340 轨道，分类板块与上方源卡片逐列对齐；
  ②单源改造时误删按源过滤，加回第二源后点 Claude 卡片进的是混合列表 →
  恢复 activeSource 状态：点谁进谁，面板新增"资讯源"切换组（带源色圆点），
  标签计数/搜索范围随源收窄。截图脚本加"点第二张源卡"用例，v5 截图验证通过。
