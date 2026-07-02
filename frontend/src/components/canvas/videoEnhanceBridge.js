/** 视频节点画质增强 API 桥（VideoGenerationNode 注册，PromptBar 读取） */
const bridges = new Map()
const listeners = new Set()

export function setVideoEnhanceBridge(nodeId, bridgeRef) {
  if (bridgeRef) bridges.set(nodeId, bridgeRef)
  else bridges.delete(nodeId)
  notifyVideoEnhanceBridge()
}

export function getVideoEnhanceBridge(nodeId) {
  const ref = bridges.get(nodeId)
  return ref?.current ?? null
}

export function notifyVideoEnhanceBridge() {
  listeners.forEach((fn) => fn())
}

export function subscribeVideoEnhanceBridge(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
