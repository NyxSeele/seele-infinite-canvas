import { useEffect, useRef } from "react"
import { useLocale } from "../../utils/locale"
import "./CanvasProjectMenu.css"

export default function CanvasProjectMenu({
  open,
  onClose,
  onBackWorkspace,
  onRename,
  onNewProject,
  onDeleteProject,
  onMigrateToTeam,
  readOnly,
}) {
  const { t } = useLocale()
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose?.()
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === "Escape") onClose?.() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div ref={ref} className="cpm-menu nodrag nopan" onPointerDown={(e) => e.stopPropagation()}>
      <button type="button" className="cpm-item" onClick={() => { onBackWorkspace?.(); onClose?.() }}>
        {t("canvas.project.backWorkspace")}
      </button>
      <div className="cpm-divider" />
      <div className="cpm-group-label">{t("canvas.project.label")}</div>
      <button
        type="button"
        className="cpm-item"
        disabled={readOnly}
        onClick={() => { onRename?.(); onClose?.() }}
      >
        {t("canvas.project.rename")}
      </button>
      <button
        type="button"
        className="cpm-item"
        disabled={readOnly}
        onClick={() => { onNewProject?.(); onClose?.() }}
      >
        {t("canvas.project.new")}
      </button>
      {onMigrateToTeam && (
        <button
          type="button"
          className="cpm-item"
          disabled={readOnly}
          onClick={() => { onMigrateToTeam?.(); onClose?.() }}
        >
          {t("ws.project.migrate")}
        </button>
      )}
      <div className="cpm-divider" />
      <button
        type="button"
        className="cpm-item cpm-item--danger"
        disabled={readOnly}
        onClick={() => { onDeleteProject?.(); onClose?.() }}
      >
        {t("canvas.common.delete")}
      </button>
    </div>
  )
}
