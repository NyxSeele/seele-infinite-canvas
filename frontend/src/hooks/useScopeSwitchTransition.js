import { useEffect, useRef, useState } from "react"

const EXIT_MS = 180
const ENTER_MS = 240

/**
 * 切换 key 时的出入场阶段（团队空间 / scope 等）
 */
export function useScopeSwitchTransition(switchKey, { exitMs = EXIT_MS, enterMs = ENTER_MS } = {}) {
  const normalizedKey = switchKey == null ? "" : String(switchKey)
  const [displayKey, setDisplayKey] = useState(normalizedKey)
  const [phase, setPhase] = useState("idle")
  const timerRef = useRef(null)

  const keyChanged = normalizedKey !== displayKey
  const visualPhase = keyChanged && phase === "idle" ? "exiting" : phase

  useEffect(() => {
    clearTimeout(timerRef.current)
    if (normalizedKey === displayKey) return undefined

    setPhase("exiting")
    timerRef.current = setTimeout(() => {
      setDisplayKey(normalizedKey)
      setPhase("entering")
      timerRef.current = setTimeout(() => {
        setPhase("idle")
      }, enterMs)
    }, exitMs)

    return () => clearTimeout(timerRef.current)
  }, [normalizedKey, displayKey, exitMs, enterMs])

  return { phase, displayKey, visualPhase }
}
