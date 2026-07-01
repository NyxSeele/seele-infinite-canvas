import { useCallback } from "react"
import { flushSync } from "react-dom"
import { useCanvasStore } from "../stores"

const TRANSITION_MS = 250

function prefersReducedMotion() {
  if (typeof window === "undefined") return false
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

function supportsViewTransitions() {
  return typeof document !== "undefined" && typeof document.startViewTransition === "function"
}

function resolveOrigin(clickEvent) {
  if (clickEvent && Number.isFinite(clickEvent.clientX) && Number.isFinite(clickEvent.clientY)) {
    return { x: clickEvent.clientX, y: clickEvent.clientY }
  }
  return {
    x: window.innerWidth / 2,
    y: window.innerHeight / 2,
  }
}

function runCircularReveal(x, y) {
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y),
  )
  document.documentElement.animate(
    {
      clipPath: [
        `circle(0px at ${x}px ${y}px)`,
        `circle(${endRadius}px at ${x}px ${y}px)`,
      ],
    },
    {
      duration: TRANSITION_MS,
      easing: "ease-in-out",
      pseudoElement: "::view-transition-new(root)",
    },
  )
}

/**
 * 主题切换圆形扩散（View Transitions API），与 scope 切换动画独立。
 */
export function useThemeTransition() {
  const toggleTheme = useCanvasStore((s) => s.toggleTheme)

  const applyThemeChange = useCallback(() => {
    toggleTheme()
  }, [toggleTheme])

  const toggleThemeWithTransition = useCallback(
    (clickEvent) => {
      if (!supportsViewTransitions() || prefersReducedMotion()) {
        applyThemeChange()
        return
      }

      const { x, y } = resolveOrigin(clickEvent)
      const transition = document.startViewTransition(() => {
        flushSync(() => {
          applyThemeChange()
        })
      })

      transition.ready
        .then(() => {
          runCircularReveal(x, y)
        })
        .catch(() => {})

      transition.finished.catch(() => {})
    },
    [applyThemeChange],
  )

  return {
    toggleThemeWithTransition,
    supportsThemeTransition: supportsViewTransitions() && !prefersReducedMotion(),
  }
}
