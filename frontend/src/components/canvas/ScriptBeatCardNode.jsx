import { useCallback, useState } from "react"
import { useReactFlow } from "reactflow"
import {
  BEAT_CARD_NODE_TYPE,
  KEYFRAME_COUNT_WARN_THRESHOLD,
  applyBeatsToBeatCard,
  beatCardHasBeatPrompts,
  beatCardStoryboardReady,
} from "../../utils/canvas/scriptBeatCard"
import {
  asKeyframeArray,
  clampShotDuration,
  makeEmptyKeyframe,
  redistributeKeyframeTimes,
  syncRowFromKeyframes,
} from "../../utils/canvas/scriptTableKeyframes"
import { splitShotBeats } from "../../utils/canvas/scriptPromptApi"
import { useLocale } from "../../utils/locale"
import { useCanvasActions } from "./CanvasActionsContext"
import ScriptBeatTimeline from "./ScriptBeatTimeline"
import TextWorkflowEdgePlugs from "./TextWorkflowEdgePlugs"
import { handleNodeWheel } from "./canvasScrollHelpers"
import "./ScriptBeatCard.css"
import "./ScriptBeatTimeline.css"
import "./ScriptShotCard.css"

const sp = (e) => e.stopPropagation()

export default function ScriptBeatCardNode({ id, data, selected }) {
  const { t } = useLocale()
  const { getNode } = useReactFlow()
  const canvasActions = useCanvasActions()
  const readOnly = data.readOnly === true
  const keyframes = asKeyframeArray(data.keyframes)
  const [splitting, setSplitting] = useState(false)

  const scriptRef = data.scriptTableRef || {}
  const scriptTableId = scriptRef.nodeId
  const rowId = scriptRef.rowId

  const scriptNode = scriptTableId ? getNode(scriptTableId) : null
  const row = scriptNode?.data?.rows?.find((r) => r.id === rowId)
  const castLibrary = scriptNode?.data?.castLibrary || []
  const sceneLibrary = scriptNode?.data?.sceneLibrary || []
  const shotPrompt = (row?.prompt || row?.description || "").trim()
  const storyboardReady = beatCardStoryboardReady(data)
  const hasBeatPrompts = beatCardHasBeatPrompts(data)
  const generating = data.status === "generating" || splitting

  const patchCard = useCallback(
    (patch) => {
      if (readOnly) return
      data.onUpdate?.(id, patch)
    },
    [data, id, readOnly]
  )

  const updateKeyframe = useCallback(
    (keyframeId, patch) => {
      const next = (data.keyframes || []).map((kf) =>
        kf.id === keyframeId ? { ...kf, ...patch } : kf
      )
      patchCard({ keyframes: next })
    },
    [data.keyframes, patchCard]
  )

  const handleAddKeyframe = useCallback(() => {
    const kfs = data.keyframes || []
    patchCard({
      keyframes: redistributeKeyframeTimes(
        syncRowFromKeyframes({
          ...data,
          duration: row?.duration,
          keyframes: [...kfs, makeEmptyKeyframe(kfs.length)],
        })
      ).keyframes,
    })
  }, [data, patchCard, row?.duration])

  const handleDeleteKeyframe = useCallback(
    (keyframeId) => {
      const kfs = (data.keyframes || []).filter((kf) => kf.id !== keyframeId)
      if (kfs.length === 0) return
      patchCard({
        keyframes: redistributeKeyframeTimes(
          syncRowFromKeyframes({
            ...data,
            duration: row?.duration,
            keyframes: kfs.map((kf, i) => ({ ...kf, index: i })),
          })
        ).keyframes,
      })
    },
    [data, patchCard, row?.duration]
  )

  const handleSplitBeats = useCallback(
    async (resplit = false) => {
      if (readOnly || !row || !shotPrompt) return
      if (!resplit && hasBeatPrompts) return
      setSplitting(true)
      try {
        const workRow = { ...row, duration: clampShotDuration(row.duration) }
        const res = await splitShotBeats(workRow, castLibrary, {
          useLlm: true,
          sceneLibrary,
        })
        if (res?.beats?.length) {
          const next = applyBeatsToBeatCard(data, res.beats)
          patchCard({
            keyframes: next.keyframes,
            beatsSplitAt: next.beatsSplitAt,
            beatsSplitSource: res.source,
            error: null,
            status: "idle",
          })
        } else {
          patchCard({ error: t("canvas.script.beatSplitRetry") })
        }
      } catch (err) {
        patchCard({ error: err?.message || t("canvas.script.beatSplitFail") })
      } finally {
        setSplitting(false)
      }
    },
    [readOnly, row, shotPrompt, hasBeatPrompts, castLibrary, sceneLibrary, data, patchCard, t]
  )

  const handleGenerateStoryboard = useCallback(async () => {
    if (readOnly || !scriptTableId || !rowId) return
    if (!hasBeatPrompts) {
      patchCard({ error: t("canvas.script.confirmBeatFirst") })
      return
    }
    await canvasActions?.runBeatCardRowGenerate?.(scriptTableId, rowId, {
      modelId: scriptNode?.data?.modelId,
    })
  }, [readOnly, scriptTableId, rowId, hasBeatPrompts, canvasActions, scriptNode, patchCard, t])

  const handleGenerateVideo = useCallback(async () => {
    if (readOnly || !scriptTableId || !rowId) return
    await canvasActions?.runScriptTableRowVideoGenerate?.(scriptTableId, rowId, {
      videoModelId: scriptNode?.data?.videoModelId,
      lane: "beat",
    })
  }, [readOnly, scriptTableId, rowId, canvasActions, scriptNode])

  const handleDeleteCard = useCallback(() => {
    if (readOnly || !scriptTableId || !rowId) return
    canvasActions?.unlinkBeatCard?.(scriptTableId, rowId, id)
    data.onDelete?.(id)
  }, [readOnly, scriptTableId, rowId, id, canvasActions, data])

  const beatCountWarn = keyframes.length > KEYFRAME_COUNT_WARN_THRESHOLD

  return (
    <div
      className={`sbc-root canvas-node-card${selected ? " selected" : ""}${readOnly ? " sbc-root--readonly" : ""}`}
      onWheel={handleNodeWheel}
    >
      <div className="sbc-head">
        <div>
          <p className="sbc-title cn-emphasis">
            {t("canvas.script.beatCardTitle", { n: data.shotNumber ?? row?.shotNumber ?? "?" })}
          </p>
          <p className="sbc-sub cn-muted">{t("canvas.script.beatCardSubtitle")}</p>
        </div>
        {!readOnly && (
          <button type="button" className="sbc-delete-btn nodrag" onClick={handleDeleteCard} onPointerDown={sp}>
            {t("canvas.common.delete")}
          </button>
        )}
      </div>

      {beatCountWarn && (
        <div className="sbc-warn-banner nodrag" onPointerDown={sp}>
          {t("canvas.script.beatCountWarn", { n: keyframes.length })}
        </div>
      )}

      {data.error && <p className="sbc-error nodrag">{data.error}</p>}

      <ScriptBeatTimeline
        row={row || { keyframes }}
        keyframes={keyframes}
        splitting={splitting}
        splitSource={data.beatsSplitSource}
        readOnly={readOnly}
        onUpdateBeatPrompt={(kfId, prompt) =>
          updateKeyframe(kfId, { prompt, description: prompt })
        }
        onUpdateBeatLabel={(kfId, label) => updateKeyframe(kfId, { label })}
        onDeleteKeyframe={handleDeleteKeyframe}
        onAddKeyframe={handleAddKeyframe}
      />

      <div className="st-shot-card-foot nodrag sbc-foot">
        <button
          type="button"
          className="st-shot-gen-beats"
          disabled={readOnly || generating || !shotPrompt}
          onClick={() => handleSplitBeats(false)}
          onPointerDown={sp}
        >
          {splitting ? t("canvas.script.splittingBeats") : t("canvas.script.splitBeat")}
        </button>
        <button
          type="button"
          className="st-shot-gen-storyboard"
          disabled={readOnly || generating || !shotPrompt || splitting || !hasBeatPrompts}
          onClick={handleGenerateStoryboard}
          onPointerDown={sp}
        >
          {data.status === "generating" && !splitting
            ? t("canvas.script.storyboardGenerating")
            : t("canvas.script.genStoryboard")}
        </button>
        <button
          type="button"
          className="st-shot-gen-video"
          disabled={readOnly || !storyboardReady || generating}
          onClick={handleGenerateVideo}
          onPointerDown={sp}
        >
          {t("canvas.script.genVideo")}
        </button>
      </div>

      <TextWorkflowEdgePlugs nodeId={id} nodeType={BEAT_CARD_NODE_TYPE} disabled={readOnly} selected={selected} />
    </div>
  )
}
