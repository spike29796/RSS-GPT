# REQ-采集器接口 + Awwwards SOTD 采集器

## 背景
第二阶段立项（前序：REQ-data-layer.md 的 JSONL 数据层）。目标是为管道接入
非 RSS 来源，首个采集对象为 Awwwards Site of the Day（无官方 feed/API，
RSSHub 无路由）。经调研：SOTD 列表页服务端渲染，每个 `<li>` 的
`data-collectable-model-value` 属性内嵌 JSON（slug/title/createdAt/tags/
images.thumbnail），裸 GET + 浏览器 UA 即可解析，无需 headless。

## 需求
1. 采集器接口：`collectors.py` 注册表 `COLLECTORS`；config.ini 源段用
   `collector` 键声明采集器，`url` 键作为采集目标。采集器返回
   feedparser 兼容的伪 feed，主管道（去重/分类/JSONL/XML 渲染）零改动。
2. Awwwards SOTD 采集器：解析列表页内嵌 JSON，产出条目
   （link=`/sites/<slug>`、title、published=createdAt、content=缩略图+标签）。
3. Awwwards 条目文本量少，不调 LLM（max_items=0），源级分类覆盖为
   「设计灵感」（用户决策）；不抓详情页分数/票数（用户决策，后续可加）。
4. 源级 `default_category` 覆盖（与 categories 覆盖同模式），避免非 AI
   内容落入「行业动态」。
5. `validate_categories.py` 支持源级 categories 覆盖；采集器源豁免
   「至少一条摘要」检查。

## 同阶段顺带修复
- 传送带 BUG（BUG-conveyor-belt.md）：截断移到合并之后 + 墓碑文件
  （`docs/<name>.dropped`）记录被截断丢弃的链接，防止 feed 仍提供的
  旧档案被当作新条目重抓。
- `gpt_summary`：格式指令从 assistant 消息挪到 system 消息（上游遗留写法
  是格式遵从差的主因）；解析失败重试 1 次再兜底 summary=None。

## 验收标准（DoD）
- `test/e2e_verify.py` 全绿：mock LLM + 真实四源连跑两轮，第二轮幂等
  （同时证明传送带修复）；重试断言通过；validate_categories 通过。
- `docs/awwwards-sotd.jsonl/.xml` 生成：条目 category 全为「设计灵感」、
  summary 为 null、content 含缩略图。
- 三 RSS 源旧条目回归一致（openai-news 因截断修复一次性回落到 1000 条，
  属预期）。
- 用户 push 后在 fork 手动触发 Actions：绿色 + 四个 feed 可访问。

## 边界
- 不抓详情页、不上 headless、不加新 pip 依赖。
- 不动 workflow、template.html、helper.py；不改 openai SDK 版本。
- 不做跨源去重/搜索/前端（第三步）。
- 模型真实输出改善以修复后首次 Actions 运行观察为准（本地无生产 secrets）。
