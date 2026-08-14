# AgentBridge 交接记录：Agent 循环与 Rhino 建模管线（2026-08-13）

> 目的：把本轮已验证的成果、关键经验、踩坑教训固化成文，供后续（包括其他智能体）
> 接手客户端开发 / 扩展软件桥接时直接使用。
> 配套文档：`gap-analysis-client-productization-2026-08-13.md`（客户端产品化差距分析）、
> `rhino-host-test-guide-2026-08-13.md`（Rhino 宿主测试指南）。

## 1. 一句话结论

**Agent 循环（读取数据 → 判断 → 建模 → 检查 → 修改 → 再检查）已在 Rhino 真机上跑通，
整层图纸（419 个构件）按此循环分 12 区建模，终审三项指标全过。** 脚本批量生成只作为
“读数据/初稿”工具，产品核心形态是 Agent 用工具循环驱动建模，用户明确否定了“脚本一把梭”。

## 2. 本轮核心成果

### 2.1 Rhino 宿主工具链（可被 Agent 调用的能力）

| 工具 | 作用 | 备注 |
| --- | --- | --- |
| `rhino_scene_summary` | 场景总览（对象数/图层/文档名） | 只读 |
| `rhino_get_objects` | 按 ID/图层/名称/包围盒列出对象，可按图层过滤 | 只读，Agent“看见”模型 |
| `rhino_create_box` | 建长方体，支持图层/图层色/命名，可回滚 | 写 |
| `rhino_delete_object` | 按对象 ID 删除 | 写，Agent 循环的“修改”步 |
| `rhino_union_layer` | 分批布尔合并图层实体 | 备用，不作为主修复手段 |
| `/rollback` | 按回滚令牌删除已建对象 | 令牌已唯一化 |

写工具统一要求 `permission_request_id`（与 Codex 审批策略联动）。

### 2.2 整层 DXF → Rhino 建模管线

- 输入：天正 T3 导出 DXF（`Tsetfile/一层平面图_t3门墙柱.dxf`）
- 输出：419 个构件 = 墙 337 + 柱 40 + 门 10 + 窗 32，全部带名字、分图层
- 分 12 个横向区域逐区建模，每区建完立即检查（净空侵入 / 交接缝隙），通过才进下一区
- 终审：净空侵入 0、交接缝隙 0、**数据一致性 0 处不匹配**
  （数据一致性 = 每个对象的实际位置与图纸数据期望位置逐名核对，容差 60mm）
- 图层：墙=灰、柱=红、门=橙、窗=蓝；门高 2.2m 落地，窗台 0.9m + 窗高 1.5m + 过梁

### 2.3 Agent 循环演示（真机验证通过）

脚本 `_demo_agent_loop.py`：清理场景 → 验证命名/删除 → 读图纸窗洞区域 → 逐个建模 →
检查（0 问题）→ 故意放入坏墙 → 检查抓到（按 ID）→ 删除 → 再检查归零。

## 3. 本轮发现并修复的关键问题（经验教训）

按重要性排序，每一条都是真实场景踩出来的：

### 3.1 对象命名在真机静默失效
- 现象：所有对象创建成功但 `Attributes.Name` 没写进去，Agent 无法按名定位。
- 原因：RhinoCommon 路径 `doc.Objects[oid].Attributes.Name = ...` 在 Rhino 8 静默失败。
- 修复：双路径写入——先 `doc.Objects.FindId(oid)` + `CommitChanges()`，
  失败再 `rs.ObjectName(oid, name)`。

### 3.2 缺“删除”能力，回滚令牌按名字碰撞
- 新增 `rhino_delete_object`（循环必备）。
- 回滚令牌从 `rhino-box-<name>` 改为 `rhino-box-<name>-<guid8>`，同名盒子不再互相覆盖。

### 3.3 “幽灵墙段”：洞口切割误用整条墙线的洞口
- 现象：同一面墙重复生成最多 15 次、出现跨真实断口的假墙（449 → 388 构件）。
- 原因：`split_runs` 把整条墙线上的所有洞口边界套用到该线每一段墙上，
  切割产生超出墙段自身长度的幻影跨度。
- 修复：只切与该墙段实际重叠的洞口（`ob < a or oa > b` 跳过），
  且 cursor 越过墙段末端即停止。

### 3.4 竖直墙洞口位置转置
- 现象：竖墙上的门窗/楣/台被放到 (pos, fixed) 而非 (fixed, pos)，跑到 x≈3.3km 远处。
- 修复：`_emit_opening` 按横/竖墙分别计算 lx/ly。

