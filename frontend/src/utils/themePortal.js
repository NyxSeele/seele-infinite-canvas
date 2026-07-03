import { createPortal } from "react-dom"
import { getThemePageClass, getThemePortalRoot } from "./themePortalRoot"

/**
 * 合并 theme page class 到已有 className
 */
export function mergeThemeClassName(className = "") {
  const theme = getThemePageClass()
  if (!className) return theme
  if (className.includes(theme)) return className
  return `${className} ${theme}`.trim()
}

/**
 * Portal 到主题容器，保留 CSS 变量作用域
 */
export function renderThemePortal(node, container) {
  return createPortal(node, container ?? getThemePortalRoot())
}
