# Skill: create_text_note

## 何时执行
- 画布无本主题的 text-note；或用户已选定创意方案后开启新链路。
- 开新链路必须**新建**节点，禁止复用旧链路 id。
- 用户首次提出全新主题、尚未选定方向时：**不要**直接本步，先走创意 ask_user。

## data
```json
{
  "prompt": "用户完整意图（必填，禁止为空）",
  "intent": "screenplay",
  "label": "宣传片策划"
}
```
- `intent=screenplay`：剧本/宣传片主链；`intent=chat`：普通问答（走完文本生成即结束）。
