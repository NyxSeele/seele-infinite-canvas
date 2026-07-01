import { useEffect } from "react"

const POLL_MS = 20_000

/**
 * Keep team member list fresh while settings UI is visible.
 * Polls + refreshes on focus / team-context-changed.
 */
export function useTeamMembersRefresh({ enabled, teamId, refreshMembers }) {
  useEffect(() => {
    if (!enabled || !teamId) return undefined

    const tick = () => refreshMembers(teamId)

    const onTeamChange = () => {
      const id = teamId
      if (id) refreshMembers(id)
    }
    const onVisible = () => {
      if (document.visibilityState === "visible") tick()
    }
    const onFocus = () => tick()

    window.addEventListener("team-context-changed", onTeamChange)
    document.addEventListener("visibilitychange", onVisible)
    window.addEventListener("focus", onFocus)

    const timer = window.setInterval(tick, POLL_MS)

    return () => {
      window.removeEventListener("team-context-changed", onTeamChange)
      document.removeEventListener("visibilitychange", onVisible)
      window.removeEventListener("focus", onFocus)
      window.clearInterval(timer)
    }
  }, [enabled, teamId, refreshMembers])
}
