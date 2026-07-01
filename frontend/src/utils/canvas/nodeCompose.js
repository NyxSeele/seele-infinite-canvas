/** 从持久化/误注入数据里剥离不属于 outline 的字段 */
export function pickOutlineNodeFields(extra = {}) {
  const {
    sourceNodeId: _s,
    linkedSourceId: _l,
    linkedSourceType: _lt,
    linkedSourceData: _ld,
    prompt: _p,
    content: _c,
    composeNodeData: _cn,
    composeOutlineNodeData: _co,
    connectOutlineFromResponse: _ce,
    onStopGeneration: _os,
    onRetry: _or,
    status: _st,
    taskId: _t,
    model: _m,
    mentions: _me,
    onUpdate: _ou,
    onDelete: _od,
    onGenerateScreenplay: _og,
    onImportScriptTable: _oi,
    onMigrateShotScript: _om,
    onGenerateScriptTable: _ogt,
    ...rest
  } = extra
  return rest
}

export function outlineSafePatch(patch) {
  const {
    sourceNodeId: _s,
    linkedSourceId: _l,
    linkedSourceType: _lt,
    linkedSourceData: _ld,
    prompt: _p,
    content: _c,
    ...safe
  } = patch
  return safe
}
