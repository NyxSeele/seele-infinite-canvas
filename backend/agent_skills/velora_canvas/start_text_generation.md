# Skill: start_text_generation

## 何时执行
- 已有 text-note，尚无 text-response，或需要重新生成剧本文本。
- 普通闲聊 `intent=chat`：只需 create_text_note + 本步，不要再 generate_outline。

## data
```json
{ "source_id": "text-note节点id" }
```
- `source_id` 必须来自画布 nodes，禁止编造。
