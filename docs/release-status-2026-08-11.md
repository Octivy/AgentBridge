# AgentBridge 0.9.0.622 预览版能力与验收状态

更新日期：2026-08-11
目标平台：Windows x64、AutoCAD 2024（R24.3）、.NET Framework 4.8

## 1. 阶段结论

| 阶段 | 结论 | 说明 |
| --- | --- | --- |
| 产品收口与目录清理 | 已完成 | 类天正墙、门、窗创建编辑工具、商业账号/积分/套餐/更新平台和旧阶段资料已移出当前产品目录。 |
| 第一阶段：连接器与 CADMCP 代码 | 已完成 | AutoCAD 插件、本地桥、backend、CADMCP、Codex 配置、多模型适配、诊断、安全 Planner 和 Skill 草稿链路均已落地。 |
| 第一阶段：自动化与本机连接验证 | 部分通过 | C#、Python、离线图纸、MCP 契约通过；Codex/CADMCP 20 次初始化、13 工具发现和 AutoCAD 快照读取已有通过报告。 |
| 第一阶段：真实环境最终验收 | 未完成 | 第二 MCP Host 首次安全批准、有效在线模型 10 次门槛、10 张真实 DWG 写图/回滚矩阵仍待完成。 |
| 第二阶段：双线墙与围合空间 | 未开始 | 必须在第一阶段连接器和真实 DWG 门槛通过后启动。 |
| 三维、车库、机械完整 MCP | 未开始 | 属于后续专业 Skill，不属于当前 MVP。 |

因此，当前版本可以作为连接器 MVP 预览版安装测试，但不能声明整个产品路线或双线墙阶段已经完成。

## 2. 当前产品能力

### 2.1 AutoCAD 插件

- AutoCAD 2024 自动加载 Bundle。
- 编译与打包参数同时支持 2014（R19.1）、2016（R20.1）和 2024（R24.3）；默认交付仍以 AutoCAD 2024 为准，2014/2016 包用于本机调试与多版本验证。
- `AICHAT` 打开多模型对话与任务面板。
- `AISNAPSHOT` 导出当前图纸结构化快照。
- `TESTCOPILOT` 检查插件和本地桥状态。
- 标准对话模式不要求登录、积分或套餐。

### 2.2 多模型与企业模型

- OpenAI Chat Completions。
- OpenAI Responses。
- Anthropic/Claude Messages。
- DeepSeek、MiniMax 和其他 OpenAI Compatible 服务。
- 本地 Ollama。
- 无鉴权或自定义鉴权的企业内网 OpenAI 兼容接口。

代码和错误适配已经完成；真实服务仍取决于有效 API Key、模型名称、网络和企业接口兼容性。

### 2.3 Codex、Claude 等 Agent 接入

- 项目级 Codex MCP 配置。
- 独立 `cadmcp` stdio Server。
- 其他 MCP Host 可注册同一启动脚本。
- 固定 13 个产品工具，防止旧工具或未授权能力漂移。
- 当前已有 Codex/CADMCP 20/20 初始化与工具发现报告；Claude Code 配置已存在，但首次项目 MCP 批准仍需用户在 Host 中完成。

### 2.4 图纸读取与理解

- 图层、普通实体、文字、尺寸、块和动态块摘要。
- 自定义对象和代理对象的运行时类型、边界与支持状态。
- 墙、门、窗及未知对象的统一 `FunctionalObject` 识别。
- 无法读取或不支持的对象必须明确返回，不允许静默丢失。

### 2.5 四个 MVP 专业 Skill

1. 图纸快照分析。
2. 功能对象识别。
3. 外围闭合轮廓提取、面积计算和闭合多段线绘制。
4. 图层映射建议与确认后的受控迁移。

这些能力已通过矩形快照等自动化测试；真实复杂 DWG 的准确率、性能和写图可靠性仍需按验证矩阵测试。

### 2.6 安全写图与回滚

