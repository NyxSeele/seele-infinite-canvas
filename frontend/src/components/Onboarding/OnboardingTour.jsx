import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { ONBOARDING_RESTART_EVENT } from "./tourSteps"
import "./onboarding.css"

const SPOTLIGHT_PADDING = 8
const TOOLTIP_GAP = 12
const TOOLTIP_EST_HEIGHT = 160
const VIEWPORT_MARGIN = 12
const PANEL_OPEN_WAIT_MS = 300

const PANEL_SELECTORS = new Set([".agent-panel", ".clt-add-menu"])

function waitForPanelOpen() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setTimeout(resolve, PANEL_OPEN_WAIT_MS)
      })
    })
  })
}

function getStorageKey(tourId, storageKey) {
  return storageKey || `onboarding_${tourId}_done`
}

function measureTarget(selector) {
  const el = document.querySelector(selector)
  if (!el) return null
  const rect = el.getBoundingClientRect()
  if (rect.width === 0 && rect.height === 0) return null
  return {
    top: rect.top - SPOTLIGHT_PADDING,
    left: rect.left - SPOTLIGHT_PADDING,
    width: rect.width + SPOTLIGHT_PADDING * 2,
    height: rect.height + SPOTLIGHT_PADDING * 2,
  }
}

function waitMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function measureTargetWithRetry(selector, maxAttempts = 10, intervalMs = 300) {
  for (let i = 0; i < maxAttempts; i += 1) {
    const measured = measureTarget(selector)
    if (measured) return measured
    if (i < maxAttempts - 1) await waitMs(intervalMs)
  }
  return null
}

function computePlacement(rect) {
  const spaceBelow = window.innerHeight - (rect.top + rect.height + TOOLTIP_GAP)
  const spaceAbove = rect.top - TOOLTIP_GAP
  if (spaceBelow >= TOOLTIP_EST_HEIGHT || spaceBelow >= spaceAbove) {
    return "bottom"
  }
  return "top"
}

function computeTooltipPosition(rect, placement) {
  const tooltipWidth = Math.min(320, window.innerWidth - VIEWPORT_MARGIN * 2)
  let top
  if (placement === "bottom") {
    top = rect.top + rect.height + TOOLTIP_GAP
  } else {
    top = rect.top - TOOLTIP_GAP - TOOLTIP_EST_HEIGHT
  }
  top = Math.max(VIEWPORT_MARGIN, Math.min(top, window.innerHeight - TOOLTIP_EST_HEIGHT - VIEWPORT_MARGIN))

  let left = rect.left + rect.width / 2 - tooltipWidth / 2
  left = Math.max(VIEWPORT_MARGIN, Math.min(left, window.innerWidth - tooltipWidth - VIEWPORT_MARGIN))

  return { top, left, width: tooltipWidth }
}

export default function OnboardingTour({
  tourId,
  steps,
  startDelayMs = 0,
  storageKey: storageKeyProp,
}) {
  const storageKey = getStorageKey(tourId, storageKeyProp)
  const [active, setActive] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [rect, setRect] = useState(null)
  const [placement, setPlacement] = useState("bottom")
  const [tooltipPos, setTooltipPos] = useState(null)
  const stepIndexRef = useRef(0)
  const activeRef = useRef(false)
  const autoStartTimerRef = useRef(null)
  const startRef = useRef(null)

  stepIndexRef.current = stepIndex
  activeRef.current = active

  const finish = useCallback(() => {
    try {
      localStorage.setItem(storageKey, "1")
    } catch {
      /* ignore */
    }
    setActive(false)
    setRect(null)
    setTooltipPos(null)
  }, [storageKey])

  const applyStep = useCallback(async (index) => {
    if (index >= steps.length) {
      finish()
      return
    }

    const step = steps[index]
    try {
      await step.beforeShow?.()
    } catch (err) {
      console.warn("[OnboardingTour] beforeShow failed:", err)
    }

    if (PANEL_SELECTORS.has(step.selector)) {
      await waitForPanelOpen()
    }

    const measured = await measureTargetWithRetry(step.selector)
    if (!measured) {
      console.warn(`[OnboardingTour] selector not found: ${step.selector}, skipping`)
      const next = index + 1
      if (next >= steps.length) {
        finish()
      } else {
        setStepIndex(next)
        applyStep(next)
      }
      return
    }

    const place = computePlacement(measured)
    setRect(measured)
    setPlacement(place)
    setTooltipPos(computeTooltipPosition(measured, place))
    setStepIndex(index)
  }, [steps, finish])

  const start = useCallback(() => {
    setActive(true)
    setStepIndex(0)
    applyStep(0)
  }, [applyStep])

  startRef.current = start

  const goNext = useCallback(() => {
    const next = stepIndexRef.current + 1
    if (next >= steps.length) {
      finish()
    } else {
      applyStep(next)
    }
  }, [steps.length, applyStep, finish])

  const refreshPosition = useCallback(() => {
    if (!activeRef.current) return
    const step = steps[stepIndexRef.current]
    if (!step) return
    const measured = measureTarget(step.selector)
    if (!measured) return
    const place = computePlacement(measured)
    setRect(measured)
    setPlacement(place)
    setTooltipPos(computeTooltipPosition(measured, place))
  }, [steps])

  useEffect(() => {
    let cancelled = false
    try {
      if (!localStorage.getItem(storageKey)) {
        autoStartTimerRef.current = setTimeout(() => {
          if (!cancelled) startRef.current?.()
        }, startDelayMs)
      }
    } catch {
      /* ignore */
    }
    return () => {
      cancelled = true
      if (autoStartTimerRef.current) clearTimeout(autoStartTimerRef.current)
    }
  }, [storageKey, startDelayMs])

  useEffect(() => {
    const onRestart = (e) => {
      if (e.detail?.tourId === tourId) {
        startRef.current?.()
      }
    }
    window.addEventListener(ONBOARDING_RESTART_EVENT, onRestart)
    return () => window.removeEventListener(ONBOARDING_RESTART_EVENT, onRestart)
  }, [tourId])

  useEffect(() => {
    if (!active) return undefined
    const onResize = () => refreshPosition()
    const onScroll = () => refreshPosition()
    window.addEventListener("resize", onResize)
    window.addEventListener("scroll", onScroll, true)
    return () => {
      window.removeEventListener("resize", onResize)
      window.removeEventListener("scroll", onScroll, true)
    }
  }, [active, refreshPosition])

  const step = steps[stepIndex]
  const isLast = stepIndex === steps.length - 1

  const overlay = active && rect && step && tooltipPos ? (
    <div className="onb-root onb-root--active" role="dialog" aria-modal="true" aria-label="新手引导">
      <div
        className="onb-spotlight"
        style={{
          top: rect.top,
          left: rect.left,
          width: rect.width,
          height: rect.height,
        }}
      />
      <div
        className="onb-tooltip"
        style={{
          top: tooltipPos.top,
          left: tooltipPos.left,
          width: tooltipPos.width,
        }}
        data-placement={placement}
      >
        <div className="onb-tooltip__progress">
          {stepIndex + 1} / {steps.length}
        </div>
        <p className="onb-tooltip__content">{step.content}</p>
        <div className="onb-tooltip__actions">
          <button type="button" className="onb-btn onb-btn--ghost" onClick={finish}>
            跳过
          </button>
          <button type="button" className="onb-btn onb-btn--primary" onClick={goNext}>
            {isLast ? "开始使用" : "下一步"}
          </button>
        </div>
      </div>
    </div>
  ) : null

  if (!overlay) return null
  return createPortal(overlay, document.body)
}
