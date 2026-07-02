import { useCallback, useEffect, useRef, useState } from "react"
import {
  restoreCanvasSnapshot,
  serializeCanvasSnapshot,
  snapshotKey,
} from "../../utils/canvas/canvasHistorySnapshot"

const MAX_HISTORY = 50

export function isCanvasShortcutTarget(target) {
  if (!target || !(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true
  if (target.isContentEditable) return true
  return Boolean(target.closest("[contenteditable='true']"))
}

export function useCanvasHistory({
  nodesRef,
  edgesRef,
  setNodes,
  setEdges,
  buildData,
  buildOutlineData,
  textRetryRef,
  zIndexCounterRef,
  readOnlyRef,
  projectId,
}) {
  const pastRef = useRef([])
  const futureRef = useRef([])
  const applyingRef = useRef(false)
  const dragCapturedRef = useRef(false)
  const [revision, setRevision] = useState(0)
  const bump = useCallback(() => setRevision((n) => n + 1), [])

  const resetHistory = useCallback(() => {
    pastRef.current = []
    futureRef.current = []
    dragCapturedRef.current = false
    bump()
  }, [bump])

  useEffect(() => {
    resetHistory()
  }, [projectId, resetHistory])

  const takeSnapshot = useCallback(() => {
    return serializeCanvasSnapshot(nodesRef.current, edgesRef.current)
  }, [nodesRef, edgesRef])

  const restoreCtx = useCallback(
    () => ({
      setNodes,
      setEdges,
      buildData,
      buildOutlineData,
      textRetryRef,
      zIndexCounterRef,
    }),
    [setNodes, setEdges, buildData, buildOutlineData, textRetryRef, zIndexCounterRef]
  )

  const pushHistory = useCallback(() => {
    if (applyingRef.current || readOnlyRef?.current) return
    const snap = takeSnapshot()
    const key = snapshotKey(snap)
    const last = pastRef.current[pastRef.current.length - 1]
    if (last && snapshotKey(last) === key) return
    pastRef.current.push(snap)
    if (pastRef.current.length > MAX_HISTORY) pastRef.current.shift()
    futureRef.current = []
    bump()
  }, [takeSnapshot, readOnlyRef, bump])

  const undo = useCallback(() => {
    if (readOnlyRef?.current || pastRef.current.length === 0) return false
    applyingRef.current = true
    try {
      const current = takeSnapshot()
      futureRef.current.push(current)
      const prev = pastRef.current.pop()
      restoreCanvasSnapshot(prev, restoreCtx())
      bump()
      return true
    } finally {
      applyingRef.current = false
    }
  }, [takeSnapshot, restoreCtx, readOnlyRef, bump])

  const redo = useCallback(() => {
    if (readOnlyRef?.current || futureRef.current.length === 0) return false
    applyingRef.current = true
    try {
      const current = takeSnapshot()
      pastRef.current.push(current)
      const next = futureRef.current.pop()
      restoreCanvasSnapshot(next, restoreCtx())
      bump()
      return true
    } finally {
      applyingRef.current = false
    }
  }, [takeSnapshot, restoreCtx, readOnlyRef, bump])

  const onNodeDragStart = useCallback(() => {
    if (readOnlyRef?.current) return
    if (!dragCapturedRef.current) {
      pushHistory()
      dragCapturedRef.current = true
    }
  }, [pushHistory, readOnlyRef])

  const onNodeDragStop = useCallback(() => {
    dragCapturedRef.current = false
  }, [])

  const wrapOnNodesChange = useCallback(
    (changes, apply) => {
      if (
        !applyingRef.current
        && !readOnlyRef?.current
        && changes.some((c) => c.type === "remove")
      ) {
        pushHistory()
      }
      apply(changes)
    },
    [pushHistory, readOnlyRef]
  )

  const wrapOnEdgesChange = useCallback(
    (changes, apply) => {
      if (
        !applyingRef.current
        && !readOnlyRef?.current
        && changes.some((c) => c.type === "remove")
      ) {
        pushHistory()
      }
      apply(changes)
    },
    [pushHistory, readOnlyRef]
  )

  const canUndo = pastRef.current.length > 0
  const canRedo = futureRef.current.length > 0

  return {
    pushHistory,
    undo,
    redo,
    resetHistory,
    onNodeDragStart,
    onNodeDragStop,
    wrapOnNodesChange,
    wrapOnEdgesChange,
    canUndo,
    canRedo,
    revision,
  }
}
