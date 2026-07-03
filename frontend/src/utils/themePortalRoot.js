/** Portal 挂载点：保留主题 CSS 变量作用域 */
export function getThemePortalRoot() {
  return (
    document.querySelector(".rf-page") ||
    document.querySelector(".ws-page") ||
    document.body
  )
}

export function getThemePageClass() {
  if (document.querySelector(".rf-page--dark, .ws-page.rf-page--dark")) {
    return "rf-page--dark"
  }
  return "rf-page--light"
}
