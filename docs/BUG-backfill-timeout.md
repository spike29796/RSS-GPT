# BUG-backfill-timeout：6 小时空跑烧 token，摘要零产出

状态：**已修复**（2026-07-30）

## 现象
2026-07-29 手动触发 Actions 跑 openai-news 档案回填（backfill_items=300），
job 跑满 6 小时被 GitHub 强杀：token 额度烧完，仓库里一条新摘要都没有
（docs/openai-news.jsonl 长期只有 ~12 条带摘要）。

## 根因（双重）
1. **无时间预算**：300 条/轮 × 每条最多 2 次调用，叠加缓慢/抖动的 API，
   整轮轻松超过 Actions 单 job 6 小时硬上限。摘要只在内存里累积，
   `Commit and push` 步骤在 job 被杀时根本没执行——产出全丢。
2. **API 抖动无重试**：上游中继间歇返回 404 resource_not_found
   （同一条目这轮失败下轮成功，日志为证）。gpt_summary 只对"格式不合规"
   重试，API 异常直接跳过该条目，且客户端无超时（SDK 默认 10 分钟），
   进一步拉长整轮时间。

## 修复（已落地）
- `main.py`
  - `[cfg] backfill_max_minutes`（默认 25 分钟）总时间预算：预算耗尽即
    停止一切 LLM 调用（回填+新条目内联摘要都受控），正常落盘提交，
    剩余条目下轮继续（回填本来就幂等、最新优先）
  - gpt_summary：单请求 `timeout=120`，API 异常也重试一次（间隔 5s）
- `cron-job.yml`
  - job `timeout-minutes: 45` 硬上限（软预算的兜底）
  - `Commit and push` 步骤 `if: always()`：Generate 失败/超时也提交
    已落盘的部分进度

## 验证
- 冒烟测试：backfill_max_minutes=0.001 时一轮完成、0 条新回填、
  日志有 "time budget exhausted"、1000 条档案完好
- `test/e2e_verify.py` 全绿无回归

## 第二轮（2026-07-30 晚）：预算被首个源吃光 + spacex 只剩 1 条

修复上线后首轮 Actions：10 条摘要落盘（零丢失目标达成），但
- **openai 一个源吃光全部 25 分钟**（~2.7 分钟/次调用，API 中继极慢），
  其余 8 源回填全部 0；inline 摘要排在 openai 回填之后也被殃及
- **spacex-updates 28 条只剩 1 条**：上游老代码
  `entry.link.find('#replay') and entry.link.find('v2ex')` 中
  find() 找不到返回 -1（Python 里为真），条件恒真，所有链接的 #fragment
  被无条件砍掉 → spacex 的 #slug 链接全部撞同一条被去重

第二轮修复：
- `_llm_deadline`：剩余预算按剩余源数均分，每源公平份额
  （inline 与回填共用），快的源不浪费、慢的源不独吞
- 回填调用按账号上限并发 3（ThreadPoolExecutor 分批），理论吞吐 ×3
- 每次回填记录耗时（`Backfilled in Ns`），供下次诊断 API 速度
- spacex 错误种子（1 条）已删，Actions 下轮重播 28 条；
  contentBlocks 拼接过滤 id/None 噪声

## 备注
- 404 抖动本身是上游中继问题；若持续高发，检查 CUSTOM_MODEL /
  OPENAI_BASE_URL 对应的渠道是否都有该模型
