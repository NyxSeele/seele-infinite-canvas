/** 判断节点 patch 是否会改变 data（忽略 undefined 字段） */
export function isNodePatchNoop(data, patch) {
  if (!patch || typeof patch !== "object") return true
  return Object.entries(patch).every(([key, value]) => {
    if (value === undefined) return true
    return data?.[key] === value
  })
}
