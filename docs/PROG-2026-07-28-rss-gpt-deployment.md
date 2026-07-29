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
