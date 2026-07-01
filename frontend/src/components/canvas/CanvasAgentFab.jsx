import { useCallback, useEffect, useRef } from "react"
import "./CanvasAgentFab.css"

const ANCHOR_RIGHT = 20
const ANCHOR_BOTTOM = 24

export default function CanvasAgentFab({ open, onToggle, disabled }) {
  const fabRef = useRef(null)

  useEffect(() => {
    const onResize = () => {
      /* 固定锚点由 CSS right/bottom 控制，resize 无需额外计算 */
    }
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  const onClick = useCallback(
    (e) => {
      e.preventDefault()
      if (!disabled) onToggle?.()
    },
    [disabled, onToggle]
  )

  if (disabled || open) return null

  return (
    <button
      ref={fabRef}
      type="button"
      className="canvas-agent-fab"
      style={{ right: ANCHOR_RIGHT, bottom: ANCHOR_BOTTOM }}
      onClick={onClick}
      aria-label="打开 AI 助手"
    >
      <img
        className="canvas-agent-fab__icon"
        src="/assets/ai-assistant-icon.png"
        alt=""
        draggable={false}
      />
    </button>
  )
}
