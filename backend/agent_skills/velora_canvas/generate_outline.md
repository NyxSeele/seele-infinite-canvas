# Skill: generate_outline

## 何时执行
- text-response 已完成，且 intent=screenplay。
- chat 模式不要执行本步。

## data
```json
{ "text_response_id": "text-response节点id" }
```

## 注意
- 必须走 pipeline_step；禁止 create_node 手写大纲。
