import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"
import { useCanvasStore, useTeamStore } from "../stores"
import { joinTeamByInvite, previewTeamInvite } from "../services/teamApi"
import "./JoinTeam.css"

export default function JoinTeam() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user, loading: authLoading, refreshUser } = useAuth()
  const theme = useCanvasStore((s) => s.theme)
  const refreshTeams = useTeamStore((s) => s.refreshTeams)
  const setActiveTeamId = useTeamStore((s) => s.setActiveTeamId)

  const token = useMemo(() => {
    const direct = searchParams.get("token")
    if (direct) return direct.trim()
    const legacyTeam = searchParams.get("team")
    const legacyToken = searchParams.get("token")
    return legacyToken?.trim() || ""
  }, [searchParams])

  const [preview, setPreview] = useState(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (authLoading || !user) return
    if (!token) {
      setError("邀请链接无效，缺少 token")
      setLoading(false)
      return
    }
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError("")
      try {
        const data = await previewTeamInvite(token)
        if (!cancelled) setPreview(data)
      } catch (err) {
        if (!cancelled) {
          setError(err?.response?.data?.detail || err.message || "无法解析邀请链接")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [authLoading, user, token])

  const handleJoin = useCallback(async () => {
    if (!token || busy) return
    setBusy(true)
    setError("")
    try {
      const team = await joinTeamByInvite(token)
      await refreshUser?.()
      await refreshTeams()
      if (team?.id) setActiveTeamId(team.id)
      window.dispatchEvent(new CustomEvent("team-context-changed"))
      navigate("/workspace", { replace: true })
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "加入团队失败")
    } finally {
      setBusy(false)
    }
  }, [token, busy, refreshTeams, refreshUser, setActiveTeamId, navigate])

  const teamName = preview?.team?.name || "团队"

  return (
    <div className={`jt-page rf-page rf-page--${theme}`}>
      <div className="jt-card">
        <h1>加入团队</h1>
        {loading ? (
          <p className="jt-muted">正在验证邀请链接…</p>
        ) : error && !preview ? (
          <>
            <p className="jt-error">{error}</p>
            <button type="button" className="jt-btn" onClick={() => navigate("/workspace")}>
              返回工作区
            </button>
          </>
        ) : (
          <>
            <p className="jt-desc">
              {preview?.already_member
                ? `你已是「${teamName}」的成员。`
                : `邀请你加入团队「${teamName}」，加入后可共享团队画布与资源。`}
            </p>
            {preview?.settings?.quotaType && (
              <p className="jt-muted jt-quota">
                {preview.settings.quotaType === "unlimited"
                  ? "通过此链接加入可使用团队 Tapies 额度。"
                  : "通过此链接加入将获得团队分配的 Tapies 额度。"}
              </p>
            )}
            {error && <p className="jt-error">{error}</p>}
            <div className="jt-actions">
              <button type="button" className="jt-btn jt-btn--ghost" onClick={() => navigate("/workspace")}>
                取消
              </button>
              <button
                type="button"
                className="jt-btn jt-btn--primary"
                disabled={busy || preview?.already_member}
                onClick={handleJoin}
              >
                {preview?.already_member ? "已是成员" : busy ? "加入中…" : "确认加入"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
