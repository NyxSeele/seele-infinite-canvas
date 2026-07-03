import { useEffect, useRef, useState } from "react"

export const MOTION_EXIT_MS = 180
export const MOTION_ENTER_MS = 240

/** 延迟卸载以播放关闭动效 */
export function useOverlayMount(open, duration = MOTION_EXIT_MS) {
  const [mounted, setMounted] = useState(open)
  const [closing, setClosing] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    clearTimeout(timerRef.current)
    if (open) {
      setMounted(true)
      setClosing(false)
    } else if (mounted) {
      setClosing(true)
      timerRef.current = setTimeout(() => {
        setMounted(false)
        setClosing(false)
      }, duration)
    }
    return () => clearTimeout(timerRef.current)
  }, [open, duration])

  return { mounted, closing }
}

/** @deprecated 使用 useOverlayMount */
export const useFlyoutMount = useOverlayMount

/**
 * 浮层 class 拼接 helper
 * @param {object} opts
 * @param {boolean} opts.mounted
 * @param {boolean} opts.closing
 * @param {boolean} opts.open
 * @param {string} [opts.base]
 * @param {string} [opts.openClass]
 * @param {string} [opts.closingClass]
 * @param {string} [opts.enterClass]
 * @param {string} [opts.exitClass]
 */
export function overlayClassNames({
  mounted,
  closing,
  open,
  base = "",
  openClass = "",
  closingClass = "",
  enterClass = "",
  exitClass = "",
}) {
  return [
    base,
    open && !closing && openClass,
    closing && closingClass,
    mounted && open && !closing && enterClass,
    closing && exitClass,
  ]
    .filter(Boolean)
    .join(" ")
}
