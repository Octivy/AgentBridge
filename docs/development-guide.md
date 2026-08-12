# AgentBridge 开发指南

更新日期：2026-07-21

## 产品边界

当前仓库只开发 AutoCAD 2024 插件、MCP 连接、图纸读取、功能对象识别、外围轮廓和图层统一。不得在本仓库重新加入墙、门、窗、房间等类天正创建编辑工具；这些能力已有独立备份/项目。

## 代码边界

- C# 插件：`Core/`、`Engine/`、`LLM/`、`Plugin/`、`UI/`。
- MCP 唯一实现：`cadmcp/`。
- Planner 与模型连接：`copilot_backend/`。
- 产品工具唯一清单：`cadmcp/tool_registry.py`。
- 产品 Skill 唯一清单：`copilot_backend/skills/registry.py`。
- 当前文档入口：`product-prd-v5-semantic-conversion.md` 与 `work-plan.md`。

## 修改规则

1. 新工具先判断是否直接服务四个 MVP Skill；否则不进入第一阶段。
2. 写工具必须支持 dry-run、一次性权限票据、提交校验；实体变更应尽可能支持回滚。
3. AutoCAD 数据库操作必须在主线程、DocumentLock 和 Transaction 中执行。
4. 快照读取不得静默丢弃天正/代理对象；无法解释时返回类型、Handle、图层和范围。
5. 工具注册表、Planner prompt、HTTP 列表、MCP 列表和本地桥路由必须同步。
6. 修复真实 DWG 失败时，优先保存脱敏快照并增加自动回归用例。
7. 当前先完成连接器 C0-C3 门槛；连接器未达标前，不扩大真实 DWG 标注投入和专业 Skill 数量。
8. 不得重新加入插件用户登录、积分、套餐、用量或在线更新平台依赖。

## 构建和测试

```powershell
dotnet build .\AgentBridge.sln -c Debug
.\AgentBridge.Tests\bin\Debug\net48\AgentBridge.Tests.exe
.\.venv\Scripts\python.exe -m unittest discover -s .\copilot_backend\tests -p "test_*.py"
.\copilot_backend\.venv\Scripts\python.exe .\scripts\validate_mvp_snapshot.py .\scripts\fixtures\mvp-rectangle-snapshot.json --expected .\scripts\fixtures\mvp-rectangle-expected.json
.\copilot_backend\.venv\Scripts\python.exe .\scripts\test_mcp_stdio_handshake.py
```

连接器阶段最后在 AutoCAD 2024 中测试 `AICHAT`、`AISNAPSHOT`、MCP 健康检查和连续快照读取。连接器门槛通过后，再测试外围轮廓写入、图层迁移与回滚；真实图纸记录格式见 `real-dwg-validation-matrix-2026-07-18.md`。

## 完成标准

- C# 与 Python 自动测试全绿；
- MCP 只暴露 13 个产品工具；
- 不新增旧架构依赖或独立专业创编命令；
- 文档、配置模板和测试与实现一致；
- 涉及真实 DWG 的结论附样本、指标或明确的人工验证状态。
