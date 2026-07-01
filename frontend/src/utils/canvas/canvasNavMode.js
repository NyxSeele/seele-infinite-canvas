/** 画布导航模式 */
export const CANVAS_NAV_MODES = {
  SCROLL_PAN: "scroll-pan",
  SCROLL_ZOOM: "scroll-zoom",
}

export const CANVAS_NAV_MODE_STORAGE_KEY = "canvas-nav-mode"

export const CANVAS_NAV_MODE_OPTIONS = [
  {
    id: CANVAS_NAV_MODES.SCROLL_PAN,
    label: "滚轮平移",
    badge: "TapNow",
    desc: "滚轮上下移动画布；中键或空格 + 拖拽平移",
  },
  {
    id: CANVAS_NAV_MODES.SCROLL_ZOOM,
    label: "滚轮缩放",
    badge: "经典",
    desc: "滚轮缩放画布；按住左键拖拽平移",
  },
]

export function getInitialCanvasNavMode() {
  try {
    const stored = localStorage.getItem(CANVAS_NAV_MODE_STORAGE_KEY)
    if (stored === CANVAS_NAV_MODES.SCROLL_PAN || stored === CANVAS_NAV_MODES.SCROLL_ZOOM) {
      return stored
    }
  } catch {
    /* ignore */
  }
  return CANVAS_NAV_MODES.SCROLL_PAN
}

/** React Flow 与当前导航模式对应的交互 props */
export function getCanvasNavFlowProps(mode) {
  if (mode === CANVAS_NAV_MODES.SCROLL_ZOOM) {
    return {
      panOnScroll: false,
      panOnScrollMode: "free",
      zoomOnScroll: true,
      panOnDrag: true,
      selectionOnDrag: false,
      panActivationKeyCode: null,
      zoomActivationKeyCode: null,
    }
  }

  return {
    panOnScroll: true,
    panOnScrollMode: "vertical",
    zoomOnScroll: false,
    panOnDrag: [1, 2],
    selectionOnDrag: true,
    panActivationKeyCode: "Space",
    zoomActivationKeyCode: "Control",
  }
}
