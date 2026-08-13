# Rhino 宿主实机验收记录

日期：2026-08-13
目的：验证 AgentBridge 的 Rhino 宿主（Host Adapter Contract v1）——宿主在 Rhino 内以脚本方式启动，
通过 HTTP 注册到 AgentBridge，Codex/其他 Agent 可调用 `rhino_scene_summary` / `rhino_create_box`，
创建的长方体出现在 Rhino 界面中，且支持回滚删除。

## 1. 环境

- Windows 11 + Rhino 8（本机：`C:\Program Files\Rhino 8\System\Rhino.exe`，中文界面）。
- Python 3.11（`C:\Users\chang_k\AppData\Local\Programs\Python\Python311\python.exe`）。
- 仓库：`H:\codex\AgentBridge`。

## 2. 安装适配器

```powershell
python -c "import sys; sys.path.insert(0, r'H:\codex\AgentBridge\copilot_backend'); from adapter_install.rhino import install_rhino_adapter; print(install_rhino_adapter())"
```

会把 `adapters/rhino/` 复制到
`%APPDATA%\McNeel\Rhinoceros\8.0\scripts\agentbridge_rhino\`，
并写入启动脚本 `AgentBridgeHost_startup.py`。

## 3. 启动宿主（手动）

1. 打开 Rhino 8（建议全新文档）。
2. 命令栏输入 `_-RunPythonScript` 回车，粘贴：
   `C:\Users\chang_k\AppData\Roaming\McNeel\Rhinoceros\8.0\scripts\AgentBridgeHost_startup.py`
3. 命令栏出现 `AGENTBRIDGE_RHINO_HOST_READY http://127.0.0.1:<port> <token>` 即成功；
   启动脚本应立即返回，Rhino 不卡死（主线程不阻塞）。
4. 注册文件写入 `%LOCALAPPDATA%\AgentBridge\hosts\rhino-main-<pid>.json`。

> 说明：`_-RunPythonScript` 在命令栏粘贴时可能显示乱码，但实际可执行；
> 若提示“不支持的文件类型”，清空命令栏重试一次即可。

## 4. 验收结果（2026-08-13，Rhino 8，PID 21008）

通过控制面/HTTP 直接调用 host：

| 步骤 | 工具 | 结果 |
| --- | --- | --- |
| 1 | `rhino_scene_summary`（基线） | ✅ `object_count=0`，约 100ms |
| 2 | `rhino_create_box` dry-run | ✅ 返回 8 角点预览，不写文档 |
| 3 | `rhino_create_box` apply（10×10×10，原点） | ✅ 返回 object_id；**Rhino 界面可见立方体**（缩放全部后确认） |
| 4 | `rhino_scene_summary` | ✅ `object_count=1` |
| 5 | `/rollback` | ✅ `deleted=true`；**Rhino 界面立方体消失**（用户确认） |
| 6 | `rhino_scene_summary` | ✅ `object_count=0` |

中文对象名（如“验收盒”）UTF-8 往返正常。

## 5. 架构要点（本次修复）

- **主线程执行**：Rhino 文档线程不安全、`RhinoDoc.ActiveDoc` 在后台线程不可靠。
  `background_host.py` 通过 `RhinoExecutor`（WinForms 定时器 + `RhinoApp.Idle` 双通道）
  把全部工具执行排到主线程；启动日志记录 `timer=True idle=True`。
- **显式文档操作**：`backend.py` 的 `create_box` 改用 RhinoCommon
  （`doc.Objects.AddBrep`），不再依赖 `scriptcontext` / `rhinoscriptsyntax` 的隐式文档。
- **可靠计数与回滚验证**：`scene_summary` 遍历对象表统计；`rollback` 先按 GUID 删除并
  扫描验证，写 `%LOCALAPPDATA%\AgentBridge\rhino-rollback.log`。
- **看门狗兜底**：主线程通道 8 秒未排空则直接执行，避免调用挂死。

## 6. 已知边界

- 宿主按“启动时活动文档”工作：若用户中途新建/切换文档，需重启宿主脚本重新绑定。
- 自动启动（settings XML StartupCommands）未生效，暂用手动 `_-RunPythonScript` 方式；
  一键安装按钮已接入客户端。
