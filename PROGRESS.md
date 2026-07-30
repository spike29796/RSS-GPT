# PROGRESS 心跳

更新时间：2026-07-30（七源扩展本地完成，待提交推送 + Actions 首轮验收）

## 当前步骤
REQ-seven-sources.md 收尾完成：6 源种子已入库、validate 通过、e2e 全绿、
前端 9 源截图验收通过。spacex-updates 本地被 Cloudflare 区域封锁（403），
按用户决定搁置本地播种，push 后由 Actions（美国 IP）首轮自动播种。

## 已完成
- 第一~三阶段、第六轮、Claude Blog 源（见 git 历史）
- 七源扩展（google/deepseek/kimi/microsoft/apple/spacex/nvidia）：
  - 3 个新采集器 + ignore_tags + 7 段源配置（昨天已写好，未提交）
  - 修复实测 bug：splitlines 截断 JSONL（U+2028/U+0085）、抓取失败留空产物、
    requests 缺省 ISO-8859-1 致 deepseek 中文乱码、侧边栏栏目链接混入、
    e2e 子进程 GBK 解码崩
  - 本地无 key 播种 6 源（摘要留空待 Actions 回填）：google 20 / deepseek 14 /
    kimi 9 / microsoft 10 / apple 20 / nvidia 18
  - 前端：SOURCES 9 源（league A–I + 品牌色）、TAG_ZH 补 Apple 映射、
    构建产物进 RSS-GPT/docs

## 下一步（用户操作）
1. 提交外层（test/ + web/ + 文档）与 RSS-GPT（采集器/配置/main.py/种子/产物）并 push
2. 手动触发一次 Actions：spacex 自动播种 + 各源开始回填摘要
3. 线上验收：9 源卡片、spacex 404 提示消失、摘要逐日增多

## 遇到的问题
- spacex 本地 403 为预期（Cloudflare 区域封锁），validate/e2e 对未播种源
  显示 SKIPPED 不算失败；Actions 播种后自动纳入校验
- microsoft/google 的 CDN 本地偶发超时/403，重跑即恢复（幂等）
- node 不在 bash PATH → 用 /c/Program Files/nodejs；vite preview 不可用于
  本地验收 → test/serve_pages.py 或 web/scripts/ui_shots.mjs
