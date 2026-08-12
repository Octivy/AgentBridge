# Host Adapters

每个目标软件一个适配器，实现 [Host Adapter Contract v1](../docs/host-adapter-contract-v1-2026-08-12.md)：

| 目录 | 软件 | 形态 | 状态 |
| --- | --- | --- | --- |
| `blender/` | Blender | Python add-on + stdlib HTTP 服务 | 骨架已实现（示例工具） |
| `sketchup/` | SketchUp | Ruby 扩展 + `TCPServer` | 骨架 |
| `rhino/` | Rhino | C# 插件或 Rhino.Python | 规划 |
| `_shared/` | - | 适配器共用的注册文件写入（无项目依赖） | 已实现 |

AutoCAD 暂以仓库内现有 C# 插件承担适配器职责（本地桥 + 13 工具），后续改造为纯适配器并复用同一注册机制。

## 验证

客户端侧发现/调用与适配器协议由 `copilot_backend/tests/test_host_*.py` 覆盖，可在无 Blender 环境运行。
