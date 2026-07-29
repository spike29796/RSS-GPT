# REQ-双语主题 + 一键翻译 + 模糊搜索 + 档案全补齐

## 背景
前端只剩单源 OpenAI News 后，用户提出四项增强：历史档案导读全部补齐、
浅色日间主题（现行深色作夜间）、一键翻译标题和标签、词意级模糊搜索。

## 需求（用户决策已确认）
1. 档案全补齐：`backfill_days=3650`、`backfill_items=50`，约 20 天补完
   ~990 条，成本认可。
2. 翻译走管道：摘要输出改三行格式（分类/导读/标题中文翻译），解析返回
   `(category, summary, title_zh)`；记录新增 `title_zh` 字段；回填资格扩展为
   「无摘要 或 无 title_zh」（存量 9 条好摘要随队补译，不丢数据）。
   标签翻译用前端内置映射（20 个官方词写死，`web/src/i18n.js`），新增官方
   tag 需同步字典，未命中兜底原文。
3. 主题：CSS 变量双主题，首次访问跟随系统 prefers-color-scheme（index.html
   内联脚本首帧前设置 data-theme），头部 ☀️/🌙 切换并 localStorage 记忆。
4. 一键翻译：头部"译"按钮（localStorage 记忆），卡片/预览标题用
   `title_zh || title`，标签走映射；未译条目静默回退原文。
5. 搜索：Fuse.js（keys: title/title_zh/summary/category/category_zh，
   threshold 0.3，ignoreLocation），替代 includes 过滤，双语可搜。

## 验收标准（DoD）
- e2e 全绿：三行格式解析/重试断言、补译不算改写已摘要条目、
  回填按基线增量 >0（窗口 3650 后 remaining>0）
- build 通过（Fuse 打入包内约 +11KB gzip）；静态模拟资源 200
- 线上复核：主题切换、翻译切换、模糊搜索中英均可

## 边界
- 不做 embedding 语义搜索；翻译不调用运行时 API（纯数据驱动）
- en 分支 prompt 同步三行格式（译题为管道语言）
- 档案补齐期间每天 50 次 LLM 调用为预期成本
