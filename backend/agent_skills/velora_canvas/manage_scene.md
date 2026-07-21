# Skill: manage_scene

## 何时执行
- 用户说「添加场景」「教室/办公室/外景」「多镜同一场景」「完善场景库」等。
- 须在分镜表已存在时。

## 规则
- 读取 nodes 中 `scene_library`：已有场景名称时**禁止重复添加**同名条目。
- 场景与角色**分开管理**：不要用 manage_cast 添加场景，不要用 manage_scene 添加角色。
- 可附带 `row_assignments` 把场景绑定到镜头（写入 `location_id` / `locationId`）；优先用行级 location 绑定而非仅在文本里写场景名。
- 本步后若仍有待配图场景，可在同一轮末尾 ask_user，`scene_pending` 列出待配图场景名。

## data
```json
{
  "script_table_id": "分镜表节点id",
  "scene_items": [
    {"action": "add|update", "name": "场景名", "description": "可选描述", "image_url": "可选参考图"}
  ],
  "row_assignments": [
    {"row_id": "镜头行id", "scene_name": "场景名", "location_id": "场景库条目id"}
  ]
}
```
