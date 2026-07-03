import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useReactFlow } from "reactflow"
import { formatScreenplayParagraphs } from "../../utils/canvas/textFormat"
import {
  outlineSceneMetaEntries,
  patchSceneMetaField,
} from "../../utils/canvas/outlineSceneMeta"
import { useLocale } from "../../utils/locale"
import { outlineToExportText } from "../../utils/canvas/cardExportText"
import NodeLoadingState from "./NodeLoadingState"
import NodeCardDotsMenu from "./NodeCardDotsMenu"
import TextWorkflowEdgePlugs from "./TextWorkflowEdgePlugs"
import { useCanvasNodeWheel, handleNodeWheel } from "./canvasScrollHelpers"
import "./canvasNodeLayout.css"
import "./canvasTypography.css"
import "./OutlineNode.css"

const ROOT_STYLE = {
  width: "540px",
  minWidth: "540px",
  boxSizing: "border-box",
}

function initialExpanded(scenes) {
  const list = scenes || []
  if (list.length === 0) return {}
  const firstId = list[0]?.id || "scene-0"
  return { [firstId]: true }
}

export default function OutlineNode({ id, data, selected }) {
  const { t } = useLocale()
  const { setNodes } = useReactFlow()
  const rootRef = useRef(null)
  useCanvasNodeWheel(rootRef)
  const readOnly = data.readOnly === true
  const [expandedScenes, setExpandedScenes] = useState(() => initialExpanded(data.scenes))
  const [editingField, setEditingField] = useState(null)
  const [selectedVersion, setSelectedVersion] = useState(data.selectedVersionIndex ?? 0)

  const versions = useMemo(() => {
    if (Array.isArray(data.versions) && data.versions.length > 0) {
      return data.versions
    }
    const list = Array.isArray(data.scenes) ? data.scenes : []
    if (list.length === 0) return []
    return [{ title: data.title || t("canvas.outline.title"), scenes: list }]
  }, [data.versions, data.scenes, data.title, t])

  useEffect(() => {
    if (typeof data.selectedVersionIndex === "number") {
      setSelectedVersion(data.selectedVersionIndex)
    }
  }, [data.selectedVersionIndex])

  useEffect(() => {
    if (Array.isArray(data.scenes) && data.scenes.length > 0) {
      setExpandedScenes((prev) => {
        if (Object.keys(prev).length > 0) return prev
        return initialExpanded(data.scenes)
      })
    }
  }, [data.scenes])

  const updateData = useCallback(
    (newData) => {
      if (readOnly) return
      if (data.onUpdate) {
        data.onUpdate(id, newData)
        return
      }
      setNodes((nodes) =>
        nodes.map((n) =>
          n.id === id ? { ...n, data: { ...n.data, ...newData } } : n
        )
      )
    },
    [id, data, setNodes, readOnly]
  )

  const patchVersions = useCallback(
    (nextScenes, versionIndex = selectedVersion) => {
      if (versions.length <= 1) {
        return { scenes: nextScenes }
      }
      const nextVersions = versions.map((v, i) =>
        i === versionIndex ? { ...v, scenes: nextScenes } : v
      )
      return { scenes: nextScenes, versions: nextVersions }
    },
    [versions, selectedVersion]
  )

  const scenes = useMemo(
    () => (Array.isArray(data.scenes) ? data.scenes : []),
    [data.scenes]
  )

  const exportText = useMemo(
    () => outlineToExportText({ title: data.title, scenes }),
    [data.title, scenes]
  )

  const selectVersion = useCallback(
    (index) => {
      if (readOnly) return
      const v = versions[index]
      if (!v) return
      setSelectedVersion(index)
      setEditingField(null)
      updateData({
        selectedVersionIndex: index,
        title: v.title,
        scenes: v.scenes,
      })
    },
    [versions, updateData, readOnly]
  )

  const handleGenerateShots = useCallback(
    async (e) => {
      e.stopPropagation()
      if (readOnly || data.loading || data.generatingShots || scenes.length === 0) return
      updateData({ generatingShots: true, error: null })
      try {
        const outlinePayload = JSON.stringify({
          title: data.title || "",
          scenes,
          target_video_duration_sec: data.targetVideoDurationSec ?? undefined,
          source_idea: data.sourceIdea || "",
        })
        const payload = {
          outline: outlinePayload,
          target_duration_sec: data.targetVideoDurationSec ?? undefined,
        }
        console.log("generate-shots payload:", payload)

        const generate =
          data.onGenerateScriptTable || data.onGenerateShotScript
        if (!generate) {
          console.error("generate-shots error: onGenerateScriptTable 未注入")
          updateData({ error: t("canvas.error.canvasNotReady") })
          return
        }
        await generate(id, outlinePayload)
      } catch (err) {
        console.error("generate-shots error:", err)
        const msg = err.response?.data?.detail || err.message || t("canvas.outline.shotFail")
        updateData({
          error: typeof msg === "string" ? msg : t("canvas.outline.shotFail"),
        })
      } finally {
        updateData({ generatingShots: false })
      }
    },
    [id, data, scenes, updateData, t, readOnly]
  )

  const startEdit = useCallback((e, field) => {
    e.stopPropagation()
    if (readOnly) return
    setEditingField(field)
  }, [readOnly])

  const body = (
    <>
      <div className="outline-node-header">
        <span className="outline-node-icon">🎬</span>
        <span className="outline-node-title cn-title">{data.title || t("canvas.outline.title")}</span>
        {data.targetVideoDurationSec ? (
          <span className="outline-target-dur cn-label">
            {t("canvas.outline.targetMin", {
              n: Math.round(data.targetVideoDurationSec / 60) || 1,
            })}
          </span>
        ) : null}
        <NodeCardDotsMenu
          text={exportText}
          filenamePrefix={t("canvas.outline.title")}
          visible={!data.loading}
        />
      </div>

      {versions.length > 1 && (
        <div className="outline-version-tabs">
          {versions.map((v, index) => (
            <button
              key={`ver-${index}`}
              type="button"
              className={`outline-version-tab nodrag${selectedVersion === index ? " outline-version-tab--active" : ""}`}
              onClick={(e) => {
                e.stopPropagation()
                selectVersion(index)
              }}
            >
              {v.title || t("canvas.outline.version", { n: index + 1 })}
            </button>
          ))}
        </div>
      )}

      <div className="outline-node-body scrollable-content nowheel">
        {data.generatingShots && (
          <div className="outline-generating-overlay nodrag">
            <NodeLoadingState message={t("canvas.outline.genShots")} />
          </div>
        )}
        {scenes.length === 0 ? (
          <p className="outline-empty">
            {data.generatingShots ? t("canvas.outline.shotsPending") : t("canvas.outline.noScenes")}
          </p>
        ) : (
          scenes.map((scene, index) => {
            const sceneId = scene.id || `scene-${index}`
            const isExpanded = expandedScenes[sceneId]
            return (
              <div key={sceneId} className="outline-scene">
                <div
                  className="outline-scene-header"
                  onClick={() =>
                    setExpandedScenes((prev) => ({
                      ...prev,
                      [sceneId]: !prev[sceneId],
                    }))
                  }
                >
                  <span className="outline-scene-arrow">
                    {isExpanded ? "▼" : "▶"}
                  </span>
                  <span className="outline-scene-title cn-section-title">{scene.title}</span>
                </div>

                {isExpanded && (
                  <div className="outline-scene-body">
                    {outlineSceneMetaEntries(scene).map((entry) => (
                      <div key={entry.key} className="outline-scene-meta">
                        <span className="outline-meta-label cn-label">{entry.label}</span>
                        {editingField?.sceneId === sceneId &&
                        editingField?.field === entry.field ? (
                          <input
                            autoFocus
                            defaultValue={entry.value}
                            className="outline-meta-input nodrag"
                            onBlur={(e) => {
                              const newScenes = scenes.map((s) =>
                                s.id === sceneId
                                  ? patchSceneMetaField(s, entry.field, e.target.value)
                                  : s
                              )
                              updateData(patchVersions(newScenes))
                              setEditingField(null)
                            }}
                          />
                        ) : (
                          <span
                            className="outline-meta-value"
                            onDoubleClick={(ev) =>
                              startEdit(ev, { sceneId, field: entry.field })
                            }
                          >
                            {entry.value}
                          </span>
                        )}
                      </div>
                    ))}

                    {editingField?.sceneId === sceneId &&
                    editingField?.field === "content" ? (
                      <textarea
                        autoFocus
                        defaultValue={scene.content}
                        className="outline-scene-content-edit nodrag nowheel scrollable-content"
                        onBlur={(e) => {
                          const formatted = formatScreenplayParagraphs(e.target.value)
                          const newScenes = scenes.map((s) =>
                            s.id === sceneId ? { ...s, content: formatted } : s
                          )
                          updateData(patchVersions(newScenes))
                          setEditingField(null)
                        }}
                      />
                    ) : (
                      <p
                        className="outline-scene-content cn-content-slot--scene cn-body-lg"
                        onDoubleClick={(e) =>
                          startEdit(e, { sceneId, field: "content" })
                        }
                      >
                        {scene.content}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>

      {data.error && (
        <p className="outline-error">{data.error}</p>
      )}
      {data.truncated && !data.loading && (
        <p className="outline-truncated-warn nodrag">
          {t("canvas.outline.truncatedRegen")}
        </p>
      )}

      <div className="outline-node-footer">
        <button
          type="button"
          className="outline-generate-btn nodrag"
          onClick={handleGenerateShots}
          disabled={readOnly || data.generatingShots || scenes.length === 0}
        >
          {data.generatingShots ? t("canvas.outline.genShots") : t("canvas.outline.genTable")}
        </button>
      </div>
    </>
  )

  return (
    <div className="outline-node" style={ROOT_STYLE} ref={rootRef}>
      <TextWorkflowEdgePlugs nodeId={id} nodeType="outline" disabled={readOnly} selected={selected} />
      <div className={`outline-card${selected ? " outline-card--selected" : ""}${readOnly ? " outline-card--readonly" : ""}`} onDoubleClick={(e) => e.stopPropagation()}>
        {data.loading ? (
          <>
            <div className="outline-node-header">
              <span className="outline-node-icon">🎬</span>
              <span className="outline-node-title">{t("canvas.outline.genOutline")}</span>
            </div>
            <div className="outline-node-body scrollable-content nowheel outline-node-body--loading">
              <NodeLoadingState message={t("canvas.outline.organizing")} />
              {[1, 2, 3].map((i) => (
                <div key={i} className="outline-scene-skeleton" />
              ))}
            </div>
          </>
        ) : (
          body
        )}
      </div>
    </div>
  )
}
