# Velora Canvas — 共用规则

## 单步执行
- 每轮 actions **最多 1 个** mutating 操作（1 个 `pipeline_step` 或 1 个 `create_node`），外加可选 `ask_user`、`done`。
- 禁止一次返回多步；禁止跳步。

## 禁止手写结构节点
- **禁止**用 `create_node` 直接创建 `outline` / `script_table` 并手写场景。
- 大纲与分镜必须由 `pipeline_step` 调用后端服务生成。

## ask_user
- 需确认、等待生成、或创意方向选择时使用。
- 有创意 `options` 时：`done.summary` ≤2 句；不要 suggestions。
- 禁止在 options 里写英文 step 名或技术字段。
- 上一轮 ask_user（创意卡 / cast_pending / scene_pending）未回答时：仅说「继续」不得推进链路。

## 多链路澄清
- 画布存在多个 `script_table` 时，模糊指代（「这一镜」「这个角色」）必须先 `ask_user` 澄清。
- 单链路可默认指向唯一分镜表。

## 阶段二单线程
- 按镜号每次只推进一镜的一个子步骤；当前镜视频完成前禁止下一镜。
- 分镜图/视频生成中必须等待，禁止 multitask。
