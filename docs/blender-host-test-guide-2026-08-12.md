# Blender 宿主实机测试指南

日期：2026-08-12
目的：验证 AgentBridge 的“外部软件宿主”模式——Blender 作为第一个非 AutoCAD 宿主，通过 Host Adapter Contract v1 接入 AgentBridge 客户端，可被 Codex/Claude 等 Agent 操作。

## 1. 前置条件

- Windows + Blender 5.x（本机已装 Blender 5.1，路径 `D:\Program Files\Blender Foundation\Blender 5.1\blender.exe`）。
- Python 3.10+，已安装项目依赖（`pip install -e . -r copilot_backend/requirements.txt`）。

## 2. 方式 A：一键自动验证（推荐先跑这个）

在仓库根目录执行：

```powershell
python .\scripts\verify_blender_host.py
```

脚本自动：后台启动 Blender → 注册宿主 → 验证 manifest / 健康检查 / 快照 → 立方体 dry-run 预览 → 授权提交（真实创建）→ 回滚删除。输出 `BLENDER HOST VERIFICATION PASSED` 即通过。

## 3. 方式 B：GUI 手动验证（模拟真实使用）

### 3.1 安装插件

1. 打开 Blender 5.x。
2. `Edit > Preferences > Add-ons > Install...`，选择：
   `H:\codex\AgentBridge\artifacts\releases\agentbridge-blender-host-v0.1.zip`
3. 在列表里搜索 **AgentBridge Host**，勾选启用。

### 3.2 启动宿主

1. 按 `F3` 搜索 **AgentBridge: Start Host** 并运行（或在顶部 `Render` 菜单里点）。
2. 信息区（左下角）会显示 `AgentBridge host listening on http://127.0.0.1:xxxxx`。
3. 宿主注册文件写入 `%LOCALAPPDATA%\AgentBridge\hosts\blender-main-<pid>.json`。

### 3.3 启动客户端并查看宿主

```powershell
cd H:\codex\AgentBridge\copilot_backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000/ui`，应看到 **Blender 5.1** 宿主卡片（状态 ok）和 `blender_scene_summary`、`blender_create_cube` 两个工具。

### 3.4 用 Codex 操作 Blender

在 `H:\codex\AgentBridge` 目录打开 Codex（`.codex/config.toml` 已注册 `hostmcp`）：

1. 让 Codex 调用 `blender_scene_summary` 读取当前场景。
2. 让 Codex 创建一个小立方体（如“在原点创建一个 size=1 的立方体”）：应先 dry-run 预览，再在你确认后提交。
3. 让 Codex 回滚刚才的立方体（`rollback`），确认场景恢复原状。

## 4. 回馈记录表

| 测试项 | 期望 | 实际 | 通过 |
| --- | --- | --- | --- |
| 一键验证（方式 A） | BLENDER HOST VERIFICATION PASSED | | |
| 插件安装与启用 | AgentBridge Host 可勾选 | | |
| Start Host | 显示监听地址，注册文件生成 | | |
| /ui 宿主卡片 | Blender 状态 ok、2 个工具 | | |
| Codex 读场景 | 返回对象/场景摘要 | | |
| Codex 建立方体 | dry-run 预览 → 确认后真实创建 | | |
| 回滚 | 立方体删除，场景恢复 | | |

失败时把 `%LOCALAPPDATA%\AgentBridge\hosts\` 下的注册文件、Blender 信息区报错和 `client.log` 一并反馈。

## 5. 常见问题

- **宿主没出现**：确认先执行了 Start Host；检查注册目录 `%LOCALAPPDATA%\AgentBridge\hosts` 是否有 `blender-main-*.json`。
- **/ui 连不上**：确认 backend 已启动、端口 8000。
- **Codex 看不到工具**：确认 `hostmcp` 在 Codex 里已连接（工具名以 `blender_` 开头）。
- **写操作被拒**：写工具非 dry-run 必须携带授权票据；先跑 dry-run 再提交。

## 6. 通过后进入下一步

Blender 验证通过后，按路线依次做：AutoCAD 插件改造成标准宿主适配器（接入同一注册机制）→ SketchUp（Ruby）→ Rhino。
