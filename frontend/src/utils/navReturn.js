/** Navigate to an in-app page while remembering where to return. */
export function navigateWithReturn(navigate, location, to) {
  const from = `${location.pathname}${location.search || ""}`
  navigate(to, { state: { from } })
}

/** Prefer explicit return path, else browser history, else fallback. */
export function goBackOr(navigate, location, fallback = "/workspace") {
  const from = location.state?.from
  if (typeof from === "string" && from && from !== location.pathname) {
    navigate(from)
    return
  }
  if (typeof window !== "undefined" && window.history.length > 1) {
    navigate(-1)
    return
  }
  navigate(fallback)
}
