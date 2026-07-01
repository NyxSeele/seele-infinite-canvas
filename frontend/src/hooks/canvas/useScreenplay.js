import { useCallback, useEffect } from "react"
import { addEdge } from "reactflow"
import api from "../../services/api"
import {
  makeId,
  NODE_WIDTHS_MAP,
  SHOT_SCRIPT_NODE_OFFSET_X,
} from "../../utils/canvas/nodeHelpers"
import { normalizeRowsToTargetDuration } from "../../utils/canvas/scriptDurationNormalize"
import {
  findScriptTableForOutline,
  segmentsToScriptPayload,
} from "../../utils/canvas/scriptTableSegments"
import { findUpstreamTargetDuration } from "../../utils/canvas/videoDurationIntent"
import { getT } from "../../utils/locale"

const OUTLINE_TO_SCRIPT_OFFSET_X = SHOT_SCRIPT_NODE_OFFSET_X

function applyDurationNormalize(rows, target, existingWarning) {
  if (!target) return { rows, durationWarning: existingWarning || null }
  const normalized = normalizeRowsToTargetDuration(rows, target)
  let durationWarning = existingWarning || null
  if (normalized.warning) {
    durationWarning = durationWarning
      ? `${durationWarning} ${normalized.warning}`
      : normalized.warning
  }
  return { rows: normalized.rows, durationWarning }
}

