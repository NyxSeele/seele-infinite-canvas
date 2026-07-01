import { useCallback, useEffect, useMemo, useState } from "react"
import { useStore } from "reactflow"
import { useCanvasStore, useTeamStore } from "../../stores"
import { getCanvasTeamId } from "../../utils/teamContext"
import { fetchTaskRecords } from "../../services/tasksApi"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import {
  filterGenHistory,
  filterPersonalHistory,
  formatHistoryTime,
  mapTaskRecordsToHistory,
  readGenHistory,
} from "../../utils/canvas/genHistory"
import { useFlyoutMount } from "../../hooks/useFlyoutMount"
import ScopeSwitchPanel from "../common/ScopeSwitchPanel"
import { useLocale } from "../../utils/locale"
import "./GenerationHistoryFlyout.css"

const sp = (e) => e.stopPropagation()

function HistoryThumb({ item, loadFailLabel }) {
  const [broken, setBroken] = useState(false)
  const url = ensureMediaUrl(item.mediaUrl)

  if (broken) {
    return <div className="ghf-thumb ghf-thumb--broken">{loadFailLabel}</div>
  }

  if (item.kind === "video") {
    return (
      <video
        src={url}
        className="ghf-thumb"
        muted
        playsInline
        onError={() => setBroken(true)}
      />
    )
  }

  return (
    <img
      src={url}
      alt=""
      className="ghf-thumb"
      draggable={false}
      onError={() => setBroken(true)}
    />
  )
}

export default function GenerationHistoryFlyout({ open, onClose, getCardPointerHandlers }) {
  const { t } = useLocale()
  const { mounted, closing } = useFlyoutMount(open)
  const expanded = useCanvasStore((s) => s.genHistoryExpanded)
  const setGenHistoryExpanded = useCanvasStore((s) => s.setGenHistoryExpanded)
  const canvasId = useCanvasStore((s) => s.canvasId)
  const projectName = useCanvasStore((s) => s.projectName)
  const projectTeamId = useCanvasStore((s) => s.projectTeamId)
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const canvasTeamId = projectTeamId || activeTeamId
  const [scopeTab, setScopeTab] = useState("mine")
  const [tab, setTab] = useState("image")
  const [personalList, setPersonalList] = useState([])
  const [teamList, setTeamList] = useState([])
  const [teamLoading, setTeamLoading] = useState(false)

  const tabs = useMemo(
    () => [
      { id: "image", label: t("canvas.empty.image") },
      { id: "video", label: t("canvas.empty.video") },
    ],
    [t]
  )

  const canvasNodes = useStore(
    useCallback((s) => {
      const nodes = []
      s.nodeInternals.forEach((n) => {
        nodes.push({ id: n.id, type: n.type, data: n.data })
      })
      return nodes
    }, [])
  )

  const refreshPersonal = useCallback(() => {
    const merged = readGenHistory(canvasNodes, {
      canvasId,
      projectName,
      teamId: null,
    })
    setPersonalList(filterPersonalHistory(merged))
  }, [canvasNodes, canvasId, projectName])

  const refreshTeam = useCallback(async () => {
    const teamId = getCanvasTeamId()
    if (!teamId) {
      setTeamList([])
      return
    }
    setTeamLoading(true)
    try {
      const records = await fetchTaskRecords({ teamId })
      setTeamList(mapTaskRecordsToHistory(records))
    } catch {
      setTeamList([])
    } finally {
      setTeamLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return undefined
    refreshPersonal()
    if (scopeTab === "team") refreshTeam()
    const handler = () => refreshPersonal()
    window.addEventListener("gen-history-updated", handler)
    return () => window.removeEventListener("gen-history-updated", handler)
  }, [open, refreshPersonal, refreshTeam, scopeTab, canvasTeamId])

  useEffect(() => {
    if (!open || scopeTab !== "team") return undefined
    refreshTeam()
  }, [open, scopeTab, refreshTeam, canvasTeamId])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  const isTeamScope = scopeTab === "team"
  const list = isTeamScope ? teamList : personalList
  const filtered = useMemo(() => filterGenHistory(list, tab), [list, tab])

  const emptyDesc = useMemo(() => {
    if (isTeamScope && !canvasTeamId) return t("canvas.history.teamEmpty")
    if (tab === "video") return t("canvas.history.emptyVideo")
    return t("canvas.history.emptyImage")
  }, [isTeamScope, canvasTeamId, tab, t])

  if (!mounted) return null

  return (
    <aside
      className={`ghf-flyout nodrag nopan${open && !closing ? " ghf-flyout--open" : ""}${closing ? " ghf-flyout--closing" : ""}${expanded ? " ghf-flyout--expanded" : ""}`}
      onPointerDown={sp}
      onDoubleClick={sp}
      role="dialog"
      aria-label={t("canvas.history.title")}
    >
      <header className="ghf-head">
        <div className="ghf-head-title">
          <h2 className="ghf-title">
            {isTeamScope ? t("canvas.history.teamLib") : t("canvas.history.personalLib")}
          </h2>
          {canvasTeamId && (
            <>
              <button
                type="button"
                className="ghf-scope-switch"
                title={isTeamScope ? t("canvas.history.switchToMine") : t("canvas.history.switchToTeam")}
                onClick={() => setScopeTab((s) => (s === "mine" ? "team" : "mine"))}
              >
                ⇄
              </button>
              <span className="ghf-scope-hint">
                {isTeamScope ? t("canvas.history.switchToMine") : t("canvas.history.switchToTeam")}
              </span>
            </>
          )}
        </div>
        <div className="ghf-head-actions">
          <button
            type="button"
            className="ghf-icon-btn"
            title={expanded ? t("canvas.common.collapse") : t("canvas.common.expand")}
            onClick={() => setGenHistoryExpanded(!expanded)}
          >
            {expanded ? "⤡" : "⤢"}
          </button>
          <button
            type="button"
            className="ghf-icon-btn"
            aria-label={t("canvas.common.close")}
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </header>

      <ScopeSwitchPanel switchKey={scopeTab} className="ghf-scope-body">
      <div className="ghf-tabs">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.id}
            type="button"
            className={`ghf-tab${tab === tabItem.id ? " ghf-tab--active" : ""}`}
            onClick={() => setTab(tabItem.id)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      <div className="ghf-body alf-scroll-hide">
        {teamLoading && isTeamScope && filtered.length === 0 ? (
          <div className="ghf-empty">
            <p className="ghf-empty-title">{t("canvas.common.loading")}</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="ghf-empty">
            <p className="ghf-empty-title">
              {tab === "video" ? t("canvas.history.noVideo") : t("canvas.history.noImage")}
            </p>
            <p className="ghf-empty-desc">{emptyDesc}</p>
          </div>
        ) : (
          <div className="ghf-grid">
            {filtered.map((item) => (
              <div
                key={item.id}
                className="ghf-card"
                title={t("canvas.history.dragHint")}
                {...getCardPointerHandlers({
                  kind: item.kind,
                  mediaUrl: item.mediaUrl,
                  title: item.title,
                  prompt: item.prompt,
                  previewUrl: item.mediaUrl,
                  source: "history",
                })}
              >
                <HistoryThumb item={item} loadFailLabel={t("canvas.history.loadFail")} />
                <p className="ghf-title-line">{item.title || t("canvas.common.unnamed")}</p>
                <span className="ghf-meta">
                  {[
                    item.ts ? formatHistoryTime(item.ts) : null,
                    item.username && isTeamScope ? item.username : null,
                    item.canvasName || (isTeamScope ? null : t("canvas.topbar.unnamed")),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      </ScopeSwitchPanel>
    </aside>
  )
}
