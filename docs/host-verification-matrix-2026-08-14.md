# AgentBridge 统一宿主验收矩阵（2026-08-14）

> 目的：CAD（AutoCAD）实机验证通过后，对 AutoCAD / Blender / SketchUp / Rhino 四个宿主
> 依次按同一套 8 步矩阵复验，把"一次配置、多次可用"的连接闭环和"dry-run → 预览 →
> 确认 → 回滚"的写安全闭环在**新链路**（异步任务 + 写确认卡 + 交付动作）上统一走一遍。
> 每个宿主验证结果登记在本文件末尾的登记表，失败样本沉淀为回归测试。

## 0. 前置条件

- 桌面端（AgentBridge.Desktop）已构建并运行，backend 在线。
- 目标软件已安装：AutoCAD 2016（本机实际版本）/ Blender / SketchUp 2025 / Rhino 8。
- 模型已在面板"设置"页配置并通过"真实连通测试"。
- 每次验证记录：宿主/版本、命令、输入、期望、实际、日志路径。

## 1. 统一 8 步矩阵

| # | 步骤 | 操作 | 通过标准 |
| --- | --- | --- | --- |
| 1 | 一键连接 | 软件配置页点"连接" | 六步编排全绿（检测→装适配器→拉桥→等注册→健康→持久化），状态=在线，auto_start 生效 |
| 2 | 自动探测 | 点"扫描本机软件" | 识别到该软件（版本 + 插件/适配器已装状态），首屏卡片出现"连接"按钮 |
| 3 | 只读工具 | 面板/Agent 下发只读命令 | 返回场景/图纸摘要，无写盘副作用 |
| 4 | dry-run 预览 | 写命令（annotate 模式） | 确认卡显示工具 + 参数 + dry-run 预览摘要，软件内**未**落盘 |
| 5 | 确认落盘 | 点"批准并继续" | 写操作提交（dry-run→票据→commit），软件内可见结果，任务完成 |
| 6 | 拒绝路径 | 另开写命令点"拒绝" | 不落盘；模型收到拒绝并给出合理解释/改道 |
| 7 | 回滚 | 交付卡片"回滚"选令牌 | 软件内对应对象/实体消失，回滚结果卡片提示宿主 |
| 8 | 交付闭环 | 完成任务看交付页 | 交付物出现，可打开 / 打开目录 / 预览 |

## 2. 各宿主重点（差异项）

| 宿主 | 工具面 | 写/回滚要点 | 现有指南 |
| --- | --- | --- | --- |
| AutoCAD（cadmcp） | 13 工具 | `arch_draw_outer_outline`/`arch_apply_layer_mapping` 走 AutoCAD 事务 + Handle 校验；回滚=事务回滚 | `connector-acceptance-guide-2026-07-24.md`、`real-dwg-validation-matrix-2026-07-18.md` |
| Blender | 6 工具 | 建模/渲染 + `rollback_token`；写=box/primitive | `blender-host-test-guide-2026-08-12.md` |
| SketchUp | 2 工具 | 扩展安装 + 主机契约；需重启 SketchUp 后自动注册 | — |
| Rhino | 6 工具 | `rhino_create_box`/`rhino_delete_object`；`/rollback` 按令牌删除 | `rhino-host-test-guide-2026-08-13.md` |

## 3. 验收登记表

| 宿主 | 版本 | 步骤 1-8 | 结论 | 日期 | 备注/失败样本 |
| --- | --- | --- | --- | --- | --- |
| AutoCAD | 2016 | 待验证 | — | — | 本轮未实机验证，前置条件 |
| Blender | — | 待复验 | — | — | 新链路复验 |
| SketchUp | 2025 | 待复验 | — | — | 新链路复验 |
| Rhino | 8.0 | 待复验 | — | — | 新链路复验 |

## 4. 判定与沉淀

- 单个宿主 8 步全绿 = 通过；任一步失败记录明确错误类别 + 恢复建议，修复后从失败步重跑。
- 失败样本（宿主、工具、输入、期望、实际、日志）固化为 `copilot_backend/tests` 回归用例。
- 全部宿主通过后，本轮"陌生人 10 分钟闭环"的连接与写安全链路视为在新链路上验收完毕。

## 5. AutoCAD 首次实机验证（本机 2016）具体步骤

AutoCAD 是唯一从未实机验证过的宿主，先跑它：

```powershell
# 1. 打包插件（本机是 2016，必须显式指定版本）
.\scripts\build-plugin-package.ps1 -AutoCADVersion 2016

# 2. 安装插件（解压产物后运行；或仓库根 install.ps1）
.\Install-AgentBridge.ps1

# 3. 重启 AutoCAD 2016，命令行执行
TESTCOPILOT        # 期望：插件与本地 MCP 桥已加载，不修改图纸
AISNAPSHOT         # 期望：%TEMP%\AgentBridge\snapshots\ 出现当前图纸快照

# 4. 启动 cadmcp（面板"连接"也会自动拉起，可跳过）
.\scripts\start-cadmcp.ps1
```

之后打开面板（桌面端或 `http://127.0.0.1:8000/ui`）→ 软件配置 → AutoCAD"连接"，
然后按第 1 节 8 步矩阵走 13 工具，重点验证：

- 只读：`cad_health_check` / `get_drawing_snapshot` / `list_layers` / `arch_get_drawing_context` / `arch_recognize_functional_objects`
- 写（annotate）：`arch_extract_outer_outline` → `arch_draw_outer_outline`（确认卡 dry-run 预览 → 批准落盘 → 图纸可见闭合多段线）
- 写（annotate）：`arch_apply_layer_mapping`（预览迁移建议 → 批准 → 图层已迁移 → 回滚恢复）
- 拒绝路径：拒绝后图纸无变化，模型收到拒绝

## 6. 交接遗留：两个窗的人工核对

人工图纸已到位，按下面两个位置核对（坐标即图纸世界坐标），把结论填到"人工核对结论"列：

| # | 洞口位置 | 宽 | 管线现状 | 要核对的问题 | 人工核对结论 |
| --- | --- | --- | --- | --- | --- |
| 1 | (40656530.8, 3303285.6) | 700 | 两侧墙线只有 100mm 短段，挂接依赖容差 | 该处是否真实窗户？两侧 100mm 短段是否为墙？ | 待填 |
| 2 | (40682180.8, 3292735.6) | 1500 | 该处图纸无墙线（最近墙 1.35m 外） | 该处是否应有墙？是否为图纸漏画？ | 待填 |

核对结论二选一：

- **窗 1**：真实窗 → 在 `copilot_backend/scripts/project_corrections.json` 加校正项并调挂接容差后重跑管线；
  不是窗 → 从数据中剔除该洞口。
- **窗 2**：图纸漏画 → 补图后重导出 T3 DXF，或加校正项；无此窗 → 剔除。

两个窗结论落定后重跑 `_build_floor_agent.py` 验证全部窗/门挂接归零，交接遗留即关闭。