export function useScreenplay({
  setNodes,
  setEdges,
  getNode,
  buildData,
  bumpZIndex,
  nodesRef,
  edgesRef,
  patchNodeData,
  screenplayHandlersRef,
  readOnlyRef,
}) {
  /** @deprecated */
  const onGenerateScreenplay = useCallback(async () => {}, [])

  const fetchSegmentsFromOutline = useCallback(
    async (outlineNode, outlineText) => {
      const outlineNodeId = outlineNode.id
      let outline = (outlineText || "").trim()
      if (
        !outline
        && Array.isArray(outlineNode.data?.scenes)
        && outlineNode.data.scenes.length > 0
      ) {
        outline = JSON.stringify({
          title: outlineNode.data.title || "",
          scenes: outlineNode.data.scenes,
          target_video_duration_sec: outlineNode.data.targetVideoDurationSec ?? undefined,
          source_idea: outlineNode.data.sourceIdea || "",
        })
      }
      if (!outline) {
        outline = (outlineNode.data?.outline || "").trim()
      }
      if (!outline) {
        throw new Error(getT()("canvas.outline.fillFirst"))
      }

      const targetDuration =
        outlineNode.data?.targetVideoDurationSec
        ?? findUpstreamTargetDuration(
          nodesRef.current,
          edgesRef?.current || [],
          outlineNodeId
        )

      const payload = {
        outline,
        target_duration_sec: targetDuration ?? undefined,
      }
      const res = await api.post("/api/screenplay/generate-shots", payload)
      const rawSegments = res.data?.segments
      if (!Array.isArray(rawSegments) || rawSegments.length === 0) {
        throw new Error(getT()("canvas.outline.noShotData"))
      }

      let { segments, rows } = segmentsToScriptPayload(rawSegments)
      const durationResult = applyDurationNormalize(
        rows,
        targetDuration,
        res.data?.duration_warning || null
      )
      rows = durationResult.rows

      return {
        segments,
        rows,
        targetDuration:
          res.data?.target_video_duration_sec ?? targetDuration ?? null,
        durationWarning: durationResult.durationWarning,
        truncated: res.data?.truncated === true,
      }
    },
    [nodesRef, edgesRef]
  )

  const linkOutlineToScriptTable = useCallback(
    (outlineNodeId, scriptTableId, replaceIntermediateShotScript = false) => {
      setEdges((es) => {
        const dropTargets = new Set(
          nodesRef.current
            .filter((n) => n.type === "shot-script" || n.type === "script-table")
            .map((n) => n.id)
        )
        let next = es.filter(
          (e) => !(e.source === outlineNodeId && dropTargets.has(e.target))
        )
        next = addEdge(
          {
            id: `e-${outlineNodeId}-${scriptTableId}-${Date.now()}`,
            source: outlineNodeId,
            sourceHandle: "src-right",
            target: scriptTableId,
            targetHandle: "tgt",
            type: "ghost",
            animated: false,
          },
          next
        )
        return next
      })

      if (replaceIntermediateShotScript) {
        setEdges((es) =>
          es.filter((e) => {
            const src = nodesRef.current.find((n) => n.id === e.source)
            return src?.type !== "shot-script"
          })
        )
      }

      patchNodeData(outlineNodeId, { linkedScriptTableId: scriptTableId })
    },
    [setEdges, patchNodeData, nodesRef]
  )

  /** P0/P1：大纲 → 分镜表（新建或就地更新） */
  const onGenerateScriptTable = useCallback(
    async (outlineNodeId, outlineText) => {
      if (readOnlyRef?.current === true) return
      const outlineNode =
        nodesRef.current.find((n) => n.id === outlineNodeId) || getNode(outlineNodeId)
      if (!outlineNode || outlineNode.type !== "outline") return

      let targetId = findScriptTableForOutline(
        outlineNodeId,
        nodesRef.current,
        edgesRef?.current || []
      )

      if (targetId) {
        patchNodeData(targetId, {
          loading: true,
          error: null,
          generatingFromOutline: true,
        })
      } else {
        targetId = makeId("script-table")
        const z = bumpZIndex()
        const position = {
          x: outlineNode.position.x + OUTLINE_TO_SCRIPT_OFFSET_X,
          y: outlineNode.position.y,
        }
        setNodes((ns) => [
          ...ns,
          {
            id: targetId,
            type: "script-table",
            position,
            width: NODE_WIDTHS_MAP["script-table"],
            zIndex: z,
            data: buildData({
              label: getT()("canvas.node.labelScriptTable"),
              rows: [],
              segments: [],
              loading: true,
              error: null,
              continuityMode: true,
              visualContinuity: false,
              sourceOutlineId: outlineNodeId,
              targetVideoDurationSec: null,
              uiMode: "simple",
              zIndex: z,
            }),
            style: { zIndex: z, width: NODE_WIDTHS_MAP["script-table"] },
          },
        ])
        linkOutlineToScriptTable(outlineNodeId, targetId)
      }

      try {
        const result = await fetchSegmentsFromOutline(outlineNode, outlineText)
        const prev =
          nodesRef.current.find((n) => n.id === targetId)
          || getNode(targetId)

        patchNodeData(targetId, {
          loading: false,
          generatingFromOutline: false,
          segments: result.segments,
          rows: result.rows,
          error: null,
          truncated: result.truncated,
          targetVideoDurationSec: result.targetDuration,
          durationWarning: result.durationWarning,
          sourceOutlineId: outlineNodeId,
          castLibrary: prev?.data?.castLibrary,
          modelId: prev?.data?.modelId,
          videoModelId: prev?.data?.videoModelId,
          continuityMode: prev?.data?.continuityMode ?? true,
          visualContinuity: prev?.data?.visualContinuity ?? false,
          uiMode: prev?.data?.uiMode || "simple",
        })

        linkOutlineToScriptTable(outlineNodeId, targetId)

        return result
      } catch (err) {
        console.error("generate script-table error:", err)
        const msg =
          err.response?.data?.detail || err.message || getT()("canvas.outline.shotFail")
        const detail = typeof msg === "string" ? msg : getT()("canvas.outline.shotFail")
        patchNodeData(targetId, {
          loading: false,
          generatingFromOutline: false,
          error: detail,
        })
        throw err
      }
    },
    [
      getNode,
      bumpZIndex,
      buildData,
      setNodes,
      patchNodeData,
      nodesRef,
      edgesRef,
      fetchSegmentsFromOutline,
      linkOutlineToScriptTable,
      readOnlyRef,
    ]
  )

  /** 兼容旧大纲 handler 名称 */
  const onGenerateShotScript = onGenerateScriptTable

  const createOrUpdateScriptTableFromSegments = useCallback(
    (sourceNode, segments, meta = {}) => {
      if (!sourceNode || !Array.isArray(segments) || segments.length === 0) return null

      let { segments: normSegs, rows } = segmentsToScriptPayload(segments)
      const target =
        meta.targetVideoDurationSec
        ?? findUpstreamTargetDuration(
          nodesRef.current,
          edgesRef?.current || [],
          sourceNode.id
        )

      const durationResult = applyDurationNormalize(
        rows,
        target,
        meta.durationWarning || null
      )
      rows = durationResult.rows

      let existingId =
        sourceNode.type === "script-table"
          ? sourceNode.id
          : null

      if (!existingId && sourceNode.type === "shot-script") {
        const edge = (edgesRef?.current || []).find((e) => e.source === sourceNode.id)
        const linked = nodesRef.current.find((n) => n.id === edge?.target)
        if (linked?.type === "script-table") existingId = linked.id
      }

      if (!existingId) {
        existingId = findScriptTableForOutline(
          sourceNode.data?.sourceOutlineId || sourceNode.id,
          nodesRef.current,
          edgesRef?.current || []
        )
      }

      if (existingId && sourceNode.type !== "script-table") {
        const prev = getNode(existingId)
        patchNodeData(existingId, {
          segments: normSegs,
          rows,
          targetVideoDurationSec: target ?? null,
          durationWarning: durationResult.durationWarning,
          truncated: meta.truncated === true,
          error: null,
        })
        return existingId
      }

      if (sourceNode.type === "script-table") {
        patchNodeData(sourceNode.id, {
          segments: normSegs,
          rows,
          targetVideoDurationSec: target ?? null,
          durationWarning: durationResult.durationWarning,
          truncated: meta.truncated === true,
          error: null,
        })
        return sourceNode.id
      }

      const scriptId = `script-table-${Date.now()}`
      const z = bumpZIndex()
      const position = {
        x: sourceNode.position.x,
        y: sourceNode.position.y + 480,
      }

      setNodes((ns) => [
        ...ns,
        {
          id: scriptId,
          type: "script-table",
          position,
          zIndex: z,
          data: buildData({
            label: getT()("canvas.node.labelScriptTable"),
            rows,
            segments: normSegs,
            continuityMode: true,
            visualContinuity: false,
            migratedFromShotScript: sourceNode.id,
            targetVideoDurationSec: target ?? null,
            durationWarning: durationResult.durationWarning,
            truncated: meta.truncated === true,
            uiMode: "simple",
            zIndex: z,
          }),
          style: { zIndex: z },
        },
      ])
      setEdges((es) =>
        addEdge(
          {
            id: `e-${sourceNode.id}-${scriptId}-${Date.now()}`,
            source: sourceNode.id,
            sourceHandle: "src-right",
            target: scriptId,
            targetHandle: "tgt",
            type: "ghost",
            animated: false,
          },
          es
        )
      )

      if (sourceNode.type === "shot-script" && sourceNode.data?.sourceOutlineId) {
        linkOutlineToScriptTable(
          sourceNode.data.sourceOutlineId,
          scriptId,
          true
        )
      }

      patchNodeData(sourceNode.id, {
        legacyReadOnly: true,
        migratedToScriptTableId: scriptId,
      })

      return scriptId
    },
    [
      getNode,
      bumpZIndex,
      buildData,
      setNodes,
      setEdges,
      patchNodeData,
      nodesRef,
      edgesRef,
      linkOutlineToScriptTable,
    ]
  )

  /** P2：旧分镜提示词卡 → 迁移到分镜表 */
  const onImportScriptTable = useCallback(
    (shotScriptNodeId) => {
      if (readOnlyRef?.current === true) return
      const shotScript =
        nodesRef.current.find((n) => n.id === shotScriptNodeId)
        || getNode(shotScriptNodeId)
      if (!shotScript || shotScript.type !== "shot-script") return

      const segments = shotScript.data?.segments
      if (!Array.isArray(segments) || segments.length === 0) return

      if (shotScript.data?.migratedToScriptTableId) {
        const existing = getNode(shotScript.data.migratedToScriptTableId)
        if (existing?.type === "script-table") return existing.id
      }

      return createOrUpdateScriptTableFromSegments(shotScript, segments, {
        targetVideoDurationSec: shotScript.data?.targetVideoDurationSec,
        durationWarning: shotScript.data?.durationWarning,
        truncated: shotScript.data?.truncated,
      })
    },
    [getNode, nodesRef, createOrUpdateScriptTableFromSegments, readOnlyRef]
  )

  const onMigrateShotScript = onImportScriptTable

  useEffect(() => {
    screenplayHandlersRef.current = {
      onGenerateScreenplay,
      onGenerateShotScript,
      onGenerateScriptTable,
      onImportScriptTable,
      onMigrateShotScript,
    }
  }, [
    onGenerateScreenplay,
    onGenerateShotScript,
    onGenerateScriptTable,
    onImportScriptTable,
    onMigrateShotScript,
    screenplayHandlersRef,
  ])

  return {
    screenplayHandlersRef,
    onGenerateScreenplay,
    onGenerateShotScript,
    onGenerateScriptTable,
    onImportScriptTable,
    onMigrateShotScript,
  }
}
