import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import NodeLoadingState from "./NodeLoadingState"
import TextWorkflowEdgePlugs from "./TextWorkflowEdgePlugs"
import { SHOT_DIRECTOR_FIELDS } from "../../utils/canvas/shotDirectorFields"
import { formatDurationSec } from "../../utils/canvas/videoDurationIntent"
import { sumSegmentShotDuration } from "../../utils/canvas/scriptDurationNormalize"
import { useLocale } from "../../utils/locale"
import { useCanvasNodeWheel, handleNodeWheel } from "./canvasScrollHelpers"
import "./CanvasShared.css"
import "./canvasNodeLayout.css"
import "./canvasTypography.css"
import "./ShotScriptNode.css"

function defaultSegments() {
  return []
}

const ROOT_STYLE = {
  width: "840px",
  minWidth: "840px",
  boxSizing: "border-box",
}

const LOADING_WRAP_STYLE = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  minHeight: "200px",
  width: "100%",
}

export default function ShotScriptNode({ id, data, selected }) {
  const { t } = useLocale()
  const loading = data.loading === true
  const collabReadOnly = data.readOnly === true
  const [segments, setSegments] = useState(
    () => (Array.isArray(data.segments) ? data.segments : defaultSegments())
  )
  const [expandedShots, setExpandedShots] = useState(() => new Set())
  const [editingField, setEditingField] = useState(null)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState(data.error || "")
  const wrapperRef = useRef(null)
  useCanvasNodeWheel(wrapperRef)

  useEffect(() => {
    if (Array.isArray(data.segments)) {
      setSegments(data.segments)
    }
  }, [data.segments])

  useEffect(() => {
    setError(data.error || "")
  }, [data.error])

  const updateData = useCallback(
    (patch) => {
      if (collabReadOnly) return
      if (data.onUpdate) data.onUpdate(id, patch)
    },
    [id, data, collabReadOnly]
  )

  const updateSegment = useCallback(
    (segIndex, patch) => {
      setSegments((prev) => {
        const next = prev.map((s, i) => (i === segIndex ? { ...s, ...patch } : s))
        updateData({ segments: next })
        return next
      })
    },
    [updateData]
  )

  const updateShot = useCallback(
    (segIndex, shotIndex, patch) => {
      setSegments((prev) => {
        const next = prev.map((seg, si) => {
          if (si !== segIndex) return seg
          const shots = (seg.shots || []).map((shot, ji) =>
            ji === shotIndex ? { ...shot, ...patch } : shot
          )
          return { ...seg, shots }
        })
        updateData({ segments: next })
        return next
      })
    },
    [updateData]
  )

  const toggleShotDetail = useCallback((shotKey) => {
    setExpandedShots((prev) => {
      const next = new Set(prev)
      if (next.has(shotKey)) next.delete(shotKey)
      else next.add(shotKey)
      return next
    })
  }, [])

  const startEdit = useCallback((e, field) => {
    e.stopPropagation()
    if (collabReadOnly) return
    setEditingField(field)
  }, [collabReadOnly])

  const legacyReadOnly = data.legacyReadOnly === true || Boolean(data.migratedToScriptTableId)
  const cardReadOnly = legacyReadOnly || collabReadOnly
  const migrateHandler = data.onMigrateShotScript || data.onImportScriptTable

  const handleMigrate = useCallback(
    async (e) => {
      e.stopPropagation()
      if (collabReadOnly || importing || loading || !migrateHandler) return
      if (!Array.isArray(segments) || segments.length === 0) return
      setImporting(true)
      try {
        await migrateHandler(id)
      } finally {
        setImporting(false)
      }
    },
    [id, migrateHandler, importing, loading, segments, collabReadOnly]
  )

  const nodeZIndex = data.zIndex ?? 0
  const shotsTotalSec = useMemo(() => sumSegmentShotDuration(segments), [segments])
  const targetSec = data.targetVideoDurationSec

  const segmentShotOffsets = useMemo(() => {
    let count = 0
    return segments.map((seg) => {
      const start = count
      count += (seg.shots || []).length
      return start
    })
  }, [segments])

  return (
    <div
      className={`ss-wrapper${selected ? " ss-wrapper--selected" : ""}`}
      style={{ ...ROOT_STYLE, zIndex: nodeZIndex }}
      ref={wrapperRef}
    >
      <TextWorkflowEdgePlugs nodeId={id} nodeType="shot-script" disabled={collabReadOnly} selected={selected} />
      <div className="ss-card" onDoubleClick={(e) => e.stopPropagation()}>
        <div className="ss-header">
          <h2 className="ss-header-title cn-title">{t("canvas.script.mergedPrompt")}</h2>
          {data.truncated && !loading && (
            <span className="ss-truncated-badge nodrag" title={t("canvas.script.truncatedTitle")}>
              {t("canvas.script.truncated")}
            </span>
          )}
        </div>

        {!loading && (
          <div className="ss-legacy-banner nodrag cn-body">
            {legacyReadOnly ? (
              <p className="ss-legacy-banner-text">
                {t("canvas.script.legacyReadonlyBanner")}
              </p>
            ) : (
              <p className="ss-legacy-banner-text">
                {t("canvas.script.legacyBanner")}
              </p>
            )}
          </div>
        )}

        {loading ? (
          <div style={LOADING_WRAP_STYLE}>
            <NodeLoadingState message={t("canvas.script.genShotPrompt")} />
          </div>
        ) : (
          <>
            {(targetSec || data.durationWarning) && !loading && (
              <div className="ss-duration-banner nodrag cn-body">
                {targetSec && (
                  <span>
                    {t("canvas.script.targetDuration", { duration: formatDurationSec(targetSec) })}
                    {" · "}
                    {t("canvas.script.currentDuration", { duration: formatDurationSec(shotsTotalSec) })}
                  </span>
                )}
                {data.durationWarning && (
                  <p className="ss-duration-warn">{data.durationWarning}</p>
                )}
              </div>
            )}

            <div
              className={`ss-body scrollable-content nowheel${cardReadOnly ? " ss-body--readonly" : ""}`}
              onWheel={handleNodeWheel}
            >
              {segments.length === 0 ? (
                <p className="ss-empty">{t("canvas.script.noShots")}</p>
              ) : (
                segments.map((seg, segIndex) => (
                  <section key={seg.id || `seg-${segIndex}`} className="ss-segment">
                    <div className="ss-seg-header">
                      {editingField?.type === "seg-title" && editingField.segIndex === segIndex ? (
                        <input
                          className="ss-seg-title nodrag nowheel"
                          autoFocus
                          defaultValue={seg.title || ""}
                          placeholder={t("canvas.script.segmentTitle")}
                          onBlur={(e) => {
                            updateSegment(segIndex, { title: e.target.value })
                            setEditingField(null)
                          }}
                        />
                      ) : (
                        <span
                          className="ss-seg-title-display cn-section-title"
                          onDoubleClick={(e) => startEdit(e, { type: "seg-title", segIndex })}
                        >
                          {seg.title || t("canvas.script.segmentTitle")}
                        </span>
                      )}
                      <label className="ss-seg-duration-label nodrag">
                        {t("canvas.script.durationShort")}
                        <input
                          type="number"
                          min={1}
                          className="ss-seg-duration nodrag"
                          value={seg.duration ?? 0}
                          onChange={(e) =>
                            updateSegment(segIndex, {
                              duration: Number(e.target.value) || 0,
                            })
                          }
                          onWheel={handleNodeWheel}
                        />
                        s
                      </label>
                    </div>
                    {editingField?.type === "seg-desc" && editingField.segIndex === segIndex ? (
                      <textarea
                        className="ss-seg-desc-edit nodrag nowheel"
                        autoFocus
                        defaultValue={seg.description || ""}
                        placeholder={t("canvas.script.plotSummary")}
                        rows={3}
                        onBlur={(e) => {
                          updateSegment(segIndex, { description: e.target.value })
                          setEditingField(null)
                        }}
                      />
                    ) : (
                      <p
                        className="ss-seg-desc-display cn-body"
                        onDoubleClick={(e) => startEdit(e, { type: "seg-desc", segIndex })}
                      >
                        {seg.description || t("canvas.script.plotSummaryDblClick")}
                      </p>
                    )}

                    {(seg.shots || []).map((shot, shotIndex) => {
                      const shotNum = (segmentShotOffsets[segIndex] ?? 0) + shotIndex + 1
                      const shotKey = shot.id || `${segIndex}-${shotIndex}`
                      const expanded = expandedShots.has(shotKey)
                      return (
                        <article key={shotKey} className="ss-shot-card">
                          <div className="ss-shot-head">
                            <span className="ss-shot-badge cn-emphasis">
                              {t("canvas.script.shot")} {shotNum}
                            </span>
                            <label className="ss-shot-dur-label nodrag">
                              <input
                                type="number"
                                min={4}
                                max={15}
                                className="ss-shot-dur nodrag"
                                value={shot.duration ?? 8}
                                onChange={(e) =>
                                  updateShot(segIndex, shotIndex, {
                                    duration: Number(e.target.value) || 8,
                                  })
                                }
                              />
                              s
                            </label>
                            <button
                              type="button"
                              className="ss-toggle-btn nodrag"
                              onClick={() => toggleShotDetail(shotKey)}
                            >
                              {expanded ? t("canvas.script.collapseParams") : t("canvas.script.expandParams")}
                            </button>
                          </div>
                          {editingField?.type === "shot-prompt"
                          && editingField.segIndex === segIndex
                          && editingField.shotIndex === shotIndex ? (
                            <textarea
                              className="ss-shot-prompt-edit nodrag nowheel"
                              autoFocus
                              defaultValue={shot.prompt || ""}
                              placeholder={t("canvas.script.directorPh")}
                              rows={4}
                              onBlur={(e) => {
                                updateShot(segIndex, shotIndex, { prompt: e.target.value })
                                setEditingField(null)
                              }}
                            />
                          ) : (
                            <p
                              className="ss-shot-prompt-display cn-body-lg"
                              onDoubleClick={(e) =>
                                startEdit(e, { type: "shot-prompt", segIndex, shotIndex })
                              }
                            >
                              {shot.prompt || t("canvas.script.directorPhDblClick")}
                            </p>
                          )}
                          {expanded && (
                            <div className="ss-shot-params">
                              {SHOT_DIRECTOR_FIELDS.map(({ key, label, placeholder }) => {
                                const editType = `shot-${key}`
                                const isEditing =
                                  editingField?.type === editType
                                  && editingField.segIndex === segIndex
                                  && editingField.shotIndex === shotIndex
                                return (
                                  <label key={key} className="ss-param">
                                    <span className="ss-param-label cn-label">{label}</span>
                                    {isEditing ? (
                                      <input
                                        className="nodrag"
                                        autoFocus
                                        defaultValue={shot[key] || ""}
                                        placeholder={placeholder}
                                        onBlur={(e) => {
                                          updateShot(segIndex, shotIndex, { [key]: e.target.value })
                                          setEditingField(null)
                                        }}
                                        onWheel={handleNodeWheel}
                                      />
                                    ) : (
                                      <span
                                        className="ss-field-value"
                                        onDoubleClick={(e) =>
                                          startEdit(e, { type: editType, segIndex, shotIndex })
                                        }
                                      >
                                        {shot[key]?.trim() || "—"}
                                      </span>
                                    )}
                                  </label>
                                )
                              })}
                            </div>
                          )}
                        </article>
                      )
                    })}
                  </section>
                ))
              )}
            </div>

            <button
              type="button"
              className="ss-import-btn nodrag"
              disabled={
                collabReadOnly
                || legacyReadOnly
                || importing
                || loading
                || segments.length === 0
                || !migrateHandler
              }
              onClick={handleMigrate}
            >
              {legacyReadOnly
                ? t("canvas.script.migrated")
                : importing
                  ? t("canvas.script.migrating")
                  : t("canvas.script.migrateToTable")}
            </button>
          </>
        )}
        {error && !loading && <p className="ss-error">{error}</p>}
      </div>
    </div>
  )
}
