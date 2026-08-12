# Host Adapters

每个目标软件一个适配器，实现 [Host Adapter Contract v1](../docs/host-adapter-contract-v1-2026-08-12.md)：

| 目录 | 软件 | 形态 | 状态 |
| --- | --- | --- | --- |
| `blender/` | Blender | Python add-on + stdlib HTTP 服务 | 已实现：场景摘要/几何体/移动/程序化别墅/渲染，实机验证通过 |
| `sketchup/` | SketchUp | Ruby 扩展 + `TCPServer` | 已实现并实机验证通过（SketchUp 2025）：摘要/创建长方体（dry-run+回滚） |
| `rhino/` | Rhino | Rhino.Python + stdlib HTTP 服务 | 已实现：场景摘要/长方体（dry-run+回滚），契约测试通过，待 Rhino 实机验证 |
| `_shared/` | - | 适配器共用的注册文件写入（无项目依赖） | 已实现 |

AutoCAD 由仓库内 C# 插件承担适配器职责（本地桥 + 9 个 CAD 可执行工具），已实现 Host Adapter Contract 端点（`/manifest`、`/health`、`/snapshot`、`/tools/<name>`、`/rollback`）并接入同一注册机制（`autocad-main`）。工具清单由 `scripts/export_autocad_host_manifest.py` 从 `cadmcp` 工具注册表生成，测试保证同步。

## 验证

客户端侧发现/调用与适配器协议由 `copilot_backend/tests/test_host_*.py` 覆盖，可在无 Blender 环境运行。
