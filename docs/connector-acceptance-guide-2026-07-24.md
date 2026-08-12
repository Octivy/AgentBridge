# AgentBridge 连接器验收指南

更新日期：2026-07-24

## 一键验收

在仓库根目录运行：

```powershell
.\scripts\run-connector-acceptance.ps1
```

该命令自动检查 Codex 配置、Claude Code 第二 Host、20 次独立 MCP 初始化和工具发现、10 次模型请求，以及 20 次 AutoCAD 本地桥健康检查，并在 `docs/validation/` 生成脱敏 JSON 和 Markdown 报告。

报告状态：

- `passed`：达到当前门槛；
- `failed`：代码或已配置外部服务确实失败；
- `blocked`：缺少 AutoCAD、Host 批准或模型配置，未伪装为通过；
- `warning`：可以继续，但存在非阻断风险。

## 当前现场状态

- Codex 项目 MCP 配置通过；
- Claude Code 2.1.198 已安装，`.mcp.json` 已创建，但项目 MCP 仍需在 Claude Code 中批准；
- CADMCP 20/20 次初始化及工具发现通过，工具漂移为 0；
- 当前 MiniMax 凭据被服务端判定为无效，运行器已分类为 `authentication` 并停止后续付费请求；
- AutoCAD 2024 已自动定位、安装当前插件包并启动；本地桥健康检查与图纸快照读取 20/20 通过。
- backend 已通过五层诊断，5 个组件状态完整且总状态为 `ok`。
- Ollama 当前未运行。

当前证据见 [连接器验收报告](validation/connector-acceptance-20260724-020554.md)。

## AutoCAD 验收

1. 启动 AutoCAD 2024，加载当前 Release 构建的 `AgentBridge.dll`。
2. 打开一张测试 DWG，确认 `TestCopilot` 和 `AICHAT` 可用。
3. 再运行一键验收脚本。
4. 桥通过后，从 Codex/Claude 测试快照读取、外围轮廓 dry-run、拒绝授权、确认写入和回滚。

## Claude Code 验收

项目已经生成 `.mcp.json`。首次进入项目时，Claude Code 会要求批准项目级 MCP Server；这个安全批准必须由本机用户在 Claude 界面完成，程序不绕过。

批准后运行：

```powershell
claude mcp get cadmcp
```

状态应为 `Connected`，随后重新运行一键验收。

## 模型验收

修复 `.env` 中的模型凭据后重新运行。报告不会保存 API Key 或完整回答，只记录 provider、成功率、延迟、回答长度、短 SHA-256 和脱敏错误类别。

## 公司规范知识库

在 `copilot_backend/.env` 配置管理员批准的资料目录：

```dotenv
CADCOPILOT_KNOWLEDGE_ROOTS=D:\CompanyStandards\Approved
```

第一版只读取 UTF-8 Markdown 和 TXT，不扫描未授权目录。服务模式调用：

```http
POST /knowledge/query
{
  "question": "标准车位宽度是多少？",
  "provider": "enterprise_private",
  "api_base_url": "http://company-model.internal/v1",
  "model": "company-model"
}
```

没有检索来源时不会调用模型生成答案；模型没有返回 `[S1]` 来源编号时，结果标记为未核验。
