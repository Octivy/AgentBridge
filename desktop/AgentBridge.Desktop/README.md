# AgentBridge.Desktop（方案 B 桌面应用）

产品级桌面应用壳：WPF + WebView2，作为 Agent（Codex / Claude / 其他 MCP 客户端）与本地软件
（AutoCAD、Blender、SketchUp、Rhino …）之间的桥接控制台。

## 职责（当前已实现）

- 托管 backend 进程：自动定位仓库与 Python，启动 `uvicorn app:app`，每 3 秒健康检查，崩溃自动重启。
- 主窗口 + 侧边导航（总览 / 软件配置 / 连接监控 / Agent 接入 / 任务交付 / 设置），内容由 WebView2
  加载配置中心 UI（`http://127.0.0.1:8000/ui`）。
- 托盘：最小化到托盘、显示主窗口、重启后端、退出。
- 状态栏：backend 运行状态与版本。

## 构建与运行

```powershell
dotnet build .\desktop\AgentBridge.Desktop\AgentBridge.Desktop.csproj -c Release
.\desktop\AgentBridge.Desktop\bin\Release\net8.0-windows\AgentBridge.Desktop.exe
```

显式指定仓库根目录（当 exe 不在仓库内运行时）：

```powershell
.\AgentBridge.Desktop.exe "H:\codex\AgentBridge"
```

## 安装器（Inno Setup）

产出 `dist\AgentBridge-Setup-<版本>.exe`，目标机器无需预装 Python / .NET：

```powershell
.\scripts\pack-desktop-installer.ps1 -CompileWithIscc -Version 1.0.0   # 打包 + 编译
.\scripts\test-installer-bootstrap.ps1 -Version 1.0.0                  # 静默安装→启动→健康→卸载
```

安装布局与说明见仓库根 README「安装器（Inno Setup）」一节。

## 依赖

- .NET 8 SDK / Runtime（开发与调试；**安装器版本自包含，无需目标机器安装**）
- WebView2 Runtime（Windows 10/11 一般自带，安装器会在缺失时提示）
- backend Python 环境（开发用；**安装器版本内置 `backend\runtime` 运行时**）

## 配置中心 API（backend 侧）

`/config/hosts` 系列接口管理软件（Host 适配器）配置：

- `GET /config/hosts` 列出软件与实时状态（注册 / 健康 / 进程）
- `POST /config/hosts` 新增；`PUT/DELETE /config/hosts/{host_id}` 更新 / 删除
- `POST /config/hosts/{host_id}/test|start|stop` 测试连接 / 启动 / 停止
- `GET /config/hosts/{host_id}/status` 单项状态
- `POST /config/hosts/auto-start` 启动所有标记为自动拉起的软件

Agent 接入（MCP 注册管理）：

- `GET /config/mcp/preview` 预览 Codex / Claude 接入配置
- `POST /config/mcp/codex` 合并写入 `~/.codex/config.toml`
- `POST /config/mcp/claude` 写入项目根 `.mcp.json`（自动备份旧文件）
- `GET /config/mcp/status` 查看 Codex 已注册与可生成的服务

控制面 MCP（`python -m control_mcp`，随 Codex 接入自动注册为 `agentbridge`）：

- 自查软件桥：`ab_list_software` / `ab_software_status` / `ab_test_connection`
- 管理桥：`ab_add_host` / `ab_update_host` / `ab_remove_host` / `ab_start_host` / `ab_stop_host`
- 接入管理：`ab_preview_mcp` / `ab_register_with_codex` / `ab_register_with_claude`
- 自搭桥：`ab_scaffold_adapter` 为没有 MCP 的软件生成 Host Adapter 脚手架
- 任务交付：`ab_list_deliveries` / `ab_record_deliverable` / `ab_set_handoff`

配置持久化于 `%LOCALAPPDATA%\AgentBridge\host_configs.json`，首次运行自动写入
AutoCAD / Blender / SketchUp / Rhino 四个默认条目。

任务交付记录持久化于 `%LOCALAPPDATA%\AgentBridge\deliveries.json`，
API 见 `/delivery/tasks` 系列（交付物登记、交接总结、查询）。
