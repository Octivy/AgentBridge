# AgentBridge 桥接技能（DeepSeek Harness 版）

你通过三个 MCP 服务器驱动本机 CAD/建模软件。智能决策由你做，几何执行由软件做，
AgentBridge 只负责连接、解释、权限票据与回滚。

## 工具命名

- `mcp__hostmcp__<软件>_<工具>`：直接读写软件（22 个工具）。
- `mcp__cadmcp__<工具>`：AutoCAD 制图工具（13 个）。
- `mcp__agentbridge__ab_<工具>`：控制平面 + 解释层（17 个）。

## 铁律

1. 永远先**读现状**，再**解释**，最后**写**。不要盲操作。
2. 写操作：先 `dry_run=true` 预览拿 `permission_token` + `preview_hash`，再以相同票据提交。
   票据一次性、会过期。`destructive_write` 需 `confirmed_by_local_user=true`。
3. 成功回读 `rollback_token`，出错用它回滚；新几何放独立图层（如 `AB-Plan-Walls`）便于整层回滚。

## 工具速查

| 软件 | 读 | 写 |
|---|---|---|
| AutoCAD | `mcp__hostmcp__autocad_get_drawing_snapshot` | `mcp__hostmcp__autocad_draw_line` 等 |
| Rhino | `mcp__hostmcp__rhino_scene_summary` / `rhino_get_objects` | `rhino_create_box`、`rhino_delete_object`、`rhino_union_layer` |
| SketchUp | `mcp__hostmcp__sketchup_scene_summary` | `sketchup_create_box` |
| Blender | `mcp__hostmcp__blender_scene_summary` | `blender_create_cube`、`blender_create_primitive` |
| 控制平面 | `mcp__agentbridge__ab_list_software`、`ab_software_status`、`ab_explain_drawing` | `ab_test_connection`、`ab_start_host`、`ab_stop_host` |

## 图纸 → 3D 墙体工作流

1. `autocad_get_drawing_snapshot` 读当前 DWG；
2. `ab_explain_drawing(host_kind="autocad")` 拿语义（墙/门窗统计、图层角色、房间标注）；
3. 墙体：WALL 层及名称含「墙」的图层，双线合并为中心线，**墙厚 = 双线实际间距**；
4. 门窗洞口：WINDOW 层线（线长=窗宽）、DOOR_FIRE 层块（比例=门宽、旋转=门扇方向）在墙上开洞；
5. 按段 `rhino_create_box`（dry-run→提交，层高默认 3.0m），最后 `rhino_union_layer` 合并。

## 坐标与单位

- CAD 图纸通常是**毫米**（天正坐标可达 4000 万 mm），建模软件常用米。
- 换算 `米 = 毫米 / 1000`，并平移到原点附近（减 `bounds.min`）。

## 图层语义

WALL/墙=墙体，COLUMN=柱，WINDOW=窗，DOOR=门，STAIR=楼梯，DIM=标注，DOTE=轴网，PUB_TEXT=房间名。
`ab_explain_drawing` 会输出每层角色解释，优先信任它。

## 安全

- 不删用户原有实体，除非明确要求并获确认；
- 连接失败先 `ab_list_software` 看状态，不要反复重试（守护会自愈）。
