# REQ-数据层重构：单一代码副本 + JSONL 数据层 + 分类配置化

## 背景
三步方案第一步（后续：Awwwards 采集器 → Vue3 前端）。改造前存在双副本问题
（`deploy/` 与 `RSS-GPT/` 内容相同、需手工同步），且生成的 XML 既是存储又是
展示，无法支撑后续搜索/聚合。

## 需求
1. 全仓库只留一份代码：`RSS-GPT/` 改为 fork（spike29796/RSS-GPT）的 git 克隆，
   删除 `deploy/` 和上游参考克隆（保留 .bak 至验收完成）。
2. JSONL 数据层：`docs/<name>.jsonl` 为唯一事实来源，每行一条
   `{link, title, published, updated, category, summary, content}`；
   每次运行先写 JSONL，XML 从统一条目渲染。JSONL 放在 `docs/` 下，
   workflow 的 `git add docs/*` 自动提交，Pages 可直接访问（第三步前端用）。
3. 存量迁移：`migrate_xml_to_jsonl.py` 从既有 XML 生成 JSONL；
   `load_entries()` 在 JSONL 缺失时自动从 XML 迁移兜底。
4. 分类配置化：`[cfg] categories` + `default_category`，支持源级覆盖；
   config.ini 显式按 UTF-8 读取（Windows GBK 坑）。
5. 数据清理（用户决策）：删除 JSONL 中无 category 的历史条目（1019 条，
   分类功能上线前产生）。各源 feed 仍会提供其中大部分，下一轮运行会作为
   新条目重新入库并保证带分类。

## 验收标准（DoD）
- 全仓库只剩一份 main.py / template.xml / config.ini，remote 指向 fork
- 本地 mock LLM 连跑两轮无报错；无新文章的源两轮输出逐字节一致（幂等）
- 旧条目（有 category 的）在重构后输出与基线逐条一致
- `test/validate_categories.py` 通过（每个 item 有合法 category）
- 改 config.ini 的分类集合能改变校验与兜底行为
- 用户 push 后在 fork 重跑 Actions 绿色

## 边界
- 不做跨源去重、不做 embedding/搜索（后续阶段）
- 不改 openai SDK 调用方式、不加新依赖
- 不动 helper.py、template.html、workflow 文件
- openai-news 源「最老 51 条被截断后重新抓取」是上游既有行为（传送带效应，
  见 BUG-conveyor-belt.md），本阶段不修
