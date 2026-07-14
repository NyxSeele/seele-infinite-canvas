import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useLocation } from "react-router-dom"
import { useCanvasStore } from "../../stores"
import "./AppUpdateBanner.css"

/** 后台轮询间隔（仅在页面可见时执行） */
const POLL_MS = 5 * 60_000
/** 两次检测之间的最短间隔，避免切 tab 时连续请求 */
const MIN_CHECK_INTERVAL_MS = 3 * 60_000
/** 用户关闭横幅后，同一版本不再提示的时长 */
const SNOOZE_MS = 6 * 60 * 60_000

const DISMISS_STORAGE_KEY = "velora:update-dismissed-build"
const SNOOZE_STORAGE_KEY = "velora:update-snooze-until"

function resolveBannerTheme(storeTheme, pathname) {
  // Public review shell is always dark — match the page, not studio login theme.
  if (pathname.startsWith("/review")) return "dark"
  if (storeTheme === "light" || storeTheme === "dark") return storeTheme
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"
  }
  return "light"
}

function readStorage(key) {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key, value) {
  try {
    sessionStorage.setItem(key, value)
  } catch {
    /* private browsing / quota */
  }
}

function isUpdateSuppressed(remoteBuildId) {
  if (!remoteBuildId) return true
  const dismissed = readStorage(DISMISS_STORAGE_KEY)
  if (dismissed === String(remoteBuildId)) return true
  const snoozeUntil = Number(readStorage(SNOOZE_STORAGE_KEY) || 0)
  return Date.now() < snoozeUntil
}

function rememberDismiss(remoteBuildId) {
  if (!remoteBuildId) return
  writeStorage(DISMISS_STORAGE_KEY, String(remoteBuildId))
  writeStorage(SNOOZE_STORAGE_KEY, String(Date.now() + SNOOZE_MS))
}

export default function AppUpdateBanner() {
  const theme = useCanvasStore((s) => s.theme)
  const location = useLocation()
  const [visible, setVisible] = useState(false)
  const [remoteBuildId, setRemoteBuildId] = useState(null)
  const lastCheckAtRef = useRef(0)
  const inFlightRef = useRef(false)
  const bannerTheme = useMemo(
    () => resolveBannerTheme(theme, location.pathname || "/"),
    [theme, location.pathname],
  )

  const check = useCallback(async ({ force = false } = {}) => {
    const current = import.meta.env.VITE_APP_BUILD_ID
    if (!current || inFlightRef.current) return

    const now = Date.now()
    if (!force && now - lastCheckAtRef.current < MIN_CHECK_INTERVAL_MS) return

    inFlightRef.current = true
    lastCheckAtRef.current = now
    try {
      const res = await fetch(`/version.json?t=${now}`, { cache: "no-store" })
      if (!res.ok) return
      const data = await res.json()
      const remoteId = data?.buildId ? String(data.buildId) : ""
      if (!remoteId || remoteId === String(current)) {
        setVisible(false)
        setRemoteBuildId(null)
        return
      }
      if (isUpdateSuppressed(remoteId)) {
        setVisible(false)
        setRemoteBuildId(remoteId)
        return
      }
      setRemoteBuildId(remoteId)
      setVisible(true)
    } catch {
      /* ignore network errors */
    } finally {
      inFlightRef.current = false
    }
  }, [])

  useEffect(() => {
    const initialTimer = window.setTimeout(() => {
      check({ force: true })
    }, 15_000)

    const pollTimer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return
      check()
    }, POLL_MS)

    const onVisible = () => {
      if (document.visibilityState === "visible") check()
    }
    document.addEventListener("visibilitychange", onVisible)

    return () => {
      window.clearTimeout(initialTimer)
      window.clearInterval(pollTimer)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [check])

  const handleDismiss = useCallback(() => {
    rememberDismiss(remoteBuildId)
    setVisible(false)
  }, [remoteBuildId])

  if (!visible) return null

  return (
    <div className={`aub-banner aub-banner--${bannerTheme}`} role="status">
      <span className="aub-text">发现新版本，刷新后即可使用最新功能</span>
      <button type="button" className="aub-btn" onClick={() => window.location.reload()}>
        立即刷新
      </button>
      <button type="button" className="aub-dismiss" aria-label="关闭" onClick={handleDismiss}>
        ×
      </button>
    </div>
  )
}
