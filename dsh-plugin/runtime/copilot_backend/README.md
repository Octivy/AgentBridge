# AgentBridge Backend

该目录提供聊天/Planner HTTP 服务和多模型适配。CAD 工具的唯一实现与注册表位于根目录 `cadmcp/`；本目录的 `mcp_runtime/` 和 `mcp_server.py` 仅是兼容入口。

## 模块

- `http_api/`：健康检查、聊天、任务、Skill 与工具查询 API。
- `planner/`：计划、技能选择、预览确认、任务状态与执行事件。
- `gateway/`：OpenAI 兼容、Anthropic 兼容及配置化 provider 适配。
- `product/`：模型配置服务。
- `skills/`：当前四个产品 Skill 的注册表，以及待审核用户 Skill 草稿存储。
- `knowledge/`：管理员授权的本地规范资料检索、来源编号和回答核验。
- `acceptance/`：模型、MCP Host 与 AutoCAD 桥重复验收和脱敏报告。
- `shared/`：设置与公共 schema。
- `tests/`：后端和 `cadmcp` 回归测试。

## 当前 Skill

- `drawing_snapshot_analysis`
- `functional_object_recognition`
- `outer_outline_drawing`
- `layer_normalization`

## 启动

```powershell
cd copilot_backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

常用 API：

- `GET /health`
- `GET /connector/capabilities`
- `GET /connector/diagnostics`
- `POST /chat/message`
- `POST /knowledge/query`
- `GET /planner/tasks`
- `GET /planner/tasks/{task_id}`
- `POST /planner/tasks/{task_id}/cancel|resume|retry`
- `POST /planner/tasks/{task_id}/skill-draft`
- `GET|POST /planner/skill-drafts`
- `PUT /planner/skill-drafts/{skill_id}`
- `POST /planner/skill-drafts/{skill_id}/validate|approve`
- `GET /planner/skills`
- `GET /planner/tools`

## 测试

从仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s .\copilot_backend\tests -p "test_*.py"
```

产品工具、权限和 MCP 接入细节见 [MCP 架构](../docs/mcp-architecture.md)。
