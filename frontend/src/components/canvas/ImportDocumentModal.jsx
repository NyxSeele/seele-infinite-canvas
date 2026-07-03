import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useLocale } from "../../utils/locale"
import { useOverlayMount, overlayClassNames } from "../../hooks/useFlyoutMount"
import { getThemePortalRoot } from "../../utils/themePortalRoot"
import {
  applyImportDocument,
  parseImportSheets,
  scanImportDocument,
  suggestImportGroups,
} from "../../services/importDocumentApi"
import {
  findNodeIdBySheetName,
  identityGroups,
  mergeCanvasFromImportResponse,
  mergeGroupWithPrevious,
  previewMacroStats,
  splitGroupAt,
} from "../../utils/canvas/importDocumentApply"
import "./ImportDocumentModal.css"

const ACCEPT = ".xlsx,.docx"
const EMPTY_PROJECTS = []

function scanStatusLabel(status, t) {
  if (status === "new") return t("canvas.import.status.new")
  if (status === "changed") return t("canvas.import.status.changed")
  return t("canvas.import.status.skipped")
}

function parseSummary(sheet, t) {
  const sc = sheet?.self_check
  if (!sc) return null
  if (sc.ok) return t("canvas.import.selfCheckPass")
  if (sheet.llm_fix?.fixed) {
    return t("canvas.import.selfCheckFixed", { summary: sheet.llm_fix.fix_summary || "" })
  }
  return t("canvas.import.selfCheckWarn")
}

function isSheetImported(sheetName, importedSheets) {
  return Boolean(importedSheets[sheetName])
}

