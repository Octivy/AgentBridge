# 项目目录清理报告

日期：2026-07-19

## 结论

开发目录已按“AutoCAD 2024 + cadmcp + 四个 MVP Skill”重新收口。旧类天正工具、建筑对象内核、空间深化算法、历史阶段资料、旧 NAS/企业部署资料和构建生成物不再参与当前开发。

备份根目录：

`E:\AgentBridge\_backup_legacy_projects\cadcopilot_mvp_cleanup_20260719_011715`

本次操作采用移动和修改前副本备份，没有删除业务源码。备份目录中的 `archive-manifest/` 记录了主要归档范围，`mixed-before-cleanup/` 保存了拆分前的混合文件，`additional-unrelated/` 保存了后续发现的无关资料。

## 保留的开发目录

| 目录/文件 | 用途 | 保留原因 |
| --- | --- | --- |
| `Core/` | 配置、本地桥、主线程调度 | AutoCAD 与 MCP 连接核心 |
| `Engine/` | 快照、写图事务、校验和回滚 | 四个 MVP Skill 的 CAD 基础 |
| `LLM/` | 插件/backend 数据契约与客户端 | UI、Planner、多模型连接 |
| `Plugin/` | `AICHAT`、`AISNAPSHOT`、诊断命令 | AutoCAD 2024 最小入口 |
| `UI/` | 聊天、任务、权限确认界面 | 用户操作面 |
| `cadmcp/` | MCP Server、13 个工具与语义能力 | 产品工具唯一实现 |
| `copilot_backend/` | Planner、HTTP、多模型 provider | AI 编排与连接 |
| `AgentBridge.Tests/` | C# 产品边界契约测试 | 防止旧工具回流 |
| `scripts/` | MCP 启动与当前验证脚本 | 开发和验收 |
| `docs/` | 当前产品、架构、开发、验证文档 | 唯一有效文档集 |

## 已移出的内容

- C# `Architecture/` 与 `ArchitectureToolbarPalette`：旧类天正命令、构建器和工具栏。
- Python 建筑对象内核与工具：墙、开口、房间、轴网、构件、规则、指标、模板、布局等。
- 空间深化算法：双线围合、房间闭合、空间修补和旧语义存储。
- 与上述能力绑定的单元测试、压力测试和 AutoCAD E2E 脚本。
- v1-v4 PRD、旧阶段计划、天正对标资料、旧开发日志、UED 截图和过程交接资料。
- 旧 `bridge_service`、NAS/企业部署目录和配置模板。
- 账号、积分、套餐、发布清单、部署快照和后台门户等产品平台层。
- 旧建筑标准、规则、指标和绘图模板 JSON 数据。
- 采样脚本、编码修复脚本、旧发布门禁脚本和历史构建报告。

## 混合文件处理

下列文件既包含当前能力又包含旧能力，因此先备份原件，再做定向收口：

- `Plugin/Commands.cs`
- `Core/LocalToolBridge.cs`
- `Engine/CommandExecutor.cs`
- `UI/ChatPanel.xaml(.cs)`
- `AgentBridge.Tests/Program.cs`
- `cadmcp/tool_registry.py`、`tool_executor.py`、`tools/architecture.py`
- `copilot_backend/skills/registry.py`、`planner/prompt_builder.py`
- `README.md`、`docs/work-plan.md`
- `copilot_backend/http_api/routes.py`、`gateway/service.py` 及其测试

## 当前产品防线

- MCP 注册表只包含 13 个产品工具。
- Skill 注册表只启用 4 个产品 Skill。
- AutoCAD 命令中没有 `AITOOLBAR`、`AIWALL*`、`AIDRAW` 等独立工具入口。
- C# 契约测试检查旧架构标识不得重新进入插件和 UI。
- 写入必须经过预览票据，本地桥还会检查 `permission_request_id`。

## 恢复方式

如需查阅或迁移旧实现，从备份目录按原相对路径复制到独立项目，不应直接复制回当前开发目录。若未来第二阶段需要双线墙或围合空间算法，应以独立模块重新引入，并只通过新的产品 Skill 接口连接。
