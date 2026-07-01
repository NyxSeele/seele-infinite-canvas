import { useCallback, useEffect } from "react"

export function preventCanvasScroll(e) {
  e.stopPropagation()
}

/**
 * 节点内滚轮：Ctrl+滚轮只阻止浏览器页面缩放，不拦截冒泡，交给 React Flow 缩放画布。
 * 普通滚轮在可滚动容器内时阻止冒泡，避免带动画布平移。
 */
export function handleNodeWheel(e) {
  if (e.ctrlKey) {
    e.preventDefault()
    return
  }
  const el = e.currentTarget
  if (!el || el.scrollHeight <= el.clientHeight) return
  const { scrollTop, scrollHeight, clientHeight } = el
  const up = e.deltaY < 0 && scrollTop > 0
  const down = e.deltaY > 0 && scrollTop + clientHeight < scrollHeight
  if (up || down) e.stopPropagation()
}

/** 挂在节点根元素：Ctrl+滚轮透传给画布缩放 */
export function useCanvasNodeWheel(ref) {
  useEffect(() => {
    const el = ref?.current
    if (!el) return undefined
    const handler = (e) => {
      if (e.ctrlKey) e.preventDefault()
    }
    el.addEventListener("wheel", handler, { passive: false })
    return () => el.removeEventListener("wheel", handler)
  }, [ref])
}

/** @deprecated 使用 useCanvasNodeWheel + handleNodeWheel */
export function useBlockCtrlWheel(ref) {
  useCanvasNodeWheel(ref)
}

export function useScrollableWheelIsolation() {
  const onMouseEnter = useCallback(() => {
    document.addEventListener("wheel", preventCanvasScroll, { passive: false })
  }, [])

  const onMouseLeave = useCallback(() => {
    document.removeEventListener("wheel", preventCanvasScroll)
  }, [])

  useEffect(
    () => () => document.removeEventListener("wheel", preventCanvasScroll),
    []
  )

  return { onMouseEnter, onMouseLeave }
}
