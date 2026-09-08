---
name: agentbridge
description: 通过 AgentBridge 连接并驱动本机 CAD/建模软件（AutoCAD/Rhino/SketchUp/Blender）。当用户需要读取图纸/场景、在建模软件中创建或修改几何、或做图纸到模型的联动（如平面图→3D 墙体）时使用本技能。包含工具协议、权限流程、图层语义与坐标单位约定。
---

# AgentBridge 桥接技能

## 角色与边界

- **智能决策归你（Agent）**：理解图纸、规划步骤、决定画什么，都由你做。
- **执行归软件**：所有几何操作由软件自身的插件完成（AutoCAD 用 .NET 事务、Rhino/SketchUp/Blender 用各自脚本 API）。
- **AgentBridge 只做中间调和方**：连接、解释、权限票据与回滚。
- 永远先**读现状**，再**解释**（`ab_explain_drawing`），最后**写**。不要凭想象盲操作。

## 接入方式

1. **MCP（Codex/Claude 等支持 MCP 的客户端）**：配置 3 个服务器——
   - `hostmcp`（22 个工具）：`<软件>_<工具>` 命名空间，直接驱动软件；
   - `cadmcp`（13 个工具）：AutoCAD 制图工具；
   - `agentbridge`（17 个工具）：`ab_*` 控制平面 + 解释层（`ab_explain_drawing`）。
2. **HTTP（DSH 等无 MCP 界面的客户端）**：直接调后端 `http://127.0.0.1:8000`——
   - `GET /hosts`（宿主与工具清单）、`GET /config/explain/drawing?host_kind=autocad`（解释图纸）、
     `POST /config/hosts/{id}/connect`（一键连接）、`GET /config/agent/test`（接入自检）。

## 写操作协议（必须遵守）

1. `dry_run=true` 先预览，拿到 `permission_token` + `preview_hash`；
2. 再以 `dry_run=false` + 同一 `permission_token`/`preview_hash` 提交（票据一次性、会过期）；
3. `reversible_write` 自动授权；`destructive_write` 需要用户确认（`confirmed_by_local_user=true`）；
4. 提交成功回读 `rollback_token`，出问题用它回滚。

## 工具速查（hostmcp 命名空间）

| 软件 | 读 | 写 |
|---|---|---|
| AutoCAD | `autocad_get_drawing_snapshot`（实体/图层/块/文字全量） | `autocad_draw_line` 等 |
| Rhino | `rhino_scene_summary` / `rhino_get_objects` | `rhino_create_box`、`rhino_delete_object`、`rhino_union_layer`（布尔并集） |
| SketchUp | `sketchup_scene_summary` | `sketchup_create_box` |
| Blender | `blender_scene_summary` | `blender_create_cube`、`blender_create_primitive` |

## 图纸 → 3D 墙体的参考工作流

1. `autocad_get_drawing_snapshot` 读当前 DWG；
2. `ab_explain_drawing(host_kind="autocad")` 拿语义解释（墙/门窗统计、图层角色、房间标注）；
3. 墙体：WALL 层（及名称含「墙」的图层）双线合并为中心线，**墙厚 = 双线实际间距**（不要用固定值）；
4. 门窗洞口：WINDOW 层线（线长=窗宽）与 DOOR_FIRE 层块（比例=门宽、旋转=门扇方向）在墙体上开洞；
5. 按段 `rhino_create_box`（dry-run→提交，层高默认 3.0m），最后 `rhino_union_layer` 合并；
6. 全程记录 `rollback_token`，完成后告诉用户如何回滚。

## 坐标与单位约定

- CAD 图纸通常是**毫米**（天正图纸坐标可达 4000 万 mm 量级）；建模软件常用米。
- 换算：`米 = 毫米 / 1000`；并平移到原点附近（减去图纸 `bounds.min`），避免远原点精度问题。
- 生成几何前先确认目标软件的单位系统。

## 图层语义（天正/常规图纸）

WALL/墙=墙体，COLUMN=柱，WINDOW=窗，DOOR=门，STAIR=楼梯，DIM=标注，DOTE=轴网，
PUB_TEXT/文字=房间名与说明。`ab_explain_drawing` 会输出每层的角色解释，优先信任它。

## 安全边界

- 不删除用户原有实体，除非用户明确要求且拿到确认；
- 新几何统一放独立图层（如 `AB-Plan-Walls`），便于整层回滚；
- 连接失败先看 `GET /config/connection/events` 与面板指引，不要反复重试（守护会自愈）。
