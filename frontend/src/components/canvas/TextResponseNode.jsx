import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useReactFlow } from "reactflow"
import { useCanvasStore, useModelStore } from "../../stores"
import { titleCaseWords } from "../../utils/canvas/textFormat"
import {
  parseOutlineStructureResponse,
  postOutlineStructure,
} from "../../utils/canvas/outlineStructureApi"
import { parseTargetDurationSec } from "../../utils/canvas/videoDurationIntent"
import { useLocale } from "../../utils/locale"
import GenerationStopButton from "./GenerationStopButton"
import GenerationBrandLoader from "./GenerationBrandLoader"
import NodeCardDotsMenu from "./NodeCardDotsMenu"
import TextWorkflowEdgePlugs from "./TextWorkflowEdgePlugs"
import { useCanvasNodeWheel } from "./canvasScrollHelpers"
import "./CanvasShared.css"
import "./canvasNodeLayout.css"
import "./canvasTypography.css"
import "./TextResponseNode.css"

const OUTLINE_OFFSET_X = 520
const OUTLINE_NODE_WIDTH = 540

export default function TextResponseNode({ id, data, selected }) {
  const { t } = useLocale()
  const readOnly = data.readOnly === true
  const status = data.status || "generating"
  const [content, setContent] = useState(data.content || "")
  const [editing, setEditing] = useState(false)
  const error = data.error || ""
  const syncPromptBar = useCanvasStore((s) => s.syncPromptBar)
  const textModels = useModelStore((s) => s.textModels)
  const { setNodes, getNode } = useReactFlow()
  const wrapperRef = useRef(null)
  useCanvasNodeWheel(wrapperRef)

  const modelTitle = useMemo(() => {
    const modelId = data.model || data.modelId
    const m = textModels.find((x) => x.id === modelId)
    const name = m?.display_name || modelId || t("canvas.text.aiReply")
    return titleCaseWords(name)
  }, [textModels, data.model, data.modelId, t])

  const [screenplayError, setScreenplayError] = useState("")
  const [screenplayLoading, setScreenplayLoading] = useState(false)
  const [importingScriptTable, setImportingScriptTable] = useState(false)
  const [importScriptError, setImportScriptError] = useState("")
  const outlineSynced = data.outlineSynced === true
  const outlineNodeIdRef = useRef(null)
  const autoOutlineStartedRef = useRef(false)

  const screenplayMode = data.screenplayMode === true

  useEffect(() => {
    if (!editing) {
      setContent(data.content || "")
    }
  }, [data.content, editing])

  useEffect(() => {
    if (status !== "completed") {
      setEditing(false)
    }
    if (status === "generating") {
      autoOutlineStartedRef.current = false
    }
  }, [status])

  const syncContent = useCallback(
    (value) => {
      if (readOnly) return
      const text = value ?? ""
      if (data.onUpdate) {
        data.onUpdate(id, { content: text, prompt: text })
      }
      // 仅同步本卡 AI 回复，勿写回上游 text-note（避免大纲/回复编辑后污染原文本卡）
      syncPromptBar(id, text)
    },
    [id, data, syncPromptBar, readOnly]
  )

  const handleContentChange = useCallback(
    (e) => {
      const value = e.target.value
      setContent(value)
      syncContent(value)
    },
    [syncContent]
  )

  const handleBlurEdit = useCallback(() => {
    setEditing(false)
    syncContent(content)
  }, [content, syncContent])

  const handleRetry = useCallback((e) => {
    e.stopPropagation()
    if (readOnly) return
    setEditing(false)
    data.onRetry?.(id)
  }, [id, data, readOnly])

  const handleGenerateScreenplay = useCallback(
    async (e) => {
      e.stopPropagation()
      if (readOnly) return
      const screenplayText = (content || "").trim()
      if (!screenplayText || screenplayLoading) return

      const responseNode = getNode(id)
      const sourceId = responseNode?.data?.sourceNodeId
      const sourceNote = sourceId ? getNode(sourceId) : null
      const sourceIdea = (sourceNote?.data?.prompt || data.prompt || "").trim()
      const targetVideoDurationSec =
        parseTargetDurationSec(sourceIdea || screenplayText) ?? undefined

      const source = responseNode
      if (!source) return
      if (!data.composeNodeData) {
        setScreenplayError(t("canvas.error.canvasNotReady"))
        return
      }

      setScreenplayError("")
      setScreenplayLoading(true)

      const outlineId = `outline-${Date.now()}`
      outlineNodeIdRef.current = outlineId
      const z = (source.zIndex ?? source.data?.zIndex ?? 0) + 1

      setNodes((ns) => [
        ...ns,
        {
          id: outlineId,
          type: "outline",
          position: {
            x: source.position.x + OUTLINE_OFFSET_X,
            y: source.position.y,
          },
          width: OUTLINE_NODE_WIDTH,
          zIndex: z,
          draggable: true,
          data: (data.composeOutlineNodeData ?? data.composeNodeData)({
            loading: true,
            title: "",
            scenes: [],
            versions: [],
            selectedVersionIndex: 0,
            error: null,
            truncated: false,
            zIndex: z,
          }),
          style: { zIndex: z, width: OUTLINE_NODE_WIDTH },
        },
      ])
      data.connectOutlineFromResponse?.(id, outlineId)

      try {
        const res = await postOutlineStructure({
          text: screenplayText,
          target_duration_sec: targetVideoDurationSec ?? null,
          source_idea: sourceIdea || screenplayText,
        })
        const outlineFields = parseOutlineStructureResponse(res, {
          sourceIdea: sourceIdea || screenplayText,
          targetVideoDurationSec,
        })
        const targetId = outlineNodeIdRef.current

        setNodes((ns) =>
          ns.map((n) =>
            n.id === targetId
              ? {
                  ...n,
                  data: {
                    ...n.data,
                    ...outlineFields,
                  },
                }
              : n
          )
        )
        if (data.onUpdate) {
          data.onUpdate(id, {
            outlineSynced: true,
            outlineNodeId: targetId,
          })
        }
      } catch (err) {
        const msg = err.response?.data?.detail || err.message || t("canvas.text.scriptGenFail")
        const detail = typeof msg === "string" ? msg : t("canvas.text.scriptGenFail")
        const targetId = outlineNodeIdRef.current
        setNodes((ns) =>
          ns.map((n) =>
            n.id === targetId
              ? { ...n, data: { ...n.data, loading: false, error: detail } }
              : n
          )
        )
        setScreenplayError(detail)
      } finally {
        setScreenplayLoading(false)
      }
    },
    [id, content, screenplayLoading, data, getNode, setNodes, t, readOnly]
  )

  useEffect(() => {
    if (readOnly) return
    if (status !== "completed" || !screenplayMode || !data.outlineAutoPending) return
    if (data.outlineSynced) return
    if (autoOutlineStartedRef.current || screenplayLoading) return
    if (!content?.trim()) return
    autoOutlineStartedRef.current = true
    if (data.onUpdate) {
      data.onUpdate(id, { outlineAutoPending: false })
    }
    handleGenerateScreenplay({ stopPropagation: () => {} })
  }, [
    status,
    screenplayMode,
    data.outlineAutoPending,
    content,
    screenplayLoading,
    handleGenerateScreenplay,
    id,
    data,
    readOnly,
  ])

  const handleDoubleClick = useCallback((e) => {
    e.stopPropagation()
    if (readOnly || status !== "completed" || !content) return
    setEditing(true)
  }, [status, content, readOnly])

  const importHandler = data.onImportScriptTable
  const migratedToScriptTable = Boolean(data.migratedToScriptTableId)

  const handleImportScriptTable = useCallback(
    async (e) => {
      e.stopPropagation()
      if (readOnly || importingScriptTable || !importHandler) return
      const text = (content || "").trim()
      if (!text) return
      setImportScriptError("")
      setImportingScriptTable(true)
      try {
        await importHandler(id)
      } catch (err) {
        setImportScriptError(err.message || t("canvas.common.unknownError"))
      } finally {
        setImportingScriptTable(false)
      }
    },
    [readOnly, importingScriptTable, importHandler, content, id, t]
  )

  const sp = (e) => e.stopPropagation()
  const nodeZIndex = data.zIndex ?? 0

  return (
    <div
      className={`tr-wrapper${selected ? " tr-wrapper--selected" : ""}`}
      style={{ zIndex: nodeZIndex }}
      ref={wrapperRef}
    >
      <TextWorkflowEdgePlugs nodeId={id} nodeType="text-response" disabled={readOnly} selected={selected} />
      <div className="tr-card" onDoubleClick={sp}>
        <div className="tr-header">
          <span className="tr-label-icon">✦</span>
          <span className="tr-label-text cn-title" title={modelTitle}>
            {modelTitle}
          </span>
          {status === "completed" && (
            <NodeCardDotsMenu
              text={content}
              filenamePrefix={t("canvas.text.aiReply")}
            />
          )}
        </div>

        <div className="tr-body">
          {status === "generating" && (
            <div className="tr-generating nowheel">
              <GenerationBrandLoader />
              <span className="tr-generating-text">
                {screenplayMode ? t("canvas.text.genScriptReply") : t("canvas.common.generating")}
              </span>
              {data.onStopGeneration && (
                <GenerationStopButton onStop={() => data.onStopGeneration(id)} />
              )}
            </div>
          )}

          {status === "completed" && screenplayLoading && (
            <div className="tr-screenplay-loading nowheel">
              <div className="generating-dots" aria-hidden>
                <span /><span /><span />
              </div>
              <span className="tr-generating-text">{t("canvas.text.organizing")}</span>
            </div>
          )}

          {status === "completed" && !screenplayLoading && (
            <>
              {screenplayMode && outlineSynced ? (
                <div className="tr-screenplay-synced nodrag nowheel">
                  <p className="tr-screenplay-synced-title">{t("canvas.text.wroteOutline")}</p>
                  <p className="tr-screenplay-synced-hint cn-body">
                    {t("canvas.text.outlineSyncedDetail")}
                  </p>
                  <button
                    type="button"
                    className="tr-screenplay-view-src nodrag"
                    onClick={() => { if (!readOnly) setEditing((v) => !v) }}
                    disabled={readOnly}
                  >
                    {editing ? t("canvas.text.collapseSource") : t("canvas.text.viewLlm")}
                  </button>
                  {editing && (
                    <textarea
                      className="tr-edit-textarea tr-edit-textarea--synced cn-edit-match nodrag nowheel"
                      value={content}
                      onChange={handleContentChange}
                      onBlur={handleBlurEdit}
                    />
                  )}
                </div>
              ) : (
                <div className="cn-content-slot cn-content-slot--tall tr-content-slot">
                  {editing ? (
                    <textarea
                      className="tr-edit-textarea cn-edit-match nodrag nowheel"
                      value={content}
                      autoFocus
                      onDoubleClick={sp}
                      onChange={handleContentChange}
                      onBlur={handleBlurEdit}
                    />
                  ) : (
                    <div
                      className="tr-content-scroll scrollable-content nowheel cn-edit-match"
                      onDoubleClick={handleDoubleClick}
                      title={t("canvas.text.dblClickEdit")}
                    >
                      <div className="tr-content-text cn-body-lg">{content}</div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {status === "failed" && (
            <div className="tr-failed">
              <p className="tr-failed-title">{t("canvas.gen.failed")}</p>
              <p className="tr-failed-msg">{error || t("canvas.common.unknownError")}</p>
              <button type="button" className="tr-retry-btn nodrag" onClick={handleRetry}>
                {t("canvas.common.retry")}
              </button>
            </div>
          )}
        </div>

        {screenplayMode && status === "completed" && (
          <div className="tr-footer-bar nodrag">
            <button
              type="button"
              className="tr-screenplay-btn nodrag"
              disabled={readOnly || !content?.trim() || screenplayLoading}
              onClick={handleGenerateScreenplay}
            >
              {screenplayLoading
                ? t("canvas.text.organizing")
                : outlineSynced
                  ? t("canvas.text.reorganize")
                  : t("canvas.text.organizeOutline")}
            </button>
          </div>
        )}

        {status === "completed" && content?.trim() && importHandler && !screenplayMode && (
          <div className="tr-footer-bar nodrag">
            {importScriptError && (
              <p className="tr-screenplay-error">{importScriptError}</p>
            )}
            <button
              type="button"
              className="tr-screenplay-btn nodrag"
              disabled={readOnly || importingScriptTable || migratedToScriptTable}
              onClick={handleImportScriptTable}
            >
              {importingScriptTable
                ? t("canvas.text.importingScriptTable")
                : migratedToScriptTable
                  ? t("canvas.script.legacyReadonlyBanner")
                  : t("canvas.text.importScriptTable")}
            </button>
          </div>
        )}
        {screenplayError && (
          <p className="tr-screenplay-error nodrag">{screenplayError}</p>
        )}
      </div>
    </div>
  )
}
