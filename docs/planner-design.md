# Planner 设计

Planner 将自然语言目标转换为受产品白名单约束的 MCP 工具调用。`available_tools` 与 `available_skills` 是唯一能力来源，不允许模型调用未注册的类天正工具。

## 流程

1. 读取任务与当前图纸上下文。
2. 从四个 Skill 中选择最小匹配能力。
3. 对读取工具直接执行并记录事件。
4. 对写工具强制 dry-run，返回预览和一次性授权票据。
5. 用户确认后复用原参数提交，不重新规划几何。
6. 记录工具结果、事务、Handle、回滚 token 与任务状态。

## 状态

任务状态包括 `created`、`running`、`waiting_user`、`completed`、`failed`、`cancelled`。缺少范围、目标或关键约束时进入 `waiting_user`；工具失败不得伪装成完成。

## 安全边界

- 工具名必须存在于 `cadmcp/tool_registry.py`。
- Skill 必须存在于 `copilot_backend/skills/registry.py`。
- 写操作必须先预览；一次性票据绑定工具名与业务参数。
- 提交后由本地 AutoCAD 桥校验，Planner 不能自行声明写入成功。

产品范围见 [产品定义](product-prd-v5-semantic-conversion.md)，执行节点见 [工作计划](work-plan.md)。
