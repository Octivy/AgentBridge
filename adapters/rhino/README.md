# Rhino Host Adapter

基于 Host Adapter Contract v1 的 Rhino 适配器（Python，复用 `adapters/blender/host.py` 的
标准库 HTTP 宿主）。

## 工具

- `rhino_scene_summary`：读取（对象数、图层、文档名）
- `rhino_create_box`：写入（dry-run 预览 → 一次性授权 → 创建 → 可回滚）

## 安装与运行

1. 在 Rhino 中打开 Python 编辑器（`Tools → Python Editor`）。
2. 运行 `adapters/rhino/background_host.py`（或把它加进 Rhino 启动脚本）。
3. 宿主会注册到 `%LOCALAPPDATA%\AgentBridge\hosts`，配置中心即可看到并托管。

> 说明：本适配器代码与契约测试已在无 Rhino 环境下验证（fake rhinoscriptsyntax）；
> 真实对象操作需在安装 Rhino 的机器上做最终验收。
