// Lightweight mutable store for per-node plus-button Y tracking.
// Uses a plain object + pub/sub to avoid routing through React setNodes state.

export const plusState = {} // { [nodeId]: { y: number | null, isReturning: boolean } }

const listeners = new Set()
const leaveTimers = {} // { [nodeId]: rafId } — deferred return to avoid flicker

export function updatePlusState(nodeId, patch) {
  plusState[nodeId] = { ...(plusState[nodeId] || { y: null, isReturning: false }), ...patch }
  listeners.forEach((fn) => fn())
}

export function subscribePlusState(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

// Schedule a return-to-center after one RAF frame.
// Caller can cancel it within the same frame (e.g. mouseenter on the button).
export function schedulePlusReturn(nodeId) {
  cancelPlusReturn(nodeId)
  leaveTimers[nodeId] = requestAnimationFrame(() => {
    delete leaveTimers[nodeId]
    updatePlusState(nodeId, { y: null, isReturning: true })
  })
}

export function cancelPlusReturn(nodeId) {
  if (leaveTimers[nodeId]) {
    cancelAnimationFrame(leaveTimers[nodeId])
    delete leaveTimers[nodeId]
  }
}
