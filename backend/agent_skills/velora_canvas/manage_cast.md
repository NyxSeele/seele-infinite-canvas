# Skill: manage_cast

## 何时执行
- 用户说「添加角色」「加个人物」「更新某某设定」「完善角色库」等。
- 须在分镜表已存在时；否则先推进到 generate_script_table。

## 规则
- 读取 nodes 中 `cast_library`：已有人物名称时**禁止重复添加**同名条目。
- cast_items **仅添加角色**（type 固定 character），不要把场景写进 cast_library。
- 每个角色必须带 **identity_id**（格式 `{角色名拼音或英文slug}_default`，如 `alice_default`）；禁止只写裸名无 identity。
- 可选 slot 图：`face_url` / `three_view_url` / `costume_url`（至少一张参考图，否则标记 pending）。
- 本步后若仍有 `pending_image: true` 的角色，可在同一轮末尾追加 ask_user（须在 manage_cast **之后**）：
  - `cast_pending` 列出待配图角色名与 identity_id
  - options 含「现在配图」「先跳过，继续生成」

## data
```json
{
  "script_table_id": "分镜表节点id",
  "cast_items": [
    {
      "action": "add|update",
      "name": "角色名",
      "type": "character",
      "identity_id": "alice_default",
      "description": "可选描述",
      "face_url": "可选正脸图URL",
      "three_view_url": "可选三视图URL"
    }
  ]
}
```
