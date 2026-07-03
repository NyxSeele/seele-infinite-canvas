import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { useReactFlow } from "reactflow"
import { useParams } from "react-router-dom"
import { useLocale } from "../../utils/locale"
import {
  createExportJob,
  getExportDownloadUrl,
  getExportJob,
} from "../../services/exportApi"
import api from "../../services/api"
import { useCanvasTheme } from "./CanvasThemeContext"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import "./ExportProjectModal.css"

const POLL_MS = 2000

function scriptTableLabel(node, nodes, t) {
  const rows = node?.data?.rows || []
  const outlineId = node?.data?.sourceOutlineId
  let title = ""
  if (outlineId) {
    const outline = nodes.find((n) => n.id === outlineId && n.type === "outline")
    title = outline?.data?.title?.trim() || ""
  }
  const base = title || t("canvas.script.table")
  return `${base}（${rows.length}${t("canvas.export.shotUnit")}）`
}

export default function ExportProjectModal({
  open,
  onClose,
  defaultScriptTableNodeId = "",
}) {
  const { t } = useLocale()
  const { theme } = useCanvasTheme()
  const { projectId } = useParams()
  const { getNodes } = useReactFlow()
  const [selectedId, setSelectedId] = useState("")
  const [phase, setPhase] = useState("select")
  const [exportId, setExportId] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const pollRef = useRef(null)

  const scriptTables = useMemo(() => {
    if (!open) return []
    return getNodes().filter((n) => n.type === "script-table")
  }, [open, getNodes])

  useEffect(() => {
    if (!open) return
    const nodes = getNodes()
    const tables = nodes.filter((n) => n.type === "script-table")
    const preferred =
      defaultScriptTableNodeId && tables.some((n) => n.id === defaultScriptTableNodeId)
        ? defaultScriptTableNodeId
        : tables[0]?.id || ""
    setSelectedId(preferred)
    setPhase("select")
    setExportId("")
    setError("")
    setLoading(false)
  }, [open, defaultScriptTableNodeId, getNodes])

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(
    (id) => {
      stopPolling()
      pollRef.current = setInterval(async () => {
        try {
          const job = await getExportJob(id)
          if (job.status === "completed") {
            stopPolling()
            setPhase("done")
            setLoading(false)
          } else if (job.status === "failed") {
            stopPolling()
            setPhase("failed")
            setError(job.error_message || t("canvas.export.failed"))
            setLoading(false)
          }
        } catch (err) {
          stopPolling()
          setPhase("failed")
          setError(err?.response?.data?.detail || err?.message || t("canvas.export.failed"))
          setLoading(false)
        }
      }, POLL_MS)
    },
    [stopPolling, t]
  )

  const handleStart = async () => {
    if (!projectId || !selectedId || loading) return
    setLoading(true)
    setError("")
    try {
      const job = await createExportJob({
        projectId,
        scriptTableNodeId: selectedId,
      })
      setExportId(job.id)
      setPhase("processing")
      if (job.status === "completed") {
        setPhase("done")
        setLoading(false)
        return
      }
      if (job.status === "failed") {
        setPhase("failed")
        setError(job.error_message || t("canvas.export.failed"))
        setLoading(false)
        return
      }
      startPolling(job.id)
    } catch (err) {
      setPhase("failed")
      setError(err?.response?.data?.detail || err?.message || t("canvas.export.failed"))
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!exportId) return
    const url = getExportDownloadUrl(exportId)
    const token = localStorage.getItem("access_token")
    if (!token) {
      window.location.href = url
      return
    }
    api
      .get(url, { responseType: "blob" })
      .then((res) => {
        const blob = new Blob([res.data], { type: "application/zip" })
        const objectUrl = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = objectUrl
        a.download = `export_${exportId.slice(0, 8)}.zip`
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(objectUrl)
      })
      .catch(() => {
        window.open(url, "_blank")
      })
  }

  const handleClose = () => {
    stopPolling()
    onClose?.()
  }

  const { mounted, closing } = useOverlayMount(open)

  const nodes = getNodes()
  const themeClass = theme === "light" ? "rf-page--light" : "rf-page--dark"

  if (!mounted) return null

  const overlayClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: `epm-overlay ${themeClass}`,
    enterClass: open && !closing ? "motion-modal-overlay-in" : "",
    exitClass: closing ? "motion-modal-overlay-out" : "",
  })

  const modalClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: "epm-modal",
    enterClass: open && !closing ? "motion-modal-in" : "",
    exitClass: closing ? "motion-modal-out" : "",
  })

  return createPortal(
    <div className={overlayClasses} onClick={handleClose}>
      <div className={modalClasses} onClick={(e) => e.stopPropagation()}>
        <div className="epm-title">{t("canvas.export.title")}</div>

        {phase === "select" && (
          <>
            <p className="epm-body">{t("canvas.export.selectHint")}</p>
            {scriptTables.length === 0 ? (
              <p className="epm-empty">{t("canvas.export.noScriptTable")}</p>
            ) : scriptTables.length === 1 ? (
              <p className="epm-single">
                {scriptTableLabel(scriptTables[0], nodes, t)}
              </p>
            ) : (
              <div className="epm-list">
                {scriptTables.map((node) => (
                  <label key={node.id} className="epm-item">
                    <input
                      type="radio"
                      name="export-script-table"
                      value={node.id}
                      checked={selectedId === node.id}
                      onChange={() => setSelectedId(node.id)}
                    />
                    <span>{scriptTableLabel(node, nodes, t)}</span>
                  </label>
                ))}
              </div>
            )}
          </>
        )}

        {phase === "processing" && (
          <p className="epm-body epm-processing">{t("canvas.export.processing")}</p>
        )}

        {phase === "done" && (
          <p className="epm-body epm-success">{t("canvas.export.ready")}</p>
        )}

        {phase === "failed" && error && (
          <p className="epm-body epm-error">{error}</p>
        )}

        <div className="epm-footer">
          <button type="button" className="epm-btn-ghost" onClick={handleClose}>
            {phase === "done" ? t("canvas.common.close") : t("canvas.common.cancel")}
          </button>
          {phase === "select" && (
            <button
              type="button"
              className="epm-btn-primary"
              onClick={handleStart}
              disabled={loading || !selectedId || scriptTables.length === 0}
            >
              {loading ? t("canvas.common.loading") : t("canvas.export.start")}
            </button>
          )}
          {phase === "done" && (
            <button type="button" className="epm-btn-primary" onClick={handleDownload}>
              {t("canvas.export.download")}
            </button>
          )}
        </div>
      </div>
    </div>,
    getThemePortalRoot()
  )
}
