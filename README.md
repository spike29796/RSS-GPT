# RSS-GPT 部署手册（个人 AI 资讯聚合平台）

目标：用 GitHub Actions 每天自动抓取 9 个资讯源，调用大模型生成**中文一句话导读**，
生成新的 RSS 页面托管在 GitHub Pages，手机可访问。

本手册按"照着重装"的标准写，包含每一步在做什么、为什么，以及踩坑记录。

> **现行形态（2026-07-31 T-001 起）**：本仓库是 monorepo——业务管线在 `RSS-GPT/` 子目录，
> 前端在 `web/`，验证脚本在 `test/`，workflow 在仓库根 `.github/workflows/`。
> 线上仓库 [spike29796/RSS-GPT](https://github.com/spike29796/RSS-GPT) 就是本仓库的推送目标。

---

## 0. 工作原理（先理解再动手）

```
GitHub Actions（仓库根 .github/workflows/cron-job.yml，定时）
  → 在 RSS-GPT/ 目录下跑 main.py → 抓 config.ini 里的 9 个源
  → 调 OpenAI 兼容 API 生成中文导读 → 把新 RSS/JSONL 写进 RSS-GPT/docs/
  → git push 回仓库 main 分支
  → .github/workflows/pages.yml 把 RSS-GPT/docs/ 发布到 GitHub Pages
```

- **不需要服务器**：GitHub Actions 就是免费定时器 + 运行环境，GitHub Pages 就是免费静态托管。
- **摘要生成在 Actions 里完成**，生成的结果（带摘要的 RSS）以代码形式提交回仓库，Pages 只是展示。
- `RSS-GPT/docs/` 目录既是脚本的输出目录，也是 Pages 的发布目录，二者通过 `config.ini` 的 `base = "docs/"` 对齐。
- **Pages 走 Actions 发布而非 branch /docs**：monorepo 里站点文件在 `RSS-GPT/docs/` 子目录，
  branch 模式的 `/docs` 选项够不到子目录，所以用 `upload-pages-artifact` + `deploy-pages` 显式指定发布目录。

## 1. 部署拓扑（现行）

```
本地 monorepo（本仓库）
  ├── RSS-GPT/          业务管线（main.py / collectors.py / config.ini / docs/ 数据）
  ├── web/              Vue3 前端，build 直出到 RSS-GPT/docs/
  ├── test/             e2e/验证脚本
  └── .github/workflows/
      ├── cron-job.yml  每日管线（working-directory=RSS-GPT）
      └── pages.yml     Pages 发布（发布 RSS-GPT/docs/）
        │ git push main
        ▼
spike29796/RSS-GPT（GitHub，public fork 改造而来）
        │ Actions 跑 cron_job → Auto Build 提交回 main
        │ pages.yml 发布
        ▼
https://spike29796.github.io/RSS-GPT/
```

要点：

- **唯一源头**：所有改动在本地 monorepo 完成，push 到远端 main 即上线；不要再在 GitHub 网页上改文件。
- **workflow 必须在仓库根**：GitHub 只认 `<仓库根>/.github/workflows/`，所以 cron-job.yml 从
  `RSS-GPT/.github/` 移到了根上，各 `run` 步骤用 `defaults.run.working-directory: RSS-GPT` 进入业务目录。
- **仓库名保持 `RSS-GPT` 不要改**：`main.py` 把 Pages 地址写死为 `https://<U_NAME>.github.io/RSS-GPT/`，
  改名后生成的订阅链接会错。
- **历史**：线上仓库最初是 [yinan-c/RSS-GPT](https://github.com/yinan-c/RSS-GPT) 的 fork
  （首次部署的网页操作流程见第 5 节存档）；T-001 起本地 monorepo 成为唯一源头。

## 2. 干净环境跑通（验证用）

全新机器/全新目录验证本仓库能跑，用 mock LLM（不烧钱、不需要真实 API key）：

```bash
# 国内直连 GitHub 被墙时走镜像（直连正常则去掉 https://gh-proxy.com/ 前缀）
git clone https://gh-proxy.com/https://github.com/spike29796/RSS-GPT.git
cd RSS-GPT

# 装依赖（Windows 上 python 可能是商店占位 stub，用 py；推荐 3.11/3.12，3.14 实测可跑）
py -m pip install -r RSS-GPT/requirements.txt

# 跑 e2e 验证：真实源 + mock LLM，两轮跑（幂等性）+ 分类校验
py test/e2e_verify.py
```

注意事项：

- **被墙源需显式代理**：部分源（如 spacex）国内直连不通，本地跑前设
  `HTTPS_PROXY=http://127.0.0.1:7892`（端口按本机代理实际值），并设
  `NO_PROXY=127.0.0.1,localhost` 保住本地 mock LLM。GitHub Actions 直连无此问题。
- e2e 会真实抓取 9 个源（复制仓库到临时目录跑，绝不碰正式 `docs/` 数据），
  全程约几分钟，输出全 PASS 即通过。
- 前端本地开发：`cd web && npm install && npm run dev`，dev server 把 `/RSS-GPT/*`
  代理到线上 Pages 取真实数据。

## 3. Secrets 需求清单

Actions 运行依赖 5 个 Repository Secrets（仓库 **Settings → Secrets and variables → Actions**）：

| Secret 名 | 用途 | 要求/注意 |
|---|---|---|
| `WORK_TOKEN` | Actions checkout + push 回写仓库 | PAT classic，scope 需 `repo` + `workflow`；**会过期**，到期 push 403，需重新生成并更新 |
| `OPENAI_API_KEY` | LLM 服务商密钥 | 在服务商控制台生成 |
| `OPENAI_BASE_URL` | OpenAI 兼容端点 | **必须显式填**；GitHub 对不存在的 secret 注入空字符串，会让 client 初始化失败 |
| `CUSTOM_MODEL` | 模型名 | 现行行为证据为 kimi-k2.6（推理模型，单次 65-219s） |
| `U_NAME` | GitHub 用户名 | 拼 Pages 地址用（`main.py` 仓库名写死 RSS-GPT） |

常见服务商填法：

| 服务商 | OPENAI_BASE_URL | CUSTOM_MODEL 示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| OpenAI 官方 | `https://api.openai.com/v1` | `gpt-4o-mini` |

> 核对方式：secret 值 GitHub 永不回显，名单也只能登录 Settings 看。
> 功能验证法——手动触发一次 cron_job，能产出真实摘要且 Auto Build 提交成功，即 5 项全部在位。

## 4. openai 库版本问题：不用处理

README 里提到的 `openai==0.27.8` 是**历史遗留说明**。实测上游现状（2026-07）：

- `requirements.txt` 已固定 `openai==1.56.2`（新版 SDK）；
- `main.py` 用的已是新版写法：`from openai import OpenAI` + `client.chat.completions.create(...)`。

**结论：保持上游代码不动，比改代码或降级都稳。** 反而如果照 README 把 openai 降级到 0.27.8，
现有代码会直接报 `AttributeError: module 'openai' has no attribute 'OpenAI'`。

新版 SDK 的好处：`base_url` 参数天然支持 DeepSeek、Moonshot、智谱等国内 OpenAI 兼容服务，
只改配置不改代码。

## 5. 首次部署存档（2026-07 fork 时代的网页操作流程）

> 以下是当初从 yinan-c/RSS-GPT fork 后、在 GitHub 网页上首次部署的操作记录。
> **现行形态下不需要照做**——所有文件已在 monorepo 里，改完 push 即生效。
> 保留此节是因为其中的 PAT 生成、secrets 配置、Actions 启用等步骤重装时仍然有效。

### 5.1 Fork 仓库（不要改仓库名）

1. 打开 https://github.com/yinan-c/RSS-GPT
2. 右上角 **Fork** → **Create fork**
3. **仓库名保持 `RSS-GPT` 不要改**（原因见第 1 节要点）。

### 5.2 启用 Actions（fork 的仓库默认禁用，必做）

1. 进入你 fork 的仓库 → 顶部 **Actions** 标签页
2. 页面提示 workflows 已禁用，点绿色按钮 **"I understand my workflows, go ahead and enable them"**

### 5.3 生成 Personal Access Token（给 Actions 回写代码用）

为什么需要：Actions 默认的 `GITHUB_TOKEN` 推送后不会再触发其他 workflow，且权限受限；
上游设计用一个 PAT（secret 名 `WORK_TOKEN`）来 checkout 和 push。

1. 点右上角头像 → **Settings**
2. 左侧最底部 **Developer settings**
3. **Personal access tokens** → **Tokens (classic)**
4. **Generate new token** → **Generate new token (classic)**
5. Note 填 `RSS-GPT`，Expiration 按需（建议 90 天或 No expiration，到期要记得换）
6. 勾选权限：**`repo`**（整组）和 **`workflow`**
7. 拉到底 **Generate token** → **立刻复制**（只显示这一次，关掉就再也看不到）

### 5.4 配置 5 个 Repository Secrets

按第 3 节清单逐项填（路径：仓库 **Settings → Secrets and variables → Actions → New repository secret**）。

### 5.5 config.ini（现行 9 源）

现行配置是 **9 个源**（`RSS-GPT/config.ini`，source002–010）：

| 源 | 类型 | 分类方式 |
|---|---|---|
| openai-news | 官方 RSS | 复用 feed 官方 20 词标签 |
| claude-blog | 采集器（Webflow SSR） | 复用卡片官方 tag |
| google-blog | 官方 RSS | 首个 tag 作分类 |
| deepseek-news | 采集器（Docusaurus） | 全局五类 LLM 分类 |
| kimi-blog | 采集器（Next.js SSR） | 全局五类 LLM 分类 |
| microsoft-blog | 官方 RSS | ignore_tags 滤噪后首个 tag |
| apple-newsroom | 官方 Atom | PRESS RELEASE / UPDATE |
| spacex-updates | 采集器（JSON API） | 源级中文五类 |
| nvidia-blog | 官方 RSS | 首个 tag 作分类 |

改配置 = 改 `RSS-GPT/config.ini` → commit → push，下一轮 Actions 生效。

### 5.6 workflow 文件（现行在仓库根）

现行：`.github/workflows/cron-job.yml` 随 monorepo 直接 push 生效，无需网页粘贴。
当初对上游 workflow 的必要修改（仍是有效的踩坑记录）：

- `runs-on: ubuntu-20.04` → `ubuntu-latest`：**20.04 镜像已被 GitHub 正式下线**，不改的话任务排队后直接被取消，报 "This request was automatically failed"。
- `actions/checkout@v3` → `v4`、`setup-python@v4` → `v5`、Python 3.8 → 3.12：v3/v4 基于已弃用的 Node 16，Python 3.8 已 EOL。
- 增加 `schedule: cron: "17 0 * * *"`：上游只剩手动触发；这行让它每天 UTC 00:17（**北京时间 08:17**）自动跑，形成"日报"。GitHub cron 只认 UTC。
- commit 加 `|| echo "No changes"`：某天源没更新时 `git commit` 无内容会退出码 1，导致整轮标红，加兜底。
- T-001 新增：`defaults.run.working-directory: RSS-GPT`，适配 monorepo 子目录。

### 5.7 定制文件说明（main.py / template.xml / collectors.py）

分类功能、采集器、摘要回填等是对上游的定制（见 5.10 起的演进记录），
文件都在 monorepo 的 `RSS-GPT/` 子目录里，改完 commit + push 即可，无需网页粘贴。

### 5.8 开启 GitHub Pages（现行：走 Actions）

1. 仓库 **Settings** → 左侧 **Pages**
2. **Build and deployment** → **Source** 选 **GitHub Actions**（不是 Deploy from a branch）
3. 之后由 `.github/workflows/pages.yml` 自动发布 `RSS-GPT/docs/`

### 5.9 手动触发运行（验收用）

1. **Actions** 标签页 → 左侧 **cron_job**
2. 右侧 **Run workflow** 下拉 → **Run workflow**
3. 等运行结束，刷新看运行记录：绿色勾 = 成功；点开可看每步日志

### 5.10 验收

- Actions 运行记录为绿色 ✅
- 打开 `https://spike29796.github.io/RSS-GPT/`，看到 9 源 Vue 聚合前端
- 点开任一源的 xml（如 `.../openai-news.xml`），文章条目里有中文导读

### 5.11 文章分类功能（对上游的定制）

每篇文章除了中文导读，还会带一个分类，写入 RSS XML 的 `<category>` 字段：

- 分类列表可在 `config.ini` 的 `[cfg] categories` 配置（默认五类：**模型发布 / 行业动态 / 政策法规 / 开源项目 / 产品应用**），兜底类由 `[cfg] default_category` 配置；单个源可用 `[sourceNNN]` 下的 `categories` 键覆盖
- 实现方式：摘要 prompt 要求模型第一行只输出分类、第二行起输出摘要；
  代码解析第一行并校验合法性，不合法（或摘要失败、超出 max_items 未调用模型）时兜底为默认分类
- 旧条目在后续运行中重新渲染时保留原分类
- 改动文件：`main.py`（prompt + 解析 + 兜底）、`template.xml`（渲染 `<category>`）

### 5.12 采集器源（非 RSS 来源；awwwards 已成历史）

管道除 RSS 外还支持"采集器源"：直接抓网页解析出条目，走同一套
去重/分类/JSONL/XML 流程。首个采集器是 **Awwwards Site of the Day**
（`awwwards-sotd`）——**该源后来已从 config.ini 移除（见 5.16），此处仅作机制存档**：

- `collector` 键指向 `collectors.py` 里的 `COLLECTORS` 注册表；`url` 作为采集目标页。
  新增采集器 = 在 `collectors.py` 写一个返回伪 feed 的函数并注册。
- 现行在用的采集器源：claude-blog / deepseek-news / kimi-blog / spacex-updates（见 5.5 表）。
- 采集器代码保留在 `collectors.py` 待用（含 awwwards）。

### 5.13 第二阶段顺带修复

- **摘要 prompt 结构**：格式指令从 assistant 消息挪到 system 消息（上游把指令塞在
  assistant 里是格式遵从差的主因之一）；解析失败自动重试 1 次，仍不合规则
  summary 记空（原始输出不再进数据层）。
- **openai-news 传送带 BUG 已修**：截断移到合并之后，且被截断丢弃的链接记入
  `docs/<name>.dropped` 墓碑文件，feed 仍提供的旧档案不再被当作新条目重抓。
  想强制重抓某源历史，删掉对应 `.dropped` 文件即可。
  （修复后 openai-news 一次性从 1051 回落到 1000 条，属预期。）

### 5.14 前端聚合页（第三阶段）

Pages 首页是一个 Vue3 单页应用（聚合展示 9 源条目：源切换/分类筛选/搜索/
缩略图），数据直接 fetch 同站的 `docs/*.jsonl`，纯静态无后端。

- 源码在本仓库 `web/`（Vite + Vue3，无 TS/router/UI 库）；
  `npm run build` 产物直接写入 `RSS-GPT/docs/`（`index.html` + `assets/`）。
- **目录归属约定**：`RSS-GPT/docs/index.html` 和 `docs/assets/` 是前端构建产物，
  不要手改、不要让管道覆盖；`main.py` 的 RSS 链接列表页已改渲染到
  `docs/feeds.html`（管道绝不会碰 index.html）。
- 改了前端后重新 `npm run build` 并把 monorepo 的产物一起 commit + push
  （注意：`docs/assets/` 里带 hash 的旧文件不会自动清理，构建后手动删掉旧版本）。
- 本地开发：`cd web && npm run dev`，dev server 会把 `/RSS-GPT/*` 代理到线上
  Pages 取真实数据（本机需走代理时给 npm 进程配 HTTPS_PROXY）。

### 5.15 摘要回填（backfill）

只有每天每源最新 `max_items` 条会拿到摘要，此前未摘要的条目（超额度/失败/兜底）
默认永远空白。开启回填后，每轮运行会额外用独立预算为**最近 N 天内**未摘要的
条目补摘要（最新优先），直到窗口内全覆盖：

```ini
[sourceNNN]
backfill_days = "7"    # 时间窗口（天），默认 0 = 关
backfill_items = "5"   # 每轮回填预算（条），默认 0 = 关
```

- **当前配置**：openai-news 3650天/10条（覆盖全部千条档案）；spacex 365天/10条；
  deepseek/kimi 90天/10条；apple 60天/10条；claude/google/microsoft/nvidia 30天/10条。
  全局软预算 `[cfg] backfill_max_minutes=25` 分钟，回填+新条目摘要共用，
  预算耗尽即停、下轮继续（防 Actions 超时整轮丢失）。
- 回填只改 summary/category/content，不改条目集合与顺序；输出不合规时跳过
  留给下轮。

### 5.16 单源 OpenAI + 官方标签（第五轮，已成历史）

> 注：本轮之后源又重新扩展到现行 9 源（见 5.5），此节仅作演进存档。

- 当时源收缩为 openai-news 一个（旧三源配置与数据文件已删，git 历史可查）。
- **分类复用官方标签**：feed 每条自带官方 `<category>`（20 个词汇），代码里
  官方 tag 优先于 LLM 分类与兜底；`[source002] categories` 写死 20 词做允许集，
  最老约 100 条无 tag 的用 `default_category="Company"` 兜底。
  LLM 只写一句话中文导读。存量用 `test/retag_official_categories.py` 重打标。
  （官方 tag 优先机制在现行 9 源中仍然生效。）

### 5.17 双语主题 / 一键翻译 / 模糊搜索 / 档案全补齐（第六轮）

- **档案全补齐**：openai-news `backfill_days=3650` 覆盖全部档案；
  **现行 `backfill_items=10`（每天 10 条，不是早先设想的 50）**——推理模型单次
  65-219s，配合 25 分钟全局软预算实测约 27 条/轮，千条档案约 3 个月补完。
- **三行摘要格式**：分类 / 一句话导读 / 标题中文翻译。记录新增 `title_zh`
  字段；回填资格 = 无摘要或无 title_zh，存量条目会随队补译不丢数据。
- **前端**：头部 ☀️/🌙 切换日/夜主题（默认跟随系统，localStorage 记忆）；
  "译"按钮切换标题与标签中文显示（译题来自数据层 title_zh，标签是前端
  内置 20 词映射，见 `web/src/i18n.js`）；搜索为 Fuse.js 双语模糊匹配。

## 6. 踩坑记录

1. **机器之心 RSS 已下线**：`jiqizhixin.com/rss` 现在 302 跳转到"数据服务"付费页，返回 HTML 而非 XML；
   RSSHub 也没有它的路由（官方文档 sitemap 查无）。本方案曾用定位最接近的**量子位**（`qbitai.com/feed`，已验证 200 + 合法 RSS）替代（现也已下线移除）。
2. **openai 0.27.8 是旧闻**：上游早已迁移到 1.x SDK，照 README 降级反而会炸（见第 4 节）。
3. **ubuntu-20.04 已下线**：上游 workflow 不改必失败（见 5.6）。
4. **fork 后 Actions 默认禁用**，不点启用按钮，`workflow_dispatch` 和定时都不会跑（见 5.2）。
5. **GitHub cron 是 UTC**，且 Actions 定时任务可能延迟几分钟到几十分钟，不要指望准点。
6. **空 secret = 空字符串**，`OPENAI_BASE_URL` 必须显式填（见第 3 节）。
7. **PAT 会过期**：Expiration 到期后 Actions 的 push 步骤会 403，到时重新生成 PAT 并更新 `WORK_TOKEN`。
8. **60 天无仓库活动，GitHub 会自动停用定时 workflow**：届时到 Actions 页点一下 re-enable 即可。
9. **API key 只放 Secrets**：本流程中密钥只出现在 `Settings → Secrets` 和 workflow 的 `${{ secrets.* }}` 引用里，
   不要写进 `config.ini`、`main.py` 或任何提交记录。
10. **摘要条数控制**：`max_items` 是"每次运行最多为几篇新文章生成摘要"，各源设为 3，
    控制 API 花费；正式用可以调大。
11. **量子位会 403 非浏览器 UA**：上游用 fake_useragent 随机 UA，实测被量子位拒绝（403）。
    `RSS-GPT/main.py` 已改为固定的现代 Chrome UA，不要改回去。
12. **第一次运行很慢**：OpenAI 官方 feed 带全部历史文章（约 1000 篇），首轮要逐篇清洗，
    Actions 第一次跑 10 分钟以上属正常；之后有去重缓存就快了。
13. **feedparser 的属性陷阱**：给 feedparser 的 entry 用点号赋值自定义属性不会写入字典，
    `entry.get('xxx')` 永远拿到 None。读取自定义属性必须用 `getattr(entry, 'xxx', None)`。
    （这是分类功能开发时踩的坑，`RSS-GPT/main.py` 里已修正并注释。）
14. **本地跑采集器源要显式代理**：部分采集目标在本机直连超时/被墙，本地验证需
    `HTTPS_PROXY=http://127.0.0.1:7892`（requests 不一定会读系统代理）；
    同时 `NO_PROXY=127.0.0.1,localhost` 保住本地 mock LLM。GitHub Actions 直连无此问题。
15. **"合并后再截断"治不了传送带**：只要 feed 全量档案 > max_entries，丢弃的条目下轮
    必然被当作新条目重抓，无论截断在合并前后。必须配墓碑文件（见 5.13）。
16. **GitHub Actions 没有 IPv6 路由**：目标站有 AAAA 记录时（如 awwwards），
    首次连接直接 ENETUNREACH（Errno 101，不是 403），要在采集器内强制 IPv4
    （`collectors.py` 的 `_get_ipv4`，AF_INET-only getaddrinfo）。本机有 IPv6/代理
    所以本地验证发现不了这个问题。
17. **workflow 必须放仓库根**：放在 `RSS-GPT/.github/` 里 GitHub 完全不认（T-001 已修正上根）。

## 7. 以后重装 / 加源

- 重装：`git clone` 本仓库（国内走 gh-proxy 镜像前缀），照第 2 节跑通验证；
  线上部署侧只需确认第 3 节 secrets 在位 + Actions 已启用 + Pages source 为 GitHub Actions。
- 加源：在 `RSS-GPT/config.ini` 末尾追加 `[sourceNNN]` 段（段名递增即可），填
  `name` / `url` / `max_items`，commit + push 后等下一轮运行。
- 改摘要语言/长度：`[cfg]` 段 `language` 和 `summary_length`。
- 改分类体系：`[cfg]` 段 `categories`（逗号分隔）和 `default_category`；单个源可在自己的 `[sourceNNN]` 段加 `categories` 覆盖全局。
