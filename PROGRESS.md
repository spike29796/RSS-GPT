# PROGRESS 心跳

更新时间：2026-07-29（第二阶段本地完成，待提交推送 + 线上验收）

## 当前步骤
第二阶段三件事（传送带修复 / prompt 结构修复+重试 / 采集器接口+Awwwards SOTD）
本地全部完成，e2e 全绿，待提交 push 并在 fork 手动触发 Actions 验收。

## 已完成
- 第一阶段闭环：脏摘要清理 + 解析兜底修复已上线（dcb11da79）
- 传送带修复：合并后截断 + `docs/<name>.dropped` 墓碑文件，e2e 两轮逐字节幂等
- gpt_summary：格式指令挪 system 消息；解析失败重试 1 次再兜底 None
- 采集器接口：collectors.py 注册表 + output() 分流，主循环零改动
- Awwwards SOTD 源上线（31 条，不调 LLM，源级分类「设计灵感」）
- 验证：test/e2e_verify.py 全绿；validate_categories 四源通过；旧条目零丢失回归
- 文档：REQ-collector.md、BUG-conveyor-belt.md（关闭）、README 2.11/2.12 + 踩坑 14/15、PROG 追加

## 下一步（用户操作）
1. 提交 + push RSS-GPT；外层仓库提交文档与脚本
2. fork 手动触发 Actions 验收：绿色 + 四 feed 可访问 + awwwards 条目正确
   + openai-news 一次性回落到 1000 条（预期）
3. 观察修复后首次真实模型输出的格式遵从率
4. 验收后可删 RSS-GPT-upstream.bak/ 和 deploy.bak/
5. 第三步（另立项）：Vue3 前端 + 聚合展示

## 遇到的问题
- "合并后再截断"治不了传送带（feed 档案 > max_entries 时丢弃集每轮轮换），
  必须配墓碑文件；已更新 BUG 文档与 README 踩坑 15
- 本地 requests 不读系统代理：awwwards 需显式 HTTPS_PROXY，mock 需 NO_PROXY
