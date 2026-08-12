# MOD-auth-preflight：GitHub 认证链路与开工自检（T-023 沉淀）

施工链路四类岗位终端开工前的认证自检口径。脚本：`test/preflight_github_auth.py`，
一条命令五项检查，全绿 exit 0，有 FAIL exit 1：

```
py test/preflight_github_auth.py
```

## 本机环境四件套（缺一项就会"经常登不上"）

1. **代理**：`127.0.0.1:7892`。git 走全局配置 `git config --global http.proxy http://127.0.0.1:7892`
   （2026-08-11 头头拍板打上）。注意：git 不认系统代理，代理客户端 TUN/系统代理状态
   漂移时直连 github.com 即超时——T-023 施工时实测现场。curl 用 `-x http://127.0.0.1:7892`。
   反向注意：api.bilibili.com 等国内站点**直连不走代理**（T-025 实测）。
2. **凭据**：git credential manager（`git config credential.helper` = `manager`），
   条目 `git:https://github.com`。只验不改：token 本体全程不落盘不打印，
   输出只许 `prefix=前4字符 len=长度`（当前为 ghp_ PAT）。
3. **token scope**：对照清单 repo / workflow / delete_repo / read:org，
   实测口径 = API 响应头 `X-OAuth-Scopes`（GET https://api.github.com/user 带 token）。
   缺项补钩：https://github.com/settings/tokens 或 `gh auth refresh -s <scope>`。
4. **gh CLI**：`gh auth status`。gh 非主线工具，未登录只 WARN 不 FAIL。

## 脚本五项检查与复演参数

① 代理链路（经 7892 访问 api.github.com 求 200）② 凭据命中（git credential fill）
③ scope 对照（缺 read:org → WARN，缺其他 → FAIL）④ gh 登录态（未登录 → WARN）
⑤ 非交互 `GIT_TERMINAL_PROMPT=0 git ls-remote`（防弹窗卡施工）。

复演参数（不碰真实凭据/代理）：`--proxy 127.0.0.1:9` 制造断代理报红；
`--extra-scope t023_rehearsal_scope` 制造 scope 缺项报红。

## 本机 Python 陷阱

`python` 命令是微软商店占位 stub（exit 49，WindowsApps 路径），真解释器只走
`py` 启动器（3.14）。所有手册/契约/脚本命令一律 `py`。

## 溯源

工单 `docs/T-023.md`；验收证据 `D:\vibe-coding\factory-shared\artifacts\T-023\`；
T-021 仓库瘦身操作中的凭据/代理纪律同口径。