### 3.5 洞口挂接零容差漏门
- 现象：一个 700 宽的门因 0.039mm 尺寸差挂不上墙（墙端 3300335.6 vs 门心 3300685.561）。
- 修复：`ATTACH_TOL_MM = 100`，挂接与切割条件统一加容差。

### 3.6 主入口/南侧门画在 WINDOW 层
- 现象：北侧主入口与南侧对应门各由两个 1800mm 块组成（3.6m 墙缺口），
  但块在 `WINDOW` 层 → 被识别成窗（有窗台堵门、1.5m 高、窗图层）。
- 修复：项目级校正清单 `copilot_backend/scripts/project_corrections.json`，
  按位置（容差 300mm）覆盖 opening 类型。以后类似“层标错”只需加一行。

### 3.7 审计指标盲区
- 缝隙/净空侵入指标抓不到“位置错位”（如转置、错位对象）。
- 新增终审“数据一致性”核对：按名字比对实际 bbox 与图纸数据期望 bbox。

### 3.8 中文编码坑（工程环境，不是产品代码）
- PowerShell 管道向 Python 传中文会乱码（GBK/UTF-8 混用），带中文的脚本必须落成
  UTF-8 文件再执行；控制台打印中文会乱码，不影响数据本身。

## 4. 目录与命令速查

```text
copilot_backend/scripts/dxf_to_rhino_plan.py   # 管线（读数据+初稿）
copilot_backend/scripts/project_corrections.json  # 项目校正清单
adapters/rhino/backend.py                        # 宿主工具实现
adapters/rhino/background_host.py / host.py      # 宿主 HTTP 服务
copilot_backend/adapter_install/rhino.py         # 一键安装适配器
copilot_backend/tests/test_rhino_backend.py
copilot_backend/tests/test_dxf_to_rhino_plan.py
_build_floor_agent.py                            # 整层 Agent 建模控制器（12 区循环）
_demo_agent_loop.py                              # 小规模循环演示
_debug_*.py                                      # 一次性排查脚本（可留可删）
```

常用命令：
```powershell
# 安装/重装 Rhino 适配器（装到 %APPDATA%\McNeel\Rhinoceros\<ver>\scripts\）
python -c "import sys; sys.path.insert(0, r'H:\codex\AgentBridge\copilot_backend'); from adapter_install.rhino import install_rhino_adapter; print(install_rhino_adapter())"

# Rhino 内启动宿主（命令栏）
_-RunPythonScript "C:\Users\chang_k\AppData\Roaming\McNeel\Rhinoceros\8.0\scripts\AgentBridgeHost_startup.py"

# 整层 Agent 建模（需宿主在线）
python _build_floor_agent.py

# 测试
python -m pytest copilot_backend/tests -q
```

Python：`C:\Users\chang_k\AppData\Local\Programs\Python\Python311\python.exe`。

## 5. 已知问题与待办（交给后续接手）

1. **两个窗未挂接**（图纸数据问题）——**已关闭（2026-08-14 用户决策）**：取消人工核对，连接链路验证通过后改用新图纸测试。
   - `(40656530.8, 3303285.6)` w=700：窗洞两侧墙线只有 100mm 短段（100mm 厚隔墙片段），
     配对后中心线存在但挂接依赖容差，需人工确认是否真实窗。
   - `(40682180.8, 3292735.6)` w=1500：该位置图纸无墙线（最近墙 1.35m 外），疑似漏画。
2. **AutoCAD 桥接未做**（需兼容 2014–2024；本机实际为 2016）——**已纳入一键连接编排**，实机验证步骤见 `host-verification-matrix-2026-08-14.md` §5。
3. **客户端开发**（用户已安排其他智能体接手，见差距分析文档）——**已完成**：P0/P1 闭环 + 连接自愈 + 双壳收口，见 `p1-closedloop-2026-08-14.md`。
4. **交付记录**：已登记 `dxf-rhino-plan-1f`（2026-08-13）。
5. **Git 未提交**：已提交（`4236982` 及之后）；`_debug_*.py`、`_plan_view.png` 已加 `.gitignore`，不随版本库。

## 6. 给接手者的三条建议

1. **坚持 Agent 循环**：脚本只做“读数据/初稿”，建模、检查、修改必须走工具循环，
   每区检查通过才进下一区；速度不是目标，准确和逻辑闭环才是。
2. **用“数据一致性”兜底**：几何指标（缝隙/侵入）抓不到错位，终审必须做
   “对象位置 vs 图纸数据”的逐名核对。
3. **图纸问题走校正清单**：遇到“层标错/尺寸差”，优先在 `project_corrections.json`
   记录并覆盖，不要为单张图写死逻辑。
