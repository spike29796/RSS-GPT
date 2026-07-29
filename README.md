# RSS-GPT 部署手册（个人 AI 资讯聚合平台 · 第一阶段）

目标：fork [yinan-c/RSS-GPT](https://github.com/yinan-c/RSS-GPT)，用 GitHub Actions 每天自动抓取 RSS 源，
调用大模型生成**中文摘要（200 字以内）**，生成新的 RSS 页面托管在 GitHub Pages，手机可访问。

本手册按"照着重装"的标准写，包含每一步在做什么、为什么，以及踩坑记录。

---

## 0. 工作原理（先理解再动手）

```
GitHub Actions（定时） → 跑 main.py → 抓 config.ini 里的 RSS 源
  → 调 OpenAI 兼容 API 生成中文摘要 → 把新 RSS 文件写进 docs/ 目录
  → git push 回仓库 → GitHub Pages 把 docs/ 发布成网页
```

- **不需要服务器**：GitHub Actions 就是免费定时器 + 运行环境，GitHub Pages 就是免费静态托管。
- **摘要生成在 Actions 里完成**，生成的结果（带摘要的 RSS）以代码形式提交回仓库，Pages 只是展示。
- `docs/` 目录既是脚本的输出目录，也是 Pages 的发布目录，二者通过 `config.ini` 的 `base = "docs/"` 对齐。

## 1. openai 库版本问题：不用处理

README 里提到的 `openai==0.27.8` 是**历史遗留说明**。实测上游现状（2026-07）：

- `requirements.txt` 已固定 `openai==1.56.2`（新版 SDK）；
- `main.py` 用的已是新版写法：`from openai import OpenAI` + `client.chat.completions.create(...)`。

**结论：保持上游代码不动，比改代码或降级都稳。** 反而如果照 README 把 openai 降级到 0.27.8，
现有代码会直接报 `AttributeError: module 'openai' has no attribute 'OpenAI'`。

新版 SDK 的好处：`base_url` 参数天然支持 DeepSeek、Moonshot、智谱等国内 OpenAI 兼容服务，
只改配置不改代码。

## 2. 需要你手动操作的清单（截图级路径）

> 全程在浏览器完成，不需要本地装任何东西。密钥只填进 GitHub Secrets，不写进任何代码文件。

### 2.1 Fork 仓库（不要改仓库名）

1. 打开 https://github.com/yinan-c/RSS-GPT
2. 右上角 **Fork** → **Create fork**
3. **仓库名保持 `RSS-GPT` 不要改** —— `main.py:30` 把 Pages 地址写死为 `https://<U_NAME>.github.io/RSS-GPT/`，改名后生成的订阅链接会错。

### 2.2 启用 Actions（fork 的仓库默认禁用，必做）

1. 进入你 fork 的仓库 → 顶部 **Actions** 标签页
2. 页面提示 workflows 已禁用，点绿色按钮 **"I understand my workflows, go ahead and enable them"**

### 2.3 生成 Personal Access Token（给 Actions 回写代码用）

为什么需要：Actions 默认的 `GITHUB_TOKEN` 推送后不会再触发其他 workflow，且权限受限；
上游设计用一个 PAT（secret 名 `WORK_TOKEN`）来 checkout 和 push。

1. 点右上角头像 → **Settings**
2. 左侧最底部 **Developer settings**
3. **Personal access tokens** → **Tokens (classic)**
4. **Generate new token** → **Generate new token (classic)**
5. Note 填 `RSS-GPT`，Expiration 按需（建议 90 天或 No expiration，到期要记得换）
6. 勾选权限：**`repo`**（整组）和 **`workflow`**
7. 拉到底 **Generate token** → **立刻复制**（只显示这一次，关掉就再也看不到）

### 2.4 配置 5 个 Repository Secrets

路径：你 fork 的仓库 → **Settings** → 左侧 **Secrets and variables** → **Actions** → **New repository secret**

| Secret 名 | 填什么 | 说明 |
|---|---|---|
| `WORK_TOKEN` | 2.3 复制的 PAT | Actions 回写仓库用 |
| `OPENAI_API_KEY` | 你的大模型 API key | 在对应服务商控制台生成 |
| `OPENAI_BASE_URL` | 服务商接口地址 | 见下方示例，**必须显式填** |
| `CUSTOM_MODEL` | 模型名 | 见下方示例 |
| `U_NAME` | 你的 GitHub 用户名 | 用于拼 Pages 地址 |

`OPENAI_BASE_URL` 常见填法（你选了"其他兼容服务"，按你实际的服务商填）：

| 服务商 | OPENAI_BASE_URL | CUSTOM_MODEL 示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| OpenAI 官方 | `https://api.openai.com/v1` | `gpt-4o-mini` |

> 坑：`OPENAI_BASE_URL` 即使官方也要显式填。GitHub 对不存在的 secret 会注入**空字符串**，
> 空字符串会让 `os.environ.get(..., 默认值)` 拿不到默认值，OpenAI client 会初始化失败。

### 2.5 替换 config.ini（3 个测试源）

1. 仓库首页点开 `config.ini` → 右上角铅笔图标 **Edit this file**
2. 全选删除，粘贴本仓库 `RSS-GPT/config.ini` 的内容（已配好：量子位 / OpenAI News / IT之家，中文、200 字摘要）
3. 底部 **Commit changes** → **Commit directly to the main branch** → **Commit changes**

### 2.6 替换 workflow 文件（上游版本已无法运行，必须改）

1. 仓库里进入 `.github/workflows/cron-job.yml` → 铅笔 **Edit**
2. 全选删除，粘贴本仓库 `RSS-GPT/.github/workflows/cron-job.yml` 的内容
3. **Commit changes**

改了什么、为什么：

- `runs-on: ubuntu-20.04` → `ubuntu-latest`：**20.04 镜像已被 GitHub 正式下线**，不改的话任务排队后直接被取消，报 "This request was automatically failed"。
- `actions/checkout@v3` → `v4`、`setup-python@v4` → `v5`、Python 3.8 → 3.12：v3/v4 基于已弃用的 Node 16，Python 3.8 已 EOL。
- 增加 `schedule: cron: "17 0 * * *"`：上游只剩手动触发；这行让它每天 UTC 00:17（**北京时间 08:17**）自动跑，形成"日报"。GitHub cron 只认 UTC。
- commit 加 `|| echo "No changes"`：某天源没更新时 `git commit` 无内容会退出码 1，导致整轮标红，加兜底。

### 2.6.1 替换 main.py 和 template.xml（分类功能）

分类功能是我们对上游的定制修改（见第 2.10 节），同样需要覆盖 fork 里的文件：

1. 仓库里点开 `main.py` → 铅笔 **Edit** → 全选删除，粘贴本仓库 `RSS-GPT/main.py` 的内容 → **Commit changes**
2. 同样方法用 `RSS-GPT/template.xml` 替换 `template.xml`

（更推荐的方式：本地 `RSS-GPT/` 目录就是 fork 的 git 克隆，直接改完 `git push`，无需网页粘贴。）

### 2.7 开启 GitHub Pages

1. 仓库 **Settings** → 左侧 **Pages**
2. **Build and deployment** → **Source** 选 **Deploy from a branch**
3. **Branch** 选 **main**，目录选 **/docs** → **Save**

（第一次 Actions 跑完把内容推进 `docs/` 后，页面才真正有东西。）

### 2.8 手动触发第一次运行（验收用）

1. **Actions** 标签页 → 左侧 **cron_job**
2. 右侧 **Run workflow** 下拉 → **Run workflow**
3. 等 1~3 分钟，刷新看运行记录：绿色勾 = 成功；点开可看每步日志

### 2.9 验收

- Actions 运行记录为绿色 ✅
- 打开 `https://<你的用户名>.github.io/RSS-GPT/`，能看到 qbitai / openai-news / ithome 三个源的入口
- 点开任一源的 xml，文章条目里有 `总结:` 开头的中文摘要

### 2.10 文章分类功能（对上游的定制）

每篇文章除了中文摘要，还会带一个分类，写入 RSS XML 的 `<category>` 字段：

- 分类列表可在 `config.ini` 的 `[cfg] categories` 配置（默认五类：**模型发布 / 行业动态 / 政策法规 / 开源项目 / 产品应用**），兜底类由 `[cfg] default_category` 配置；单个源可用 `[sourceNNN]` 下的 `categories` 键覆盖
- 实现方式：摘要 prompt 要求模型第一行只输出分类、第二行起输出摘要；
  代码解析第一行并校验合法性，不合法（或摘要失败、超出 max_items 未调用模型）时兜底为默认分类
- 旧条目在后续运行中重新渲染时保留原分类
- 改动文件：`main.py`（prompt + 解析 + 兜底）、`template.xml`（渲染 `<category>`），以 fork 仓库（本地 `RSS-GPT/` 克隆）为准

### 2.11 采集器源（非 RSS 来源，第二阶段新增）

管道除 RSS 外还支持"采集器源"：直接抓网页解析出条目，走同一套
去重/分类/JSONL/XML 流程。首个采集器是 **Awwwards Site of the Day**
（`awwwards-sotd`），配置方式（已在 config.ini 里）：

```ini
[source004]
name = "awwwards-sotd"
url = "https://www.awwwards.com/websites/sites_of_the_day/"
collector = "awwwards_sotd"
max_items = "0"
categories = "设计灵感"
default_category = "设计灵感"
```

- `collector` 键指向 `collectors.py` 里的 `COLLECTORS` 注册表；`url` 作为采集目标页。
  新增采集器 = 在 `collectors.py` 写一个返回伪 feed 的函数并注册。
- Awwwards 条目凭 标题+Tags 走 LLM（`max_items=5`）：独立分类集
  （榜单发布/优秀工作室/技术展示/视觉风格/行业资讯）+ 一句话导读；
  `backfill 30天/10条` 覆盖存量。不抓详情页分数（后续想要可加）。
- 源级 `default_category` 覆盖与 `categories` 覆盖同模式，非 AI 内容不会落进「行业动态」。

### 2.12 第二阶段顺带修复

- **摘要 prompt 结构**：格式指令从 assistant 消息挪到 system 消息（上游把指令塞在
  assistant 里是格式遵从差的主因之一）；解析失败自动重试 1 次，仍不合规则
  summary 记空（原始输出不再进数据层）。
- **openai-news 传送带 BUG 已修**：截断移到合并之后，且被截断丢弃的链接记入
  `docs/<name>.dropped` 墓碑文件，feed 仍提供的旧档案不再被当作新条目重抓。
  想强制重抓某源历史，删掉对应 `.dropped` 文件即可。
  （修复后 openai-news 一次性从 1051 回落到 1000 条，属预期。）

### 2.13 前端聚合页（第三阶段）

Pages 首页是一个 Vue3 单页应用（聚合展示四源条目：源切换/分类筛选/搜索/
缩略图），数据直接 fetch 同站的 `docs/*.jsonl`，纯静态无后端。

- 源码在外层仓库 `web/`（Vite + Vue3，无 TS/router/UI 库）；
  `npm run build` 产物直接写入 `RSS-GPT/docs/`（`index.html` + `assets/`）。
- **目录归属约定**：`RSS-GPT/docs/index.html` 和 `docs/assets/` 是前端构建产物，
  不要手改、不要让管道覆盖；`main.py` 的 RSS 链接列表页已改渲染到
  `docs/feeds.html`（管道绝不会碰 index.html）。
- 改了前端后重新 `npm run build` 并把 `RSS-GPT` 仓库的产物一起 commit + push
  （注意：`docs/assets/` 里带 hash 的旧文件不会自动清理，构建后手动删掉旧版本）。
- 本地开发：`cd web && npm run dev`，dev server 会把 `/RSS-GPT/*` 代理到线上
  Pages 取真实数据（本机需走代理时给 npm 进程配 HTTPS_PROXY）。

### 2.14 摘要回填（backfill）

只有每天每源最新 `max_items` 条会拿到摘要，此前未摘要的条目（超额度/失败/兜底）
默认永远空白。开启回填后，每轮运行会额外用独立预算为**最近 N 天内**未摘要的
条目补摘要（最新优先），直到窗口内全覆盖：

```ini
[sourceNNN]
backfill_days = "7"    # 时间窗口（天），默认 0 = 关
backfill_items = "5"   # 每轮回填预算（条），默认 0 = 关
```

- 当前配置：qbitai 7天/5条、ithome 3天/10条、openai-news 7天/5条（窗口内
  才补，1000+ 历史档案超窗永不碰）、awwwards 30天/10条。
- 回填只改 summary/category/content，不改条目集合与顺序；输出不合规时跳过
  留给下轮。

### 2.15 一句话导读 + 赛季/流派 UI（第四轮）

- **摘要格式**：从"200 字分点总结"改为**一句话导读**（`[cfg] summary_length=50`，
  不分点），保留 `<br><br>总结:` 标记；摘要输入带标题（采集器源正文只有 Tags）。
  旧长摘要用 `test/refresh_summaries.py` 一次性置空，靠回填换血。
- **Awwwards 独立分类**：榜单发布/优秀工作室/技术展示/视觉风格/行业资讯
  （见 2.11）。
- **前端信息架构**（参照 poe.ninja）：资讯源 ↔ 赛季（字母徽章 openai=A、
  awwwards=C、量子位/IT之家=D，B 预留新源），分类 ↔ 赛季流派。
  首页 = 赛季分组卡片 + 各源热门分类 top3（计数+占比）；深色游戏风。

## 3. 踩坑记录

1. **机器之心 RSS 已下线**：`jiqizhixin.com/rss` 现在 302 跳转到"数据服务"付费页，返回 HTML 而非 XML；
   RSSHub 也没有它的路由（官方文档 sitemap 查无）。本方案用定位最接近的**量子位**（`qbitai.com/feed`，已验证 200 + 合法 RSS）替代。
   以后想换回来，只需改 `config.ini` 里 source001 的 url。
2. **openai 0.27.8 是旧闻**：上游早已迁移到 1.x SDK，照 README 降级反而会炸（见第 1 节）。
3. **ubuntu-20.04 已下线**：上游 workflow 不改必失败（见 2.6）。
4. **fork 后 Actions 默认禁用**，不点启用按钮，`workflow_dispatch` 和定时都不会跑（见 2.2）。
5. **GitHub cron 是 UTC**，且 Actions 定时任务可能延迟几分钟到几十分钟，不要指望准点。
6. **空 secret = 空字符串**，`OPENAI_BASE_URL` 必须显式填（见 2.4）。
7. **PAT 会过期**：Expiration 到期后 Actions 的 push 步骤会 403，到时重新生成 PAT 并更新 `WORK_TOKEN`。
8. **60 天无仓库活动，GitHub 会自动停用定时 workflow**：届时到 Actions 页点一下 re-enable 即可。
9. **API key 只放 Secrets**：本流程中密钥只出现在 `Settings → Secrets` 和 workflow 的 `${{ secrets.* }}` 引用里，
   不要写进 `config.ini`、`main.py` 或任何提交记录。
10. **摘要条数控制**：`max_items` 是"每次运行最多为几篇新文章生成摘要"，测试期每个源设为 3，
    控制 API 花费；正式用可以调大。
11. **量子位会 403 非浏览器 UA**：上游用 fake_useragent 随机 UA，实测被量子位拒绝（403）。
    `RSS-GPT/main.py` 已改为固定的现代 Chrome UA，不要改回去。
12. **第一次运行很慢**：OpenAI 官方 feed 带全部历史文章（约 1000 篇），首轮要逐篇清洗，
    Actions 第一次跑 10 分钟以上属正常；之后有去重缓存就快了。
13. **feedparser 的属性陷阱**：给 feedparser 的 entry 用点号赋值自定义属性不会写入字典，
    `entry.get('xxx')` 永远拿到 None。读取自定义属性必须用 `getattr(entry, 'xxx', None)`。
    （这是分类功能开发时踩的坑，`RSS-GPT/main.py` 里已修正并注释。）
14. **本地跑采集器源要显式代理**：awwwards.com 在本机直连超时，本地验证需
    `HTTPS_PROXY=http://127.0.0.1:7892`（requests 不一定会读系统代理）；
    同时 `NO_PROXY=127.0.0.1,localhost` 保住本地 mock LLM。GitHub Actions 直连无此问题。
15. **"合并后再截断"治不了传送带**：只要 feed 全量档案 > max_entries，丢弃的条目下轮
    必然被当作新条目重抓，无论截断在合并前后。必须配墓碑文件（见 2.12）。
16. **GitHub Actions 没有 IPv6 路由**：目标站有 AAAA 记录时（如 awwwards），
    首次连接直接 ENETUNREACH（Errno 101，不是 403），要在采集器内强制 IPv4
    （`collectors.py` 的 `_get_ipv4`，AF_INET-only getaddrinfo）。本机有 IPv6/代理
    所以本地验证发现不了这个问题。

## 4. 以后重装 / 加源

- 重装：照第 2 节从头走一遍即可，文件以 fork 仓库为准（本地 `RSS-GPT/` 目录是 fork 的克隆，改完 `git push` 同步，无需网页粘贴）。
- 加源：在 `config.ini` 末尾追加 `[source005]` 段（段名递增即可），填 `name` / `url` / `max_items`，commit 后等下一轮运行。
- 改摘要语言/长度：`[cfg]` 段 `language` 和 `summary_length`。
- 改分类体系：`[cfg]` 段 `categories`（逗号分隔）和 `default_category`；单个源可在自己的 `[sourceNNN]` 段加 `categories` 覆盖全局。
