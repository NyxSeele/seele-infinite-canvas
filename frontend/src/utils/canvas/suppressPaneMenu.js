let suppressUntil = 0

/** 关闭卡片三点菜单后短时抑制画布双击/右键菜单，避免误触 */
export function markSuppressPaneMenu(ms = 400) {
  suppressUntil = Date.now() + ms
}

export function isPaneMenuSuppressed() {
  return Date.now() < suppressUntil
}
