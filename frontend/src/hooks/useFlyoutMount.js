import { useEffect, useRef, useState } from "react"

/** 延迟卸载以播放关闭动效 */
export function useFlyoutMount(open, duration = 220) {
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
