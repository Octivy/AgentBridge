# AgentBridge 连接器、Agent 与 Skill 路线图

更新日期：2026-07-24

## 1. 本轮产品裁决

项目继续采用“先验证连接与任务闭环，再增加专业算法”的 MVP 路线。当前产品不是另一套 CAD 工具箱，而是：

> AutoCAD 2024 内的多模型对话入口、标准 CADMCP 服务、安全任务 Agent 和可复用专业 Skill 容器。

第一阶段成功标准是“模型能连、图纸能读、任务能安全执行、成功流程能沉淀为待审核 Skill”，不是一次性交付建筑、车库、机械设计的全部算法。

## 2. 六项目标与当前状态

| 目标 | 第一版状态 | 当前边界 |
| --- | --- | --- |
| CAD 内连接多家大模型并问答 | 已实现代码入口 | 支持 OpenAI、Anthropic/Claude、DeepSeek、MiniMax、OpenAI Compatible、Ollama、企业内网接口；真实 Key 与网络仍需现场验证 |
| 公司/本地模型规范问答 | 最小可信链路已实现 | 支持授权 Markdown/TXT 目录、检索、来源编号和引用校验；PDF、OCR、向量库和文档权限分组留待下一版 |
| Codex、Claude 等 Agent 调 CAD | 已实现 MCP 基座 | Codex 项目配置和其他 Host 示例已具备；需在 AutoCAD 2024 中完成连续连接与真实写图验证 |
| 自有 Agent 执行计划 | 已有 Planner MVP | 支持计划、工具白名单、预览授权、执行事件、继续、重试、取消、回滚 |
| 成功计划转 Skill | 第一版已实现 | 只生成持久化待审核草稿；不能自动启用，不能引入白名单外工具 |
| 完整 CAD/工业/机械 MCP | 后续方向 | 当前只保留 13 个验证过的工具；按真实场景逐项扩展，不先做“大而全” |

## 3. 已落地的第一版

### 3.1 多模型与本地模型

- 插件标准模式可直接配置 provider、模型、API Base URL 和可选 API Key。
- Ollama 默认地址为 `http://127.0.0.1:11434/v1`，默认模型为 `qwen3:8b`。
- 企业内网和其他本地服务走 OpenAI Chat Completions 兼容协议；无鉴权内网接口允许 API Key 留空。
- Anthropic/Claude 使用 Messages 协议和可配置 Base URL。
- backend 同时支持 `openai_chat`、`openai_responses`、`anthropic_messages` 三种协议。

### 3.2 五层连接诊断

`GET /connector/diagnostics` 统一检查：

1. backend HTTP；
2. 模型网关与当前 provider；
3. CADMCP 工具和 Skill 注册；
4. AutoCAD 本地桥及 `2.0` 协议；
5. AutoCAD 2024 与当前活动图纸。

插件诊断面板显示五层摘要、原始诊断和恢复提示。`GET /connector/capabilities` 提供 Host 可读取的能力清单。

### 3.3 Agent 与 Skill 草稿

- Planner 只可使用当前 13 个 MCP 工具和 4 个内置 Skill。
- 写图仍遵守预览、用户授权、事务提交、Handle 校验和回滚。
- 已完成任务可调用 `POST /planner/tasks/{task_id}/skill-draft`。
- 用户也可通过 `POST /planner/skill-drafts` 创建草稿。
- 草稿保存在 `CADCOPILOT_SKILL_DRAFT_STORE_PATH`，默认是用户目录下 `.cadcopilot/skill-drafts.json`。
- 草稿必须审核后才能进入未来的发布流程；第一版刻意不提供自动启用。
- 草稿支持编辑、校验和人工批准；批准后仍保持 `enabled=false`，不能绕过 Planner 安全边界。

### 3.4 公司规范问答

- `CADCOPILOT_KNOWLEDGE_ROOTS` 只允许管理员指定本地资料根目录。
- 当前读取 UTF-8 Markdown/TXT，并返回相对来源、标题、版本、章节和原文片段。
- `POST /knowledge/query` 要求模型用 `[S1]` 引用；缺少或伪造来源编号时标记为未核验。
- 没有检索结果时不调用模型生成无来源答案。

## 4. 下一阶段验证节点

### V1：真实模型连接

- OpenAI Chat、Anthropic Messages、本地 Ollama、公司模型各完成 10 次标准问答。
- 验证无效 Key、无效模型、超时、限流、非 JSON 和服务重启。
- 公司模型回答规范时必须返回条文号、版本和来源；不能验证来源的回答标记为“仅供查询线索”。

### V2：外部 Agent 与 AutoCAD

- Codex 和第二种 Host 各连续完成 20 次初始化、工具发现和快照读取。
- 在 AutoCAD 2024 中验证预览、拒绝授权、确认写入和回滚。
- 未授权写入、白名单外工具和敏感配置泄漏都必须为 0。

### V3：任务转 Skill

- 选择 5 个真实完成任务生成草稿。
- 人工检查步骤是否可复现、参数是否应变量化、工具是否最小、失败条件是否明确。
- 下一版再增加草稿编辑、验收样例运行、签名和“审核后发布”；不允许模型直接发布。

## 5. 专业 Skill 的投入顺序

1. 先验证现有“外围轮廓”和“图层统一”在真实 DWG 上稳定。
2. 再做平面功能图 Skill：保留墙、门、窗、轴线图层，识别内外轮廓和功能区，最后着色表达。
3. 再做面积规则 Skill：规则版本化、面积线、分层统计、可追溯计算依据。
4. 车库自动排布最后进入：它同时涉及红线、柱网、车道、安全疏散、规范版本和优化求解，不能作为连接器 MVP 的验证功能。
5. 工业/机械能力按一个真实高频流程一个 Skill 扩展；先增加必要的只读工具，再增加可回滚写入工具。

## 6. 明确未完成项

- 未完成 PDF/OCR、向量检索、部门级文档权限隔离。
- 未完成 Skill 自动验收、签名、正式启用和共享市场。
- 未完成 Codex/第二 Host 的 20 次稳定性数据。
- 未完成真实 provider 批量连接数据。
- 未完成 AutoCAD 2024 真实 DWG 写图与回滚验收。

因此，下一轮应进入 V1、V2 的真实环境验证与硬化，而不是继续增加新的专业绘图工具。