- 写操作先预览。
- 一次性权限票据。
- AutoCAD 事务提交。
- 新增或修改实体 Handle 校验。
- 显式回滚，并拒绝覆盖用户提交后的新修改。
- Planner 只能选择 13 个白名单工具。

### 2.7 自有 Agent 与 Skill 草稿

- Planner 支持计划、执行事件、继续、重试、取消和回滚。
- 已完成任务可以转换为持久化的待审核 Skill 草稿。
- 草稿支持编辑、校验和人工批准。
- 批准后仍不会自动启用，不能绕过工具白名单和写图授权。

### 2.8 公司规范可信问答

- 管理员配置 Markdown/TXT 资料根目录。
- 检索后再调用模型。
- 回答要求使用 `[S1]` 等来源编号。
- 缺少来源或伪造来源时标记为未核验。
- 没有检索结果时拒绝生成无依据答案。

PDF、OCR、向量检索和部门级权限隔离尚未实现。

### 2.9 五层诊断

1. backend HTTP。
2. 模型 gateway/provider。
3. CADMCP 工具和 Skill 注册。
4. AutoCAD 本地桥与协议版本。
5. AutoCAD 2024 与当前活动图纸。

## 3. 2026-08-11 自动化结果

- `dotnet build AgentBridge.sln -c Release`：通过，0 警告、0 错误。
- C# 产品边界与插件契约测试：6/6 通过。
- Python 单元测试：129/129 通过（含 4 个子测试）。
- MVP 矩形快照：实体归集、墙识别、外围轮廓和面积全部通过。
- MCP stdio 握手：通过，发现工具数为 13。
- CADMCP wheel：构建并验证通过，包含当前架构模块且不包含 backend 模块。
- GitHub CI（`ci.yml`）：ruff 全绿、pytest 129 通过、wheel 构建校验和 MCP stdio 握手全部通过。

## 3.1 2026-08-11 增补：同步与发布状态

- 4 处产品内 lint 问题已修复，ruff 规则集已在 `pyproject.toml` 固定（E4/E7/E9/F），CI 结果确定可复现。
- PR #1（`agent/cadmcp-mvp-preview`）已合并进 `main`（提交 `e995e11`，随后 `f962eb9` 增加自动预发布工作流）。
- 标签 `v0.9.0.622-preview` 已推送；`.github/workflows/release.yml` 在推送 `v*` 标签时自动创建 GitHub 预发布并上传插件 zip。
- 多版本打包：`scripts/build-plugin-package.ps1` 与 `install.ps1` 已支持 `-AutoCADVersion 2014|2016|2024`，生成对应 Series 的 Bundle 与安装包。
- 2016/2014 测试包已在本机用对应版本程序集编译验证（C# 契约测试 6/6 通过）；AutoCAD 2014/2016 内的 .NET 4.8 运行时兼容性仍需在对应 AutoCAD 实机验证。

## 4. 安装与测试建议

1. 下载 `AgentBridge-0.9.0.622-AutoCAD-2024.zip`。
2. 对照同目录 `latest.json` 检查 SHA-256。
3. 完整解压后运行 `Install-AgentBridge.ps1`。
4. 重启 AutoCAD 2024，执行 `TESTCOPILOT`。
5. 执行 `AICHAT`，先测试标准模式的模型问答。
6. 测试 Codex/Planner 时，从 GitHub 获取项目源码并运行 `start-local-dev.ps1` 与 `scripts/start-cadmcp.ps1`。
7. 在真实 DWG 上先做只读快照和 dry-run，再授权外围轮廓或图层迁移写入。

测试中请记录 AutoCAD/天正版本、DWG 类型、命令、输入、期望、实际结果和日志路径；真实 DWG 验收矩阵见 `docs/real-dwg-validation-matrix-2026-07-18.md`。

## 5. 当前不应期待的能力

- 双线墙配对和中心线提取。
- 门窗开口补口后的房间围合识别。
- 自动平面功能着色。
- 面积规则库和分层面积统计。
- 车库自动排布。
- 二维到三维或完整机械设计 MCP。
- Skill 自动发布或公共 Skill 市场。
