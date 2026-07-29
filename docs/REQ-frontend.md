# REQ-前端：Vue3 聚合展示页（纯静态）

## 背景
第一、二阶段完成后，管道每天产出 4 个源的 JSONL（量子位/IT之家/OpenAI News/
Awwwards SOTD），托管在 GitHub Pages 上可直接 fetch。第三阶段做聚合展示前端，
替代 Pages 当前的 RSS 链接列表首页。（早期"Vue3 + Supabase"设想经决策降级为
纯静态：数据已静态可访问，无需后端。）

## 需求（用户决策已确认）
1. Vue3 + Vite 单页应用，源码在外层仓库 `web/`，构建产物直接写入
   `RSS-GPT/docs/`（index.html + assets/），与数据同源部署，无跨域。
2. 前端启动时并行 fetch 4 个 JSONL，合并按发布时间降序；单源失败不拖垮整体。
3. 首版功能 = 浏览聚合：源 tabs / 分类 chips（动态收集）/ 关键词搜索
   （标题+摘要）/ 条目卡片（标题、分类徽章、来源、时间、摘要、原文链接，
   Awwwards 显示缩略图）/ 每批 50 条加载更多。移动端适配。
4. 管道让出入口页：`main.py` 的链接列表页改渲染为 `docs/feeds.html`，
   `docs/index.html` 留给前端产物，每日 Auto Build 不再覆盖应用。
5. 无 TS/router/UI 库；构建在本地完成后提交产物，Actions 只跑 Python。

## 验收标准（DoD）
- `npm run build` 成功，产物落入 RSS-GPT/docs/ 且不破坏既有数据文件
- `npm run preview` 可访问，资源路径带 /RSS-GPT/ 前缀
- `test/e2e_verify.py` 两轮仍全绿（管道改动无回归）
- push 后线上 Pages 打开即为应用：四源数据、筛选/搜索/缩略图正常，手机可用

## 边界
- 不做已读/收藏/登录/跨设备同步；不做 SEO、虚拟滚动
- 不改数据层结构、不动 workflow
- 旧 RSS 链接列表以 feeds.html 形式保留
