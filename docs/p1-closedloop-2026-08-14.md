# AgentBridge P1 闭环实现状态（2026-08-14）

> 依据：`gap-analysis-client-productization-2026-08-13.md` 的最终目标——"陌生人 10 分钟闭环"
> （安装 → 连接软件 → 配模型 → 下一句话命令 → 看到智能体操作软件 → 拿到交付物）。
> 上一轮已完成 P0 四项（模型配置进面板、统一连接动线、本机软件探测、首次运行向导）；
> 本轮补齐挡在闭环中间的三项 P1 缺口。

## 1. 本轮完成

### 1.1 annotate 写确认落为真实交互（原死穴）

之前的问题：面板有"写操作需确认（annotate）"选项，但写操作被拦截后没有任何确认/继续的
交互落点，用户选了也走不通。现在：

- annotate 模式下，Agent 循环在**第一个写工具调用**处停下：任务状态 `needs_confirmation`，
  `pending_write` 携带工具名、调用 ID 与完整参数。
- 面板渲染"智能体请求执行写操作"确认卡：工具名 + 参数 JSON + **批准并继续 / 拒绝**。
- **批准**：按 dry-run → 一次性票据 → 提交执行该写操作，把结果写回对话历史，继续循环。
- **拒绝**：把"用户拒绝了这次写操作"作为工具错误结果喂回模型，让它总结或改道。
- **其后每一次新的写操作都会再次停下等确认**（per-write 确认，不是一次批准全程放行）。
- 确认状态持久化于 `%LOCALAPPDATA%\AgentBridge\agent_tasks.json`（最近 50 条），
  backend 重启后待确认任务仍可继续确认。

### 1.2 Agent 任务过程可视化（原 90 秒同步黑盒）

- `POST /agent/task` 改为异步：立即返回 `task_id` + `status`，不再同步阻塞到超时。
- 循环每一步（思考内容 / 工具调用 ✓✗ / 被拦截的写）实时写入任务记录；
  面板 800ms 轮询 `GET /agent/tasks/{task_id}` 渲染时间线（等待确认时 2.5s 轮询，
  其他窗口确认后本面板自动跟上）。
- 总览首屏"给智能体下命令"与任务交付页共用同一任务面板组件。
- 任务失败（如模型离线）显示具体错误而不是静默挂起。

### 1.3 交付物可消费（原"只到登记，没到交付"）

交付卡片每个交付物新增动作：

- **打开**：用系统默认程序打开文件。
- **打开目录**：Explorer 定位到文件。
- **预览**：截图/图片类交付物内联显示（后端流式返回，30MB 上限）。
- **回滚**：解析工具令牌台账（两种形态：`created` 二元组 / `objects[].rollback_token`，
  自动去重），列出全部令牌，支持单令牌回滚与"全部回滚"。回滚通过任一已注册在线宿主的
  `POST /rollback` 执行，宿主离线或令牌不属于台账时给出明确错误。

## 2. 新增/变更 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/agent/task` | **变更**：异步启动，立即返回任务记录 |
| GET | `/agent/tasks` | 任务列表（最近 N 条） |
| GET | `/agent/tasks/{task_id}` | 任务详情（步骤时间线，不含内部 history） |
| POST | `/agent/tasks/{task_id}/confirm` | `{"approve": true|false}` 批准/拒绝 pending_write |
| POST | `/delivery/tasks/{id}/deliverables/{i}/open` | 系统打开 |
| POST | `/delivery/tasks/{id}/deliverables/{i}/reveal` | 打开所在目录 |
| GET | `/delivery/tasks/{id}/deliverables/{i}/file` | 预览文件内容 |
| GET | `/delivery/tasks/{id}/deliverables/{i}/rollback-tokens` | 台账令牌列表 |
| POST | `/delivery/tasks/{id}/deliverables/{i}/rollback` | `{"token": "..."}` 执行回滚 |

代码位置：`agent/task_store.py`（持久化）、`agent/task_runner.py`(编排)、
`agent/host_task.py`（`build_task_context` / `confirm_policy` 抽取）、
`agent/loop.py`（`AgentResult.history` 供续跑）、`delivery/actions.py`（交付动作）、
`http_api/routes.py`、`http_api/ui.html`。

## 3. 验证结果（2026-08-14）

- `python -m pytest copilot_backend/tests`：**269 通过**（241 旧 + 28 新），含
  `test_agent_task_flow.py`（异步流 / annotate 拦截 / 批准提交 / 拒绝回喂 /
  连续写逐个确认 / 失败可见）、`test_delivery_actions.py`（台账两形态 / 预览 /
  回滚成功与错误路径）、`test_http_task_routes.py`（路由 400/404/409 + UI 元素冒烟）。
- ruff 全绿；桌面端 Release 构建通过。
- 真机冒烟（本机 backend + 真实交付数据）：
  - `dxf-rhino-plan-1f` 台账解析出 **414 个回滚令牌**；
  - PNG 交付物预览 200（image/png，40KB）；
  - 宿主离线时回滚返回明确指引；令牌不属于台账被拒绝；
  - 非待确认状态调用 confirm 返回 409；任务视图不含内部 history。

## 4. 剩余差距（相对"陌生人 10 分钟闭环"）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| P1 #5 双壳二选一 | 已完成 | 保留 `desktop/`，删除 `client/` 托盘壳（2026-08-14） |
| annotate 确认的 dry-run 预览呈现 | 已完成 | 写操作被拦截时执行 dry-run 取预览，确认卡渲染摘要 + 预览数据 |
| P2 真安装器（MSIX/Inno + 内嵌运行时） | 未做 | 仍依赖预装 Python + .NET |
| P2 连接自愈可见化 | 已完成 | 事件日志 + 桥进程守护（崩溃自动重启/预算/端口归因）+ 监控页事件流 |
| P2 陌生环境实测 | 未做 | 需要未接触过项目的人从零安装一遍 |
| 交接遗留：两个窗未挂接 | 未做 | 需人工确认图纸问题（见 handover 文档） |
| 交接遗留：AutoCAD 2014–2024 实机连接验证 | 未做 | 已纳入一键连接编排，缺实机记录；复验矩阵见 `host-verification-matrix-2026-08-14.md` |
