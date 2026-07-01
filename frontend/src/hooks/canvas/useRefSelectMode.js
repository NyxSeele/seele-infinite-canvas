import { useCallback, useState } from "react"

export function useRefSelectMode(setSelectedNodeId) {
  const [refSelectMode, setRefSelectMode] = useState({
    active: false,
    sourceNodeId: null,
    pickTarget: "referenceImage",
    pickMeta: null,
    hoverRef: null,
    selectedRef: null,
  })

  const resetReferencePickerState = useCallback(() => {
    setRefSelectMode((m) => ({
      ...m,
      hoverRef: null,
      selectedRef: null,
    }))
  }, [])

  const exitRefSelectMode = useCallback(() => {
    setRefSelectMode({
      active: false,
      sourceNodeId: null,
      pickTarget: "referenceImage",
      pickMeta: null,
      hoverRef: null,
      selectedRef: null,
    })
  }, [])

  const enterRefSelectMode = useCallback((sourceNodeId, pickTarget = "referenceImage", pickMeta = null) => {
    setRefSelectMode({
      active: true,
      sourceNodeId,
      pickTarget,
      pickMeta: pickMeta || null,
      hoverRef: null,
      selectedRef: null,
    })
    setSelectedNodeId(null)
  }, [setSelectedNodeId])

  const setRefSelectHover = useCallback((hoverRef) => {
    setRefSelectMode((m) =>
      m.active ? { ...m, hoverRef: hoverRef || null } : m
    )
  }, [])

  const setRefSelectSelected = useCallback((selectedRef) => {
    setRefSelectMode((m) =>
      m.active ? { ...m, selectedRef: selectedRef || null } : m
    )
  }, [])

  const setRefSelectHighlight = useCallback((highlightRef) => {
    setRefSelectMode((m) =>
      m.active ? { ...m, hoverRef: highlightRef || null } : m
    )
  }, [])

  return {
    refSelectMode,
    exitRefSelectMode,
    enterRefSelectMode,
    setRefSelectHover,
    setRefSelectSelected,
    setRefSelectHighlight,
    resetReferencePickerState,
  }
}
