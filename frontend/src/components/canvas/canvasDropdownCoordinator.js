/** 同一时刻只保留一个画布内嵌下拉打开，避免分镜表工具栏与镜头卡互相遮挡。 */
let activeClose = null

export function openCanvasDropdown(closeSelf) {
  if (activeClose && activeClose !== closeSelf) {
    activeClose()
  }
  activeClose = closeSelf
}

export function closeCanvasDropdown(closeSelf) {
  if (activeClose === closeSelf) activeClose = null
}

export function closeActiveCanvasDropdown() {
  if (activeClose) {
    activeClose()
    activeClose = null
  }
}
