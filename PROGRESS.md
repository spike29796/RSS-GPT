# PROGRESS 心跳

更新时间：2026-07-30（第二轮摘要修复：公平份额+并发3+spacex 去重 bug）

## 当前步骤
首轮修复后 Actions 落盘 10 条摘要（零丢失达成），但 openai 吃光全部
25 分钟预算（API ~2.7min/次），其余 8 源零回填；spacex 28 条因上游
find() 恒真条件砍 #fragment 只剩 1 条。第二轮：预算按源均分、回填并发 3、
耗时日志、spacex 种子重播。e2e 全绿，待推送后手动触发 Actions 复验。

## 已完成
- 第一~三阶段、第六轮、Claude Blog 源（见 git 历史）
- 七源扩展（RSS-GPT 1925f554d）
- 摘要空跑修复第一轮（096db23bc）：时间预算/超时重试/job 上限
- 第二轮（待推送）：_llm_deadline 公平份额、回填并发 3、
  find() 恒真砍 fragment 修复（spacex 去重车祸根因）、
  spacex 错误种子删除待重播、contentBlocks 噪声过滤

## 下一步（用户操作）
1. 推送后手动触发 Actions → 看 Auto Build：9 源应各有摘要进账、
   spacex-updates 28 条入库、日志带 "Backfilled in Ns" 耗时
2. 若 API 仍 ~3min/次：每轮约 27 条（9 源×3），属正常；想提速只能
   换快的中继/模型，或加大 backfill_max_minutes（≤40）
3. 若 404 仍高发：检查 CUSTOM_MODEL/OPENAI_BASE_URL 中继渠道

## 遇到的问题
- spacex 本地 403 为预期，靠 Actions 播种；validate/e2e SKIPPED 不算失败
- microsoft/google 的 CDN 本地偶发超时/403，重跑即恢复（幂等）
- 外层仓库无远程，仅本地提交
