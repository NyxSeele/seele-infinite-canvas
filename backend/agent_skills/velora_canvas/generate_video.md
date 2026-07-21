# Skill: generate_video

## 何时执行
- 该镜分镜图已完成，且尚无**已完成**的视频（has_video=false）。
- 当前镜视频完成前禁止进入下一镜出图。

## data
```json
{
  "script_table_id": "script_table节点id",
  "row_id": "镜头行id"
}
```
- 勿用 create_node(video) 替代分镜表镜头视频。