export default function ImportDocumentModal({
  open,
  onClose,
  projectId: projectIdProp = "",
  projects = EMPTY_PROJECTS,
  theme = "dark",
  onApplied,
  canvasBridge = null,
}) {
  const { t } = useLocale()
  const getNodes = canvasBridge?.getNodes || (() => [])
  const setNodes = canvasBridge?.setNodes
  const setEdges = canvasBridge?.setEdges
  const fileRef = useRef(null)
  const wasOpenRef = useRef(false)

  const [step, setStep] = useState("file")
  const [projectId, setProjectId] = useState(projectIdProp)
  const [file, setFile] = useState(null)
  const [scanResult, setScanResult] = useState(null)
  const [importedSheets, setImportedSheets] = useState({})
  const [selectedSheetNames, setSelectedSheetNames] = useState([])
  const [shotQueue, setShotQueue] = useState([])
  const [queueBanner, setQueueBanner] = useState("")
  const [activeEpisode, setActiveEpisode] = useState(null)
  const [parsedSheet, setParsedSheet] = useState(null)
  const [microRows, setMicroRows] = useState([])
  const [segments, setSegments] = useState([])
  const [groups, setGroups] = useState([])
  const [parseNote, setParseNote] = useState("")
  const [groupNote, setGroupNote] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const macroPreview = useMemo(
    () => previewMacroStats(microRows, groups),
    [microRows, groups]
  )

  const reset = useCallback(() => {
    setStep("file")
    setFile(null)
    setScanResult(null)
    setImportedSheets({})
    setSelectedSheetNames([])
    setShotQueue([])
    setQueueBanner("")
    setActiveEpisode(null)
    setParsedSheet(null)
    setMicroRows([])
    setSegments([])
    setGroups([])
    setParseNote("")
    setGroupNote("")
    setLoading(false)
    setError("")
  }, [])

  useEffect(() => {
    if (!open) {
      wasOpenRef.current = false
      return
    }
    if (wasOpenRef.current) return
    wasOpenRef.current = true
    setProjectId(projectIdProp || projects[0]?.id || "")
    reset()
  }, [open, projectIdProp, projects, reset])

  const toggleSheetSelected = (sheetName) => {
    setSelectedSheetNames((prev) =>
      prev.includes(sheetName)
        ? prev.filter((n) => n !== sheetName)
        : [...prev, sheetName]
    )
  }

  const handleSelectAll = () => {
    const names = (scanResult?.sheets || [])
      .filter((s) => !isSheetImported(s.sheet_name, importedSheets))
      .map((s) => s.sheet_name)
    setSelectedSheetNames(names)
  }

  const handleClearSelection = () => {
    setSelectedSheetNames([])
  }

  const handlePickFile = () => fileRef.current?.click()

  const handleFileChange = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    setError("")
    e.target.value = ""
  }

  const handleScan = async () => {
    if (!file || !projectId) {
      setError(t("canvas.import.needFileProject"))
      return
    }
    setLoading(true)
    setError("")
    try {
      const result = await scanImportDocument({ projectId, file })
      setScanResult(result)
      setStep("pickEpisode")
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || t("canvas.import.scanFailed"))
    } finally {
      setLoading(false)
    }
  }

  const loadGrouping = (sheet) => {
    setMicroRows(sheet.rows || [])
    setSegments(sheet.segments || [])
    setParseNote(parseSummary(sheet, t) || "")
    setGroupNote("")
    setGroups(identityGroups(sheet.rows || []))
  }

  const handleLlmSuggestGroups = async () => {
    if (!parsedSheet || !scanResult) return
    setLoading(true)
    setError("")
    setGroupNote("")
    try {
      const data = await suggestImportGroups({
        projectId,
        importSessionId: scanResult.import_session_id,
        sheetName: parsedSheet.sheet_name,
        mode: "llm",
      })
      setGroups(data.groups || [])
      if (data.summary) {
        setGroupNote(
          data.source === "rule_fallback"
            ? t("canvas.import.llmGroupFallback", { summary: data.summary })
            : t("canvas.import.llmGroupDone", { summary: data.summary })
        )
      } else if (data.source === "rule_fallback") {
        setGroupNote(t("canvas.import.llmGroupFallbackShort"))
      }
    } catch (err) {
      setError(
        err?.response?.data?.detail || err?.message || t("canvas.import.llmGroupFailed")
      )
    } finally {
      setLoading(false)
    }
  }

  const handleResetTableGroups = () => {
    setGroups(identityGroups(microRows))
    setGroupNote("")
    setError("")
  }

  const startImportSheet = async (sheetMeta) => {
    setLoading(true)
    setError("")
    setActiveEpisode(sheetMeta)
    setQueueBanner("")
    try {
      const { sheets } = await parseImportSheets({
        projectId,
        importSessionId: scanResult.import_session_id,
        sheetNames: [sheetMeta.sheet_name],
      })
      const sheet = sheets[0]
      if (sheet.error) {
        setError(sheet.error)
        return
      }
      setParsedSheet(sheet)
      if (sheetMeta.kind === "outline") {
        setStep("reviewOutline")
        return
      }
      loadGrouping(sheet)
      setStep("groupShots")
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || t("canvas.import.parseFailed"))
    } finally {
      setLoading(false)
    }
  }

  const continueShotQueue = async () => {
    if (!shotQueue.length || !scanResult) return
    const [nextName, ...rest] = shotQueue
    setShotQueue(rest)
    const meta = scanResult.sheets.find((s) => s.sheet_name === nextName)
    if (!meta) return
    if (rest.length > 0) {
      setQueueBanner(
        t("canvas.import.batchRemaining", {
          n: rest.length,
          name: scanResult.sheets.find((s) => s.sheet_name === rest[0])?.display_name || rest[0],
        })
      )
    }
    await startImportSheet(meta)
  }

  const handleBatchProcessShots = () => {
    const sheets = (scanResult?.sheets || []).filter(
      (s) =>
        selectedSheetNames.includes(s.sheet_name) &&
        s.kind === "shot_table" &&
        !isSheetImported(s.sheet_name, importedSheets)
    )
    if (!sheets.length) {
      setError(t("canvas.import.selectShotSheets"))
      return
    }
    setError("")
    setSelectedSheetNames([])
    setShotQueue(sheets.slice(1).map((s) => s.sheet_name))
    if (sheets.length > 1) {
      setQueueBanner(
        t("canvas.import.batchRemaining", {
          n: sheets.length - 1,
          name: sheets[1].display_name || sheets[1].sheet_name,
        })
      )
    }
    startImportSheet(sheets[0])
  }

  const handleConfirmOutline = async () => {
    if (!parsedSheet || !activeEpisode) return
    setLoading(true)
    setError("")
    const nodes = getNodes()
    try {
      const result = await applyImportDocument({
        project_id: projectId,
        import_session_id: scanResult.import_session_id,
        outline: {
          confirmed: true,
          sheet_name: parsedSheet.sheet_name,
          text: parsedSheet.text || "",
          content_hash: parsedSheet.content_hash || "",
          label: activeEpisode.display_name || parsedSheet.sheet_name,
          replace_node_id:
            activeEpisode.linked_node_id ||
            findNodeIdBySheetName(nodes, parsedSheet.sheet_name) ||
            null,
        },
      })
      if (setNodes && setEdges) {
        mergeCanvasFromImportResponse(result.canvas_data, setNodes, setEdges)
      }
      setImportedSheets((prev) => ({ ...prev, [parsedSheet.sheet_name]: "imported" }))
      setParsedSheet(null)
      setStep("done")
      onApplied?.({ ...result, projectId })
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || t("canvas.import.applyFailed"))
    } finally {
      setLoading(false)
    }
  }

  const finishEpisodeApply = async () => {
    if (!parsedSheet || !groups.length) {
      setError(t("canvas.import.needGroups"))
      return false
    }
    setLoading(true)
    setError("")
    const nodes = getNodes()
    const scanMeta = activeEpisode
    try {
      const result = await applyImportDocument({
        project_id: projectId,
        import_session_id: scanResult.import_session_id,
        shot_tables: [
          {
            confirmed: true,
            sheet_name: parsedSheet.sheet_name,
            label: parsedSheet.sheet_name,
            content_hash: parsedSheet.content_hash || "",
            segments,
            groups,
            replace_node_id:
              scanMeta?.linked_node_id ||
              findNodeIdBySheetName(nodes, parsedSheet.sheet_name) ||
              null,
          },
        ],
      })
      if (setNodes && setEdges) {
        mergeCanvasFromImportResponse(result.canvas_data, setNodes, setEdges)
      }
      setImportedSheets((prev) => ({ ...prev, [parsedSheet.sheet_name]: "imported" }))
      setParsedSheet(null)
      setGroups([])
      onApplied?.({ ...result, projectId })
      return true
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || t("canvas.import.applyFailed"))
      return false
    } finally {
      setLoading(false)
    }
  }

  const handleApplyEpisode = async () => {
    const ok = await finishEpisodeApply()
    if (!ok) return
    if (shotQueue.length > 0) {
      const rest = shotQueue
      const nextMeta = scanResult.sheets.find((s) => s.sheet_name === rest[0])
      setQueueBanner(
        t("canvas.import.batchRemaining", {
          n: rest.length,
          name: nextMeta?.display_name || rest[0],
        })
      )
      setStep("pickEpisode")
      return
    }
    setStep("done")
  }

  const handleClose = () => {
    if (scanResult?.import_session_id) {
      applyImportDocument({
        project_id: projectId,
        import_session_id: scanResult.import_session_id,
        cleanup_session: true,
        shot_tables: [],
      }).catch(() => {})
    }
    onClose()
  }

  const dispositionBadge = (sheet) => {
    if (isSheetImported(sheet.sheet_name, importedSheets)) {
      return { label: t("canvas.import.imported"), kind: "imported" }
    }
    return { label: scanStatusLabel(sheet.status, t), kind: sheet.status }
  }

  const selectedPendingShots = useMemo(
    () =>
      (scanResult?.sheets || []).filter(
        (s) =>
          selectedSheetNames.includes(s.sheet_name) &&
          s.kind === "shot_table" &&
          !isSheetImported(s.sheet_name, importedSheets)
      ),
    [scanResult, selectedSheetNames, importedSheets]
  )

  const outlineCharCount = parsedSheet?.text?.length || parsedSheet?.stats?.char_count || 0

  const { mounted, closing } = useOverlayMount(open)

  const themeClass = theme === "light" ? "rf-page--light" : "rf-page--dark"

  if (!mounted) return null

  const overlayClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: `idm-overlay ${themeClass}`,
    enterClass: open && !closing ? "motion-modal-overlay-in" : "",
    exitClass: closing ? "motion-modal-overlay-out" : "",
  })

  const modalBase = `idm-modal idm-modal--wide${
    step === "pickEpisode" ? " idm-modal--pick" : ""
  }${step === "groupShots" ? " idm-modal--group" : ""}`

  const modalClasses = overlayClassNames({
    mounted,
    closing,
    open,
    base: modalBase,
    enterClass: open && !closing ? "motion-modal-in" : "",
    exitClass: closing ? "motion-modal-out" : "",
  })

  return createPortal(
    <div className={overlayClasses} onMouseDown={handleClose}>
      <div
        className={modalClasses}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="idm-title">{t("canvas.import.title")}</div>
        <div className="idm-sub">{t("canvas.import.subtitleV2")}</div>
        {step === "pickEpisode" && (
          <p className="idm-pick-hint">{t("canvas.import.pickEpisodeHint")}</p>
        )}

        {error && <div className="idm-error">{error}</div>}
        {queueBanner && step === "pickEpisode" && (
          <div className="idm-queue-banner">{queueBanner}</div>
        )}
        {parseNote && (step === "groupShots" || step === "reviewOutline") && (
          <div className="idm-parse-note">{parseNote}</div>
        )}

        {step === "pickEpisode" && (
          <>
            <div className="idm-pick-toolbar">
              <button
                type="button"
                className="idm-btn-secondary idm-btn-secondary--sm"
                disabled={loading}
                onClick={handleSelectAll}
              >
                {t("canvas.import.selectAll")}
              </button>
              <button
                type="button"
                className="idm-btn-secondary idm-btn-secondary--sm"
                disabled={loading || selectedSheetNames.length === 0}
                onClick={handleClearSelection}
              >
                {t("canvas.import.clearSelection")}
              </button>
              <button
                type="button"
                className="idm-btn-primary idm-btn-primary--sm idm-pick-toolbar-primary"
                disabled={loading || selectedPendingShots.length === 0}
                onClick={handleBatchProcessShots}
              >
                {selectedPendingShots.length > 0
                  ? t("canvas.import.batchProcessShotsN", { n: selectedPendingShots.length })
                  : t("canvas.import.batchProcessShots")}
              </button>
            </div>

            {shotQueue.length > 0 && (
              <div className="idm-pick-queue-actions">
                <button
                  type="button"
                  className="idm-btn-primary idm-btn-primary--sm"
                  disabled={loading}
                  onClick={continueShotQueue}
                >
                  {t("canvas.import.batchProcessNext")}
                </button>
              </div>
            )}
          </>
        )}

        <div className="idm-body">
          {step === "file" && (
            <>
              {!projectIdProp && projects.length > 0 && (
                <select
                  className="idm-project-select"
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name || p.id}
                    </option>
                  ))}
                </select>
              )}
              <input
                ref={fileRef}
                type="file"
                className="idm-file-input"
                accept={ACCEPT}
                onChange={handleFileChange}
              />
              <button type="button" className="idm-file-btn" onClick={handlePickFile}>
                {t("canvas.import.pickFile")}
              </button>
              {file && <div className="idm-file-name">{file.name}</div>}
            </>
          )}

          {step === "pickEpisode" && (
            <div className="idm-sheet-list">
              {(scanResult?.sheets || []).map((s) => {
                  const badge = dispositionBadge(s)
                  const checked = selectedSheetNames.includes(s.sheet_name)
                  const imported = isSheetImported(s.sheet_name, importedSheets)
                  return (
                    <div
                      key={s.sheet_name}
                      className={`idm-sheet-row${imported ? " idm-sheet-row--imported" : ""}`}
                    >
                      <input
                        type="checkbox"
                        className="idm-sheet-check"
                        checked={checked}
                        disabled={loading || imported}
                        onChange={() => toggleSheetSelected(s.sheet_name)}
                        aria-label={s.display_name || s.sheet_name}
                      />
                      <div className="idm-sheet-row-content">
                        <strong className="idm-sheet-title">
                          {s.display_name || s.sheet_name}
                        </strong>
                        <div className="idm-sheet-row-meta">
                          <span className="idm-kind-pill">
                            {s.kind === "outline"
                              ? t("canvas.import.kindOutline")
                              : t("canvas.import.kindShotTable")}
                          </span>
                          {!imported && (
                            <button
                              type="button"
                              className="idm-sheet-review-btn"
                              disabled={loading}
                              onClick={() => startImportSheet(s)}
                            >
                              {t("canvas.import.review")}
                            </button>
                          )}
                          <span className={`idm-status idm-status--${badge.kind}`}>
                            {badge.label}
                          </span>
                        </div>
                      </div>
                    </div>
                  )
                })}
            </div>
          )}

          {step === "reviewOutline" && parsedSheet && (
            <div className="idm-outline-review">
              <div className="idm-outline-review-head">
                <strong>{activeEpisode?.display_name || parsedSheet.sheet_name}</strong>
                <span className="idm-review-meta">
                  {t("canvas.import.charCount", {
                    n: outlineCharCount || (parsedSheet.text || "").length,
                  })}
                </span>
              </div>
              <p className="idm-outline-review-hint">{t("canvas.import.reviewOutlineHint")}</p>
              <div className="idm-outline-preview idm-outline-preview--full">
                {parsedSheet.text || "—"}
              </div>
            </div>
          )}

          {step === "groupShots" && (
            <div className="idm-group-layout">
              <div className="idm-group-preview">
                {t("canvas.import.macroPreview", {
                  macros: macroPreview.macroCount,
                  micros: macroPreview.microCount,
                })}
                {macroPreview.macros.map((m, i) => (
                  <span key={i} className={`idm-macro-chip idm-macro-chip--tone${i % 4}`}>
                    {t("canvas.import.macroChip", {
                      n: i + 1,
                      dur: m.duration,
                      beats: m.beatCount,
                    })}
                  </span>
                ))}
              </div>

              <div className="idm-group-actions">
                <p className="idm-shot-list-hint">{t("canvas.import.shotListHint")}</p>
                <div className="idm-group-actions-btns">
                  <button
                    type="button"
                    className="idm-btn-primary idm-btn-primary--sm"
                    disabled={loading || !microRows.length}
                    onClick={handleLlmSuggestGroups}
                  >
                    {loading ? t("canvas.import.llmGrouping") : t("canvas.import.llmGroup")}
                  </button>
                  <button
                    type="button"
                    className="idm-btn-ghost idm-btn-secondary--sm"
                    disabled={loading || !microRows.length}
                    onClick={handleResetTableGroups}
                  >
                    {t("canvas.import.resetTableGroups")}
                  </button>
                </div>
              </div>
              <p className="idm-llm-group-hint">{t("canvas.import.llmGroupHint")}</p>
              {groupNote && <div className="idm-group-note">{groupNote}</div>}

              <div className="idm-micro-list">
                {groups.map((group, groupIdx) => {
                  const tone = groupIdx % 4
                  const stats = macroPreview.macros[groupIdx]
                  return (
                    <div
                      key={`macro-${groupIdx}-${group.join("-")}`}
                      className={`idm-macro-block idm-macro-block--tone${tone}`}
                    >
                      <div className="idm-macro-block-head">
                        <span className="idm-macro-block-title">
                          {t("canvas.import.macroChip", {
                            n: groupIdx + 1,
                            dur: stats?.duration ?? 0,
                            beats: group.length,
                          })}
                        </span>
                        {groupIdx > 0 && (
                          <button
                            type="button"
                            className="idm-shot-action-btn"
                            onClick={() =>
                              setGroups(mergeGroupWithPrevious(groups, groupIdx))
                            }
                          >
                            {t("canvas.import.mergePrev")}
                          </button>
                        )}
                      </div>
                      <div className="idm-macro-block-rows">
                        {group.map((rowIdx, i) => {
                          const row = microRows[rowIdx]
                          if (!row) return null
                          const prompt = (row.prompt || row.description || "").slice(0, 80)
                          return (
                            <div
                              key={`${row.shotNumber}-${rowIdx}`}
                              className="idm-micro-row"
                            >
                              <span className="idm-micro-num">#{row.shotNumber}</span>
                              <span className="idm-micro-dur">{row.duration || 8}s</span>
                              <span className="idm-micro-prompt">{prompt || "—"}</span>
                              {i > 0 && (
                                <button
                                  type="button"
                                  className="idm-shot-action-btn"
                                  onClick={() => setGroups(splitGroupAt(groups, rowIdx))}
                                >
                                  {t("canvas.import.splitHere")}
                                </button>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {step === "done" && (
            <p className="idm-review-meta">{t("canvas.import.doneEpisodeHint")}</p>
          )}
        </div>

        <div className="idm-footer">
          <button type="button" className="idm-btn-ghost" onClick={handleClose} disabled={loading}>
            {t("canvas.import.close")}
          </button>

          {step === "file" && (
            <button
              type="button"
              className="idm-btn-primary"
              disabled={loading || !file}
              onClick={handleScan}
            >
              {loading ? t("canvas.import.scanning") : t("canvas.import.scan")}
            </button>
          )}

          {step === "reviewOutline" && (
            <>
              <button
                type="button"
                className="idm-btn-ghost"
                disabled={loading}
                onClick={() => {
                  setStep("pickEpisode")
                  setParsedSheet(null)
                }}
              >
                {t("canvas.import.backEpisodes")}
              </button>
              <button
                type="button"
                className="idm-btn-primary"
                disabled={loading}
                onClick={handleConfirmOutline}
              >
                {loading ? t("canvas.import.applying") : t("canvas.import.confirmOutline")}
              </button>
            </>
          )}

          {step === "groupShots" && (
            <>
              <button
                type="button"
                className="idm-btn-ghost"
                disabled={loading}
                onClick={() => {
                  setStep("pickEpisode")
                  setParsedSheet(null)
                  setGroups([])
                }}
              >
                {t("canvas.import.backEpisodes")}
              </button>
              <button
                type="button"
                className="idm-btn-primary"
                disabled={loading || !groups.length}
                onClick={handleApplyEpisode}
              >
                {loading ? t("canvas.import.applying") : t("canvas.import.confirmEpisode")}
              </button>
            </>
          )}

          {step === "done" && (
            <button
              type="button"
              className="idm-btn-primary"
              onClick={() => {
                setStep("pickEpisode")
                if (shotQueue.length > 0) {
                  continueShotQueue()
                }
              }}
            >
              {shotQueue.length > 0
                ? t("canvas.import.batchProcessNext")
                : t("canvas.import.importNextEpisode")}
            </button>
          )}
        </div>
      </div>
    </div>,
    getThemePortalRoot()
  )
}
