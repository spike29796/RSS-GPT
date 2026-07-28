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
