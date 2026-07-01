import { useState, useRef, useEffect, useCallback, useMemo } from "react"
import { createPortal } from "react-dom"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../../contexts/AuthContext"
import { useCanvasStore } from "../../stores"
import { sanitizeNodeDataForPersist } from "../../components/canvas/videoReferenceHelpers"
import { normalizeTextResponseNode } from "../../utils/canvas/nodeNormalize"
import { shareCanvas } from "../../services/canvasApi"
import { formatRelativeTime } from "../../utils/canvas/formatRelativeTime"
import CanvasProjectMenu from "./CanvasProjectMenu"
import CanvasPresenceBar from "./CanvasPresenceBar"
import WorkspaceNotifyPanel from "../workspace/WorkspaceNotifyPanel"
import CanvasShareMenu from "./CanvasShareMenu"
import ExportProjectModal from "./ExportProjectModal"
import { IconCollabScreen, IconAgent, IconShare } from "./CanvasTopbarIcons"
import { LineIcon } from "../icons/LineIcons"
import { useNotificationUnread, emitNotificationUnread } from "../../hooks/useNotificationUnread"
import { showDevNotice } from "../common/ProductNoticeModal"
import { useLocale } from "../../utils/locale"

export default function CanvasTopbar({
  projectId = null,
  nodes = [],
  edges = [],
  readOnly = false,
  collabReadOnly = false,
  lockHolder = null,
  presenceMembers = [],
  presenceEnabled = false,
  agentOpen = false,
  agentReadOnly = false,
  onToggleAgent,
  onShareToast,
  onNewProject,
  onDeleteProject,
  onMigrateToTeam,
  mentionToast = null,
}) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { t } = useLocale()
  const { unread: notifyUnread, setUnread: setNotifyUnread } = useNotificationUnread({ listenCanvasWs: true })
  const [notifyOpen, setNotifyOpen] = useState(false)
  const projectName = useCanvasStore((s) => s.projectName)
  const setProjectName = useCanvasStore((s) => s.setProjectName)
  const lastModifiedAt = useCanvasStore((s) => s.lastModifiedAt)
  const lastModifiedBy = useCanvasStore((s) => s.lastModifiedBy)
  const saveStatus = useCanvasStore((s) => s.saveStatus)
  const renameRequest = useCanvasStore((s) => s.renameRequest)
  const requestRename = useCanvasStore((s) => s.requestRename)

  const logoSrc = "/velora-logo.png"

  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(projectName)
  const [menuOpen, setMenuOpen] = useState(false)
  const [shareMenuOpen, setShareMenuOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const inputRef = useRef(null)
  const logoWrapRef = useRef(null)
  const shareBtnRef = useRef(null)

  useEffect(() => { setName(projectName) }, [projectName])
  useEffect(() => { if (editing) inputRef.current?.select() }, [editing])
  useEffect(() => {
    if (renameRequest > 0 && !readOnly) setEditing(true)
  }, [renameRequest, readOnly])

  const handleNameBlur = useCallback(() => {
    setEditing(false)
    const trimmed = name.trim() || t("canvas.topbar.unnamed")
    setName(trimmed)
    setProjectName(trimmed)
  }, [name, setProjectName, t])

  const handleNameKeyDown = useCallback((e) => {
    if (e.key === "Enter") inputRef.current?.blur()
    if (e.key === "Escape") { setName(projectName); setEditing(false) }
  }, [projectName])

  const handleShare = useCallback(async () => {
    if (readOnly) return
    try {
      const serializableNodes = nodes.map((n) => {
        const { onUpdate, onDelete, ...restData } = n.data || {}
        return normalizeTextResponseNode({
          ...n,
          data: sanitizeNodeDataForPersist(restData),
        })
      })
      const res = await shareCanvas({
        canvas_data: { nodes: serializableNodes, edges },
        project_name: projectName,
      })
      const url = `${window.location.origin}${res.url_path}`
      await navigator.clipboard.writeText(url)
      onShareToast?.(t("canvas.topbar.shareCopied"))
    } catch (err) {
      console.error(err)
      onShareToast?.(t("canvas.topbar.shareFailed"))
    }
  }, [nodes, edges, projectName, readOnly, onShareToast, t])

  const q = user?.quota
  const quotaText = q
    ? (q.image_limit < 0 ? "∞" : `${q.image_used ?? 0} / ${q.image_limit}`)
    : null

  const metaLine = useMemo(() => {
    const parts = []
    if (lastModifiedAt) {
      const timeLabel = formatRelativeTime(lastModifiedAt)
      if (timeLabel) {
        parts.push(t("canvas.topbar.modifiedAt", { time: timeLabel }))
      }
      if (lastModifiedBy) {
        parts.push(t("canvas.topbar.modifiedBy", { who: lastModifiedBy }))
      }
    } else {
      parts.push(t("canvas.topbar.unsaved"))
    }
    if (collabReadOnly) {
      const who = lockHolder?.display_name || lockHolder?.username || t("canvas.topbar.otherUser")
      parts.push(t("canvas.topbar.editing", { who }))
    }
    if (saveStatus === "saving") parts.push(t("canvas.topbar.saving"))
    else if (saveStatus === "error") parts.push(t("canvas.topbar.saveError"))
    return parts.join(" · ")
  }, [lastModifiedAt, lastModifiedBy, saveStatus, collabReadOnly, lockHolder, t])

  return (
    <div className="ctb-bar" onPointerDown={(e) => e.stopPropagation()}>
      <div className="ctb-left">
        <div className="ctb-logo-wrap" ref={logoWrapRef}>
          <button
            type="button"
            className="ctb-logo"
            onClick={() => setMenuOpen((v) => !v)}
            title={t("canvas.project.menu")}
          >
            <img
              src={logoSrc}
              alt={t("canvas.topbar.brand")}
              className="ctb-logo-img"
              draggable={false}
            />
          </button>
          <CanvasProjectMenu
            open={menuOpen}
            onClose={() => setMenuOpen(false)}
            readOnly={readOnly}
            onBackWorkspace={() => navigate("/workspace")}
            onRename={requestRename}
            onNewProject={onNewProject}
            onDeleteProject={onDeleteProject}
            onMigrateToTeam={onMigrateToTeam}
          />
        </div>

        <div className="ctb-project">
          {editing ? (
            <input
              ref={inputRef}
              className="ctb-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={handleNameBlur}
              onKeyDown={handleNameKeyDown}
            />
          ) : (
            <button
              type="button"
              className={`ctb-name${readOnly ? " ctb-name--readonly" : ""}`}
              onClick={() => { if (!readOnly) setEditing(true) }}
              title={readOnly ? name : t("canvas.topbar.renameHint")}
            >
              {name}
            </button>
          )}
          <span className={`ctb-meta${saveStatus === "error" ? " ctb-meta--error" : ""}`}>
            {metaLine}
          </span>
        </div>
      </div>

      <div className="ctb-right-wrap">
        <div className="ctb-right-capsule">
        {presenceEnabled && (
          <>
            <CanvasPresenceBar
              members={presenceMembers}
              inline
              currentUserId={user?.id ?? null}
            />
            <div className="ctb-capsule-sep ctb-capsule-sep--half" />
          </>
        )}
        {presenceEnabled && (
          <>
            <button
              type="button"
              className="ctb-capsule-btn ctb-capsule-btn--icon"
              title={t("canvas.topbar.collabScreenHint")}
              onClick={() => showDevNotice(t("canvas.topbar.collabScreen"))}
            >
              <IconCollabScreen />
            </button>
            <div className="ctb-capsule-sep" />
          </>
        )}

        {quotaText && (
          <>
            <div className="ctb-credit-pill" title={t("canvas.topbar.quota")}>
              <span className="ctb-credit-icon">✦</span>
              <span className="ctb-credit-num">{quotaText}</span>
            </div>
            <div className="ctb-capsule-sep" />
          </>
        )}

        {(onToggleAgent || agentReadOnly) && (
          <>
            <button
              type="button"
              className={`ctb-capsule-btn ctb-capsule-btn--icon${agentOpen ? " ctb-capsule-btn--active" : ""}`}
              title={
                agentReadOnly
                  ? t("canvas.topbar.agentReadOnly")
                  : t("canvas.topbar.agent")
              }
              disabled={agentReadOnly}
              onClick={onToggleAgent}
            >
              <IconAgent />
            </button>
            <div className="ctb-capsule-sep" />
          </>
        )}

        <button
          ref={shareBtnRef}
          type="button"
          className={`ctb-capsule-btn ctb-capsule-btn--icon${shareMenuOpen ? " ctb-capsule-btn--active" : ""}`}
          title={readOnly ? t("canvas.topbar.readonlyShare") : t("canvas.topbar.share")}
          disabled={readOnly}
          onClick={() => setShareMenuOpen((v) => !v)}
        >
          <IconShare />
        </button>

        <div className="ctb-capsule-sep" />

        <button
          type="button"
          className="ctb-capsule-btn ctb-capsule-btn--icon ctb-notify-btn"
          title={t("menu.notifications")}
          onClick={() => setNotifyOpen(true)}
        >
          <LineIcon name="bell" size={15} />
          {notifyUnread > 0 && <span className="ctb-notify-dot" aria-hidden />}
        </button>
        </div>
      </div>
      {mentionToast && createPortal(
        <div className="ctb-toast ctb-toast--mention">{mentionToast}</div>,
        document.body
      )}
      <WorkspaceNotifyPanel
        open={notifyOpen}
        onClose={() => setNotifyOpen(false)}
        onUnreadChange={(count) => {
          setNotifyUnread(count)
          emitNotificationUnread(count)
        }}
      />
      <CanvasShareMenu
        open={shareMenuOpen}
        onClose={() => setShareMenuOpen(false)}
        anchorRef={shareBtnRef}
        readOnly={readOnly}
        onCopyLink={handleShare}
        onExportProject={() => setExportOpen(true)}
      />
      <ExportProjectModal open={exportOpen} onClose={() => setExportOpen(false)} />
    </div>
  )
}
