# RSS-GPT · 个人 AI 资讯聚合平台

用 **GitHub Actions 每日自动抓取**多个资讯源，调用大模型生成**中文一句话导读**，由 **Vue3 前端**聚合展示，托管在 **GitHub Pages**——零服务器成本，手机可直接访问。

> 线上演示：https://spike29796.github.io/RSS-GPT/（GitHub Pages 自动部署）

---

## ✨ 特性

- **每日自动采集**：GitHub Actions 定时任务抓取 9 个 RSS 源 + B站官方 API（`cron-job.yml`，每日凌晨跑）
- **LLM 中文导读**：OpenAI 兼容 API 为每条生成一句话中文摘要（`config.ini` 可切换模型/源）
- **Vue3 前端聚合页**：
  - 双语主题（日/夜）+ 一键翻译（标题/标签）
  - 模糊搜索（中英文）
  - 资讯源卡墙：一源一卡、卡内滚轮滚动前 20 条（newsnow 风格）
  - **B站模块**：coverflow 轮播、B站详情页（标题 + 150×100 封面）、**视频就地播放**（B站官方 iframe 内嵌，点开即播）
- **零服务器成本**：GitHub Actions 当定时器 + 运行环境，GitHub Pages 当静态托管

## 🛠 技术栈

| 层 | 技术 |
|----|------|
| 采集管线 | Python（`main.py` / `collectors.py` / `bilibili_collect.py`） |
| 自动化 | GitHub Actions（定时采集 / Pages 发布 / semgrep 扫描 / feedparser fuzz） |
| 前端 | Vue 3 + Vite（`web/`） |
| 托管 | GitHub Pages（发布 `RSS-GPT/docs/`） |

## 📦 仓库结构

```
├── RSS-GPT/              采集管线（main.py / collectors.py / config.ini）
│   └── docs/             构建产物 + 数据（= GitHub Pages 发布目录）
├── web/                  Vue3 前端源码
├── docs/                 模块文档（MOD-*.md）
├── .github/workflows/    定时采集 / Pages 发布 / 安全扫描 / fuzz
└── CLAUDE.md             开发协作约定
```

## 🚀 快速开始（部署）

1. **Fork 本仓库**（保留仓库名）
2. **启用 GitHub Actions**（fork 默认禁用，在 Settings → Actions 打开）
3. **配置 Repository Secrets**（5 个：OpenAI API Key、Personal Access Token 等，见 `RSS-GPT/config.ini` 与 cron workflow 注释）
4. **开启 GitHub Pages**（Source 选 Actions，发布 `RSS-GPT/docs/`）
5. **手动触发一次** cron workflow（Actions → cron-job → Run workflow）验证采集与部署

> 前端改动后：在 `web/` 跑 `npm run build`，产物落到 `RSS-GPT/docs/`，随 commit 推送后 Pages 自动更新。

### 本地跑（接本地 LLM）

想用**本地 LLM**（Ollama / LM Studio 等 OpenAI 兼容端点）在**自己机器**上采集：

```bash
cd RSS-GPT
cp .env.example .env          # Windows: copy .env.example .env
# 编辑 .env：填 OPENAI_BASE_URL（如 http://127.0.0.1:11434/v1）、CUSTOM_MODEL、OPENAI_API_KEY（本地可留空）、U_NAME
pip install -r requirements.txt
python run_local.py            # 跑管线 + 提交 docs/（加 --push 自动推送到 origin）
```

- `.env` 已被 gitignore，密钥不进仓库
- GitHub Actions 的 cron-job 已改手动触发（云端连不到 localhost 的本地 LLM）

## 📄 许可

MIT（见 [RSS-GPT/LICENSE](RSS-GPT/LICENSE)）

---

> 本仓库由 [yinan-c/RSS-GPT](https://github.com/yinan-c/RSS-GPT) 深度定制而来：新增 Vue3 聚合前端、B站采集与轮播/详情页/就地播放、双语主题、模糊搜索等。

- https://openai.com/news/rss.xml -> https://None.github.io/RSS-GPT/openai-news.xml
- https://www.qbitai.com/feed -> https://None.github.io/RSS-GPT/qbitai.xml
- https://simonwillison.net/atom/everything/ -> https://None.github.io/RSS-GPT/simonwillison.xml
- https://www.geekpark.net/rss -> https://None.github.io/RSS-GPT/geekpark.xml
- https://www.ithome.com/rss/ -> https://None.github.io/RSS-GPT/ithome.xml
- https://www.producthunt.com/feed -> https://None.github.io/RSS-GPT/producthunt.xml
- https://www.infoq.cn/feed -> https://None.github.io/RSS-GPT/infoq.xml
- https://blogs.nvidia.com/feed/ -> https://None.github.io/RSS-GPT/nvidia-blog.xml
