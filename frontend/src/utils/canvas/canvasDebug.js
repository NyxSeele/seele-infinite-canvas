/** 画布热路径调试日志：仅在 DEV 且 window.__CANVAS_DEBUG__ 时输出 */
export function isCanvasDebugEnabled() {
  return import.meta.env.DEV
    && typeof window !== "undefined"
    && Boolean(window.__CANVAS_DEBUG__)
}
