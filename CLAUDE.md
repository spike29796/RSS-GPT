# 开工先读手册

包工头说你是谁，你就读谁的岗位手册，再读厂区结构.md：

- 头头.md / 员工.md / 测试.md — 岗位手册
- 厂区结构.md — 地盘与权限、status/ 状态文件、状态枚举
- 既有项目接入.md — 旧项目接入流程（T-000 体检单起步）

**共享区 = `D:\vibe-coding\factory-shared\`**（本仓库父目录下的 factory-shared 目录，绝对路径，仓库外，不进 git）。
工单 tickets/、状态 status/、交付物 artifacts/、ideas.md、report.md 一律读写共享区，本仓库里只有手册和业务代码。

ideas.md（共享区里）有冻结挂起的事项，动手前先看清哪些活是冻着的。

## git 纪律

- 工单测试岗验收 PASS 后，头头把该工单分支合并进 main 并 commit 一次（一单一个 commit）。
- 包工头本轮吩咐的任务全部 PASS 后，头头 push 一次。
- 除此两个节点外，任何人不主动往 main commit / push；员工在自己分支上的施工 commit 不限。
