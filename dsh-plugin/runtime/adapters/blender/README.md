# Blender 适配器（参考实现）

安装：

1. 在 Blender 中 `Edit > Preferences > Add-ons > Install...`，选择本目录（或压缩为 zip）。
2. 勾选启用 **Development: AgentBridge Host**。
3. F3 搜索 `AgentBridge: Start Host` 运行，或从顶部 `Render` 菜单启动。

启动后适配器：

- 监听 `127.0.0.1` 随机端口（端点显示在信息区）。
- 写入注册文件 `%LOCALAPPDATA%\AgentBridge\hosts\blender-main-<pid>.json`，AgentBridge 客户端轮询发现。
- 暴露 2 个示例工具：`blender_scene_summary`（只读）、`blender_create_cube`（写、支持 dry-run 与回滚）。

Blender 操作在 `bpy.app.timer` 驱动的队列中于主线程执行，HTTP 服务线程只负责接收请求，避免 bpy 线程安全问题。

## 实机验证

仓库内提供一键验证（需要本机安装 Blender）：

```powershell
python .\scripts\verify_blender_host.py
```

脚本以 `--background` 启动 Blender，通过注册发现宿主，验证 manifest/health/snapshot、写操作 dry-run、授权提交和回滚，全部通过后输出 `BLENDER HOST VERIFICATION PASSED`。

## 与现有插件的区别

Blender 适配器不含任何聊天 UI 和模型逻辑，只实现 Host Adapter Contract v1。全部智能来自外部 Agent（Codex/Claude 等），经 AgentBridge 客户端接入。
