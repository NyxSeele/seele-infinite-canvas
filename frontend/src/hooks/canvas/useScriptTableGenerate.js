import { useCallback } from "react"
import { addEdge } from "reactflow"
import api from "../../services/api"
import { resolveReferenceUrlForApi } from "../../services/uploadImage"
import { stripMediaTicket } from "../../utils/mediaTicket"
import { getT } from "../../utils/locale"
import { normalizeCastLibrary } from "../../utils/canvas/castLibrary"
import {
  buildEntityThemeContext,
  characterCastLibrary,
  resolveCharacterRefsForRow,
  resolveSceneRefsForRow,
} from "../../utils/canvas/entityRefs"
import { useAssetStore } from "../../stores/assetStore"
import { getEffectiveQualityPresetId } from "../../utils/canvas/scriptTableNode"
import { appendDirectorFieldsToDescription } from "../../utils/canvas/shotDirectorFields"
import {
  BEAT_CARD_NODE_TYPE,
  beatCardStoryboardReady,
  syncBeatCardFromKeyframes,
} from "../../utils/canvas/scriptBeatCard"
import {
  asKeyframeArray,
  clampShotDuration,
  getLastKeyframeResult,
  getPreviousKeyframeInRow,
  keyframeApiText,
  keyframeGenerationApiText,
  keyframeGenerationText,
  keyframeText,
  rowDirectImageReady,
  rowStoryboardReady,
  scriptRowText,
  shotPromptText,
  syncRowFromKeyframes,
} from "../../utils/canvas/scriptTableKeyframes"
import { buildRefItem } from "../../components/canvas/videoReferenceHelpers"
import { buildShotPromptPackage } from "../../utils/canvas/scriptPromptPackage"
import { appendStyleReferenceToDescription } from "../../utils/canvas/styleReferenceFormat"
import {
  makeId,
  SCRIPT_TABLE_WIDTH,
  SCRIPT_TABLE_TO_IMAGE_GAP,
  SCRIPT_TABLE_ROW_Y_OFFSET,
  SCRIPT_TABLE_CHROME_Y,
  SCRIPT_KEYFRAME_Y_STEP,
  computeScriptTableGenX,
  computeScriptTableShotY,
  computeScriptTableGenPosition,
  sortScriptRows,
} from "../../utils/canvas/nodeHelpers"

const KEYFRAME_Y_STEP = SCRIPT_KEYFRAME_Y_STEP
const VIDEO_NODE_EXTRA_Y = 140

function newTraceId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID()
  }
  return `trace-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function resolveBeatCard(nodes, row) {
  if (!row?.beatCardNodeId) return null
  return nodes.find((n) => n.id === row.beatCardNodeId && n.type === BEAT_CARD_NODE_TYPE) || null
}

function beatCardKeyframes(nodes, row) {
  const card = resolveBeatCard(nodes, row)
  return asKeyframeArray(card?.data?.keyframes)
}

export function useScriptTableGenerate({ nodes, setNodes, setEdges, getNode, nodesRef, buildData, bumpZIndex }) {
  const patchScriptTableRow = useCallback((scriptTableNodeId, rowId, patch) => {
    setNodes((ns) =>
      ns.map((n) => {
        if (n.id !== scriptTableNodeId || n.type !== "script-table") return n
        const rows = (n.data.rows || []).map((r) => {
          if (r.id !== rowId) return r
          const merged = { ...r, ...patch }
          if (patch.directResultUrl !== undefined || patch.directStatus !== undefined) {
            merged.resultUrl = patch.directResultUrl ?? merged.directResultUrl ?? merged.resultUrl
            merged.status = patch.directStatus ?? merged.directStatus ?? merged.status
          }
          return syncRowFromKeyframes(merged)
        })
        return { ...n, data: { ...n.data, rows } }
      })
    )
  }, [setNodes])

  const patchBeatCard = useCallback((beatCardNodeId, patch) => {
    setNodes((ns) =>
      ns.map((n) => {
        if (n.id !== beatCardNodeId || n.type !== BEAT_CARD_NODE_TYPE) return n
        const nextData = syncBeatCardFromKeyframes({ ...n.data, ...patch })
        return { ...n, data: nextData }
      })
    )
  }, [setNodes])

  const patchBeatCardKeyframe = useCallback(
    (beatCardNodeId, keyframeId, patch) => {
      setNodes((ns) =>
        ns.map((n) => {
          if (n.id !== beatCardNodeId || n.type !== BEAT_CARD_NODE_TYPE) return n
          const keyframes = (n.data.keyframes || []).map((kf) =>
            kf.id === keyframeId ? { ...kf, ...patch } : kf
          )
          return { ...n, data: syncBeatCardFromKeyframes({ ...n.data, keyframes }) }
        })
      )
    },
    [setNodes]
  )

  const patchScriptTableKeyframe = useCallback(
    (scriptTableNodeId, rowId, keyframeId, patch) => {
      const scriptNode = nodesRef.current.find((n) => n.id === scriptTableNodeId)
      const row = scriptNode?.data?.rows?.find((r) => r.id === rowId)
      if (row?.beatCardNodeId) {
        patchBeatCardKeyframe(row.beatCardNodeId, keyframeId, patch)
        return
      }
      setNodes((ns) =>
        ns.map((n) => {
          if (n.id !== scriptTableNodeId || n.type !== "script-table") return n
          const rows = (n.data.rows || []).map((r) => {
            if (r.id !== rowId) return r
            const keyframes = (r.keyframes || []).map((kf) =>
              kf.id === keyframeId ? { ...kf, ...patch } : kf
            )
            return syncRowFromKeyframes({ ...r, keyframes })
          })
          return { ...n, data: { ...n.data, rows } }
        })
      )
    },
    [setNodes, nodesRef, patchBeatCardKeyframe]
  )

  const runScriptTableDirectImageGenerate = useCallback(
    async (scriptTableNodeId, rowId, options = {}) => {
      const scriptNode =
        nodesRef.current.find((n) => n.id === scriptTableNodeId) || getNode(scriptTableNodeId)
      if (!scriptNode || scriptNode.type !== "script-table") return false

      const rows = sortScriptRows(scriptNode.data.rows || [])
      const rowIndex = rows.findIndex((r) => r.id === rowId)
      const row = rows[rowIndex]
      if (!row) return false

      const modelId = options.modelId || scriptNode.data.modelId
      if (!modelId) {
        patchScriptTableRow(scriptTableNodeId, rowId, {
          directStatus: "failed",
          error: getT()("canvas.script.selectImageModel"),
        })
        return false
      }

      const rowPromptBase =
        options.descriptionOverride?.trim()
        || row.compiledPromptPackage?.apiDescription?.trim()
        || shotPromptText(row)
      const rowDesc = appendDirectorFieldsToDescription(rowPromptBase, row)
      if (!rowDesc) {
        patchScriptTableRow(scriptTableNodeId, rowId, {
          directStatus: "failed",
          error: getT()("canvas.script.fillPlotOrCell"),
        })
        return false
      }

      patchScriptTableRow(scriptTableNodeId, rowId, {
        directStatus: "generating",
        error: null,
        status: "generating",
      })

      try {
        const priorShots = rows.slice(0, rowIndex).map((r) => ({
          shot_number: r.shotNumber ?? 1,
          description: shotPromptText(r) || scriptRowText(r),
        }))

        const prevRow = rowIndex > 0 ? rows[rowIndex - 1] : null
        const visualContinuity = scriptNode.data.visualContinuity === true
        const continuityMode = scriptNode.data.continuityMode !== false
        const castLibrary = normalizeCastLibrary(scriptNode.data.castLibrary || [])
        const rowForCast = { ...row, prompt: rowDesc }
        const globalAssets = useAssetStore.getState().assets || []
        const sceneLibrary = scriptNode.data?.sceneLibrary || []
        const matchedCast = resolveCharacterRefsForRow(rowForCast, castLibrary, globalAssets)
        const matchedScenes = resolveSceneRefsForRow(rowForCast, sceneLibrary)
        const castContext = buildEntityThemeContext(
          rowForCast,
          castLibrary,
          sceneLibrary,
          globalAssets
        )

        const MAX_CHAR_REFS = 3
        const MAX_SCENE_REFS = 1
        let manualRefs = []
        const charRefs = matchedCast.map((c) => c.imageUrl).filter(Boolean).slice(0, MAX_CHAR_REFS)
        const sceneRefs = matchedScenes.map((s) => s.imageUrl).filter(Boolean).slice(0, MAX_SCENE_REFS)
        manualRefs = [...charRefs, ...sceneRefs]
        if (!manualRefs.length && castLibrary.length) {
          manualRefs = characterCastLibrary(castLibrary)
            .map((c) => c.imageUrl)
            .filter(Boolean)
            .slice(0, MAX_CHAR_REFS)
        }

        const traceId = newTraceId()
        const buildRes = await api.post("/api/prompt/build-shot", {
          description: rowDesc,
          model_id: modelId,
          global_style: "",
          quality_preset_id: getEffectiveQualityPresetId(row, scriptNode.data),
          theme_context: castContext || scriptNode.data.themeContext || "",
          prior_shots: priorShots,
          shot_number: row.shotNumber ?? rowIndex + 1,
          visual_continuity: visualContinuity,
          continuity_mode: continuityMode,
          has_previous_shot_image: Boolean(
            prevRow?.directResultUrl || getLastKeyframeResult(prevRow)
          ),
          has_manual_reference: manualRefs.length > 0,
          trace_id: traceId,
        })

        const {
          prompt,
          display_prompt: displayPrompt,
          negative_prompt: negativePrompt,
          use_visual_reference: useVisualReference,
          img2img_denoise: suggestedDenoise,
          visual_reference_note: visualReferenceNote,
          trace_id: traceIdFromApi,
        } = buildRes.data
        const sessionTraceId = traceIdFromApi || traceId

        if (!(prompt || "").trim()) {
          patchScriptTableRow(scriptTableNodeId, rowId, {
            directStatus: "failed",
            error: getT()("canvas.script.fillDesc"),
          })
          return false
        }

        let refUrls = manualRefs.map((u) => stripMediaTicket(u)).filter(Boolean)
        let img2imgDenoise = null
        if (refUrls.length > 0) {
          img2imgDenoise = suggestedDenoise ?? 0.55
        } else if (useVisualReference && prevRow) {
          const prevResult = prevRow.directResultUrl || getLastKeyframeResult(prevRow)
          if (prevResult) {
            refUrls = [stripMediaTicket(prevResult)]
            img2imgDenoise = suggestedDenoise ?? 0.7
          }
        }

        const resolvedRefs = []
        for (const rawUrl of refUrls) {
          try {
            resolvedRefs.push(await resolveReferenceUrlForApi(rawUrl))
          } catch (uploadErr) {
            patchScriptTableRow(scriptTableNodeId, rowId, {
              directStatus: "failed",
              error: uploadErr?.message || getT()("canvas.script.refUploadFail"),
            })
            return false
          }
        }
        const refUrl = resolvedRefs[0] || null

        let imageGenId = row.directImageGenNodeId
        const existingImageGen = imageGenId
          ? nodesRef.current.find((n) => n.id === imageGenId) || getNode(imageGenId)
          : null

        const uiPrompt = (displayPrompt || rowDesc).trim()
        const label = getT()("canvas.script.shotImage", {
          n: row.shotNumber ?? rowIndex + 1,
        })
        const imageGenPayload = {
          prompt: uiPrompt,
          generationPrompt: prompt,
          displayPrompt: uiPrompt,
          modelId,
          traceId: sessionTraceId,
          referenceImageUrl: refUrl,
          referenceImage: refUrl,
          referenceImages: resolvedRefs.length
            ? resolvedRefs.map((url, i) => ({
                nodeId: "",
                imageIndex: i,
                imageUrl: url,
                imageId: `script_direct_${rowId}_${i}`,
                label: i === 0 ? label : `${label} ref${i + 1}`,
              }))
            : [],
          reference_images: resolvedRefs.length ? resolvedRefs : undefined,
          count: 1,
          expectedCount: 1,
          builtPrompt: prompt,
          negativePrompt,
          img2imgDenoise: refUrl ? img2imgDenoise : null,
          scriptTableRef: {
            nodeId: scriptTableNodeId,
            rowId,
            lane: "direct",
          },
          pendingTrigger: Date.now(),
        }

        if (visualReferenceNote) {
          patchScriptTableRow(scriptTableNodeId, rowId, { continuityNote: visualReferenceNote })
        }

        if (!existingImageGen || existingImageGen.type !== "image-gen") {
          imageGenId = makeId("image-gen")
          const z = bumpZIndex()
          const newNode = {
            id: imageGenId,
            type: "image-gen",
            position: computeScriptTableGenPosition(scriptNode, rowIndex),
            zIndex: z,
            data: buildData({ label, zIndex: z, ...imageGenPayload }),
            style: { zIndex: z },
          }
          setNodes((ns) => [...ns, newNode])
          setEdges((es) =>
            addEdge(
              {
                id: `e-${scriptTableNodeId}-${imageGenId}-${Date.now()}`,
                source: scriptTableNodeId,
                target: imageGenId,
                sourceHandle: "src-right",
                targetHandle: "tgt",
                type: "ghost",
                animated: false,
              },
              es
            )
          )
        } else {
          setNodes((ns) =>
            ns.map((n) => (n.id === imageGenId ? { ...n, data: { ...n.data, ...imageGenPayload } } : n))
          )
        }

        patchScriptTableRow(scriptTableNodeId, rowId, {
          directStatus: "generating",
          directImageGenNodeId: imageGenId,
          directResultUrl: null,
          compiledPromptPackage: row.compiledPromptPackage || {
            apiDescription: rowPromptBase,
          },
        })
        return true
      } catch (err) {
        const detail = err.response?.data?.detail
        patchScriptTableRow(scriptTableNodeId, rowId, {
          directStatus: "failed",
          status: "failed",
          error: typeof detail === "string" ? detail : err.message || getT()("canvas.gen.failed"),
        })
        return false
      }
    },
    [
      getNode,
      patchScriptTableRow,
      bumpZIndex,
      buildData,
      setNodes,
      setEdges,
      nodesRef,
    ]
  )

  const runScriptTableKeyframeGenerate = useCallback(
    async (scriptTableNodeId, rowId, keyframeId, options = {}) => {
      const scriptNode =
        nodesRef.current.find((n) => n.id === scriptTableNodeId) || getNode(scriptTableNodeId)
      if (!scriptNode || scriptNode.type !== "script-table") return false

      const rows = sortScriptRows(scriptNode.data.rows || [])
      const rowIndex = rows.findIndex((r) => r.id === rowId)
      const row = rows[rowIndex]
      if (!row) return false

      const beatCard = resolveBeatCard(nodesRef.current, row)
      const beatCardId = beatCard?.id
      const keyframes = beatCard
        ? asKeyframeArray(beatCard.data?.keyframes)
        : asKeyframeArray(row.keyframes)
      const keyframe = keyframes.find((k) => k.id === keyframeId)
      if (!keyframe) return false

      const modelId = options.modelId || scriptNode.data.modelId
      if (!modelId) {
        patchScriptTableKeyframe(scriptTableNodeId, rowId, keyframeId, {
          status: "failed",
          error: getT()("canvas.script.selectImageModel"),
        })
        return false
      }

      const castForPkg = normalizeCastLibrary(scriptNode.data.castLibrary || [])
      const rowPromptBase =
        options.descriptionOverride?.trim()
        || keyframeApiText(keyframe)
        || keyframe.compiledPromptPackage?.apiDescription?.trim()
        || buildShotPromptPackage(row, castForPkg, { keyframeId: keyframe.id }).apiDescription
        || keyframeGenerationApiText(row, keyframe)
        || keyframeGenerationText(row, keyframe)
      const rowDesc = appendDirectorFieldsToDescription(rowPromptBase, row)
      if (!rowDesc) {
        patchScriptTableKeyframe(scriptTableNodeId, rowId, keyframeId, {
          status: "failed",
          error: getT()("canvas.script.fillPlotOrCell"),
        })
        return false
      }

      patchScriptTableKeyframe(scriptTableNodeId, rowId, keyframeId, {
        status: "generating",
        error: null,
      })
      if (beatCardId) patchBeatCard(beatCardId, { status: "generating", error: null })

      try {
        const priorShots = rows.slice(0, rowIndex).map((r) => ({
          shot_number: r.shotNumber ?? 1,
          description: scriptRowText(r) || shotPromptText(r),
        }))

        const prevRow = rowIndex > 0 ? rows[rowIndex - 1] : null
        const prevKfInRow = getPreviousKeyframeInRow({ keyframes }, keyframeId)
        const visualContinuity = scriptNode.data.visualContinuity === true
        const continuityMode = scriptNode.data.continuityMode !== false
        const castLibrary = normalizeCastLibrary(scriptNode.data.castLibrary || [])
        const rowForCast = {
          ...row,
          prompt: rowDesc,
          promptMentions: [...(row.promptMentions || []), ...(keyframe.promptMentions || [])],
        }
        const globalAssets = useAssetStore.getState().assets || []
        const sceneLibrary = scriptNode.data?.sceneLibrary || []
        const matchedCast = resolveCharacterRefsForRow(rowForCast, castLibrary, globalAssets)
        const matchedScenes = resolveSceneRefsForRow(rowForCast, sceneLibrary)
        const castContext = buildEntityThemeContext(
          rowForCast,
          castLibrary,
          sceneLibrary,
          globalAssets
        )

        const MAX_CHAR_REFS = 3
        const MAX_SCENE_REFS = 1
        let manualRefs = []
        const charRefs = matchedCast.map((c) => c.imageUrl).filter(Boolean).slice(0, MAX_CHAR_REFS)
        const sceneRefs = matchedScenes.map((s) => s.imageUrl).filter(Boolean).slice(0, MAX_SCENE_REFS)
        manualRefs = [...charRefs, ...sceneRefs]
        if (!manualRefs.length && castLibrary.length) {
          manualRefs = characterCastLibrary(castLibrary)
            .map((c) => c.imageUrl)
            .filter(Boolean)
            .slice(0, MAX_CHAR_REFS)
        }

        const traceId = newTraceId()
        const buildRes = await api.post("/api/prompt/build-shot", {
          description: rowDesc,
          model_id: modelId,
          global_style: "",
          quality_preset_id: getEffectiveQualityPresetId(row, scriptNode.data),
          theme_context: castContext || scriptNode.data.themeContext || "",
          prior_shots: priorShots,
          shot_number: row.shotNumber ?? rowIndex + 1,
          visual_continuity: visualContinuity,
          continuity_mode: continuityMode,
          has_previous_shot_image: Boolean(
            prevKfInRow?.resultUrl || getLastKeyframeResult(prevRow)
          ),
          has_manual_reference: manualRefs.length > 0,
          trace_id: traceId,
        })

        const {
          prompt,
          display_prompt: displayPrompt,
          negative_prompt: negativePrompt,
          use_visual_reference: useVisualReference,
          img2img_denoise: suggestedDenoise,
          visual_reference_note: visualReferenceNote,
          trace_id: traceIdFromApi,
        } = buildRes.data
        const sessionTraceId = traceIdFromApi || traceId

        if (!(prompt || "").trim()) {
          patchScriptTableKeyframe(scriptTableNodeId, rowId, keyframeId, {
            status: "failed",
            error: getT()("canvas.script.fillDesc"),
          })
          return false
        }

        let refUrls = manualRefs.map((u) => stripMediaTicket(u)).filter(Boolean)
        let img2imgDenoise = null
        if (refUrls.length > 0) {
          img2imgDenoise = suggestedDenoise ?? 0.55
        } else if (useVisualReference) {
          let continuityRef = null
          if (prevKfInRow?.resultUrl) {
            continuityRef = stripMediaTicket(prevKfInRow.resultUrl)
            img2imgDenoise = suggestedDenoise ?? 0.65
          } else if (prevRow) {
            const prevResult = getLastKeyframeResult(prevRow) || prevRow.directResultUrl
            if (prevResult) {
              continuityRef = stripMediaTicket(prevResult)
              img2imgDenoise = suggestedDenoise ?? 0.7
            }
          }
          if (continuityRef) refUrls = [continuityRef]
        }

        const resolvedRefs = []
        for (const rawUrl of refUrls) {
          try {
            resolvedRefs.push(await resolveReferenceUrlForApi(rawUrl))
          } catch (uploadErr) {
            patchScriptTableKeyframe(scriptTableNodeId, rowId, keyframeId, {
              status: "failed",
              error: uploadErr?.message || getT()("canvas.script.refUploadFail"),
            })
            return false
          }
        }
        const refUrl = resolvedRefs[0] || null

        const kfIndex = keyframes.findIndex((k) => k.id === keyframeId)
        let imageGenId = keyframe.imageGenNodeId
        const existingImageGen = imageGenId
          ? nodesRef.current.find((n) => n.id === imageGenId) || getNode(imageGenId)
          : null

        const uiPrompt = (displayPrompt || rowDesc).trim()
        const label = `${row.shotNumber ?? rowIndex + 1}-${keyframe.label || getT()("canvas.script.cellN", { n: kfIndex + 1 })}`
        const anchorNode = beatCard || scriptNode
        const imageGenPayload = {
          prompt: uiPrompt,
          generationPrompt: prompt,
          displayPrompt: uiPrompt,
          modelId,
          traceId: sessionTraceId,
          referenceImageUrl: refUrl,
          referenceImage: refUrl,
          referenceImages: resolvedRefs.length
            ? resolvedRefs.map((url, i) => ({
                nodeId: "",
                imageIndex: i,
                imageUrl: url,
                imageId: `script_ref_${rowId}_${keyframeId}_${i}`,
                label: i === 0 ? label : `${label} ref${i + 1}`,
              }))
            : [],
          reference_images: resolvedRefs.length ? resolvedRefs : undefined,
          count: 1,
          expectedCount: 1,
          builtPrompt: prompt,
          negativePrompt,
          img2imgDenoise: refUrl ? img2imgDenoise : null,
          scriptTableRef: {
            nodeId: scriptTableNodeId,
            rowId,
            keyframeId,
            lane: "beat",
            beatCardNodeId: beatCardId || null,
          },
          pendingTrigger: Date.now(),
        }

        if (visualReferenceNote) {
          patchScriptTableRow(scriptTableNodeId, rowId, { continuityNote: visualReferenceNote })
        }

        const baseY = beatCard
          ? beatCard.position.y + kfIndex * KEYFRAME_Y_STEP
          : computeScriptTableShotY(scriptNode, rowIndex) + kfIndex * KEYFRAME_Y_STEP
        const baseX = computeScriptTableGenX(scriptNode)

        if (!existingImageGen || existingImageGen.type !== "image-gen") {
          imageGenId = makeId("image-gen")
          const z = bumpZIndex()
          const newNode = {
            id: imageGenId,
            type: "image-gen",
            position: { x: baseX, y: baseY },
            zIndex: z,
            data: buildData({ label, zIndex: z, ...imageGenPayload }),
            style: { zIndex: z },
          }
          setNodes((ns) => [...ns, newNode])
          setEdges((es) =>
            addEdge(
              {
                id: `e-${anchorNode.id}-${imageGenId}-${Date.now()}`,
                source: anchorNode.id,
                target: imageGenId,
                sourceHandle: "src-right",
                targetHandle: "tgt",
                type: "ghost",
                animated: false,
              },
              es
            )
          )
        } else {
          setNodes((ns) =>
            ns.map((n) => (n.id === imageGenId ? { ...n, data: { ...n.data, ...imageGenPayload } } : n))
          )
        }

        patchScriptTableKeyframe(scriptTableNodeId, rowId, keyframeId, {
          status: "generating",
          builtPrompt: prompt,
          compiledPromptPackage: {
            apiDescription: rowPromptBase,
            fullText: options.compiledPackage?.fullText,
          },
          negativePrompt,
          imageGenNodeId: imageGenId,
          resultUrl: null,
        })
        return true
      } catch (err) {
        const detail = err.response?.data?.detail
        patchScriptTableKeyframe(scriptTableNodeId, rowId, keyframeId, {
          status: "failed",
          error: typeof detail === "string" ? detail : err.message || getT()("canvas.gen.failed"),
        })
        return false
      }
    },
    [
      getNode,
      patchScriptTableKeyframe,
      patchScriptTableRow,
      patchBeatCard,
      bumpZIndex,
      buildData,
      setNodes,
      setEdges,
      nodesRef,
    ]
  )

  const waitForScriptTableKeyframe = useCallback(
    (scriptTableNodeId, rowId, keyframeId, timeoutMs = 300000) => {
      return new Promise((resolve, reject) => {
        const start = Date.now()
        const tick = () => {
          const scriptNode = nodesRef.current.find((n) => n.id === scriptTableNodeId)
          const row = scriptNode?.data?.rows?.find((r) => r.id === rowId)
          const kfs = beatCardKeyframes(nodesRef.current, row) || row?.keyframes || []
          const kf = kfs.find((k) => k.id === keyframeId)
          if (!kf) {
            reject(new Error(getT()("canvas.script.cellNotFound")))
            return
          }
          if (kf.status === "completed" || kf.status === "failed") {
            resolve(kf)
            return
          }
          if (Date.now() - start > timeoutMs) {
            reject(new Error(getT()("canvas.gen.timeout")))
            return
          }
          setTimeout(tick, 1500)
        }
        tick()
      })
    },
    [nodesRef]
  )

  const runScriptTableRowGenerate = useCallback(
    async (scriptTableNodeId, rowId, options = {}) => {
      return runScriptTableDirectImageGenerate(scriptTableNodeId, rowId, options)
    },
    [runScriptTableDirectImageGenerate]
  )

  const runBeatCardRowGenerate = useCallback(
    async (scriptTableNodeId, rowId, options = {}) => {
      const scriptNode =
        nodesRef.current.find((n) => n.id === scriptTableNodeId) || getNode(scriptTableNodeId)
      if (!scriptNode) return false
      const row = (scriptNode.data.rows || []).find((r) => r.id === rowId)
      if (!row) return false
      const kfs = beatCardKeyframes(nodesRef.current, row)
      if (kfs.length === 0) return false

      const modelId = options.modelId || scriptNode.data.modelId
      if (!modelId) return false

      const continuityOn = scriptNode.data.continuityMode !== false
      for (const kf of kfs) {
        const started = await runScriptTableKeyframeGenerate(
          scriptTableNodeId,
          rowId,
          kf.id,
          { modelId }
        )
        if (!started) continue
        if (continuityOn) {
          try {
            const finished = await waitForScriptTableKeyframe(scriptTableNodeId, rowId, kf.id)
            if (finished.status === "failed") break
          } catch {
            break
          }
        }
      }
      return true
    },
    [getNode, runScriptTableKeyframeGenerate, waitForScriptTableKeyframe, nodesRef]
  )

  const runScriptTableDirectVideoGenerate = useCallback(
    async (scriptTableNodeId, rowId, options = {}) => {
      const scriptNode =
        nodesRef.current.find((n) => n.id === scriptTableNodeId) || getNode(scriptTableNodeId)
      if (!scriptNode || scriptNode.type !== "script-table") return false

      const rows = sortScriptRows(scriptNode.data.rows || [])
      const rowIndex = rows.findIndex((r) => r.id === rowId)
      const row = rows[rowIndex]
      if (!row) return false

      if (!rowDirectImageReady(row)) {
        patchScriptTableRow(scriptTableNodeId, rowId, {
          error: getT()("canvas.script.directImageFirst"),
        })
        return false
      }

      const videoModelId = options.videoModelId || scriptNode.data.videoModelId
      if (!videoModelId) {
        patchScriptTableRow(scriptTableNodeId, rowId, {
          error: getT()("canvas.script.selectVideoModel"),
        })
        return false
      }

      const durationSec = clampShotDuration(row.duration)
      const shotStyleRef = row.styleReference || null
      const videoPrompt = appendStyleReferenceToDescription(shotPromptText(row), shotStyleRef)

      const firstRef = buildRefItem({
        nodeId: row.directImageGenNodeId || scriptTableNodeId,
        imageIndex: 0,
        imageUrl: stripMediaTicket(row.directResultUrl),
        label: getT()("canvas.image.slotFirst"),
      })

      let videoGenId = row.directVideoGenNodeId
      const existingVideo = videoGenId
        ? nodesRef.current.find((n) => n.id === videoGenId) || getNode(videoGenId)
        : null

      const label = getT()("canvas.script.shotVideo", { n: row.shotNumber ?? rowIndex + 1 })
      const videoPayload = {
        label,
        prompt: videoPrompt,
        modelId: videoModelId,
        qualityPresetId: getEffectiveQualityPresetId(row, scriptNode.data),
        keyframes: { first: firstRef, last: firstRef },
        referenceMode: "keyframe",
        vidDuration: `${durationSec}s`,
        vidRatio: "16:9",
        vidQuality: "1080P",
        scriptTableRef: { nodeId: scriptTableNodeId, rowId, lane: "direct" },
        pendingTrigger: Date.now(),
      }

      const baseY = computeScriptTableShotY(scriptNode, rowIndex) + VIDEO_NODE_EXTRA_Y

      if (!existingVideo || existingVideo.type !== "video-gen") {
        videoGenId = makeId("video-gen")
        const z = bumpZIndex()
        const newNode = {
          id: videoGenId,
          type: "video-gen",
          position: {
            x: computeScriptTableGenX(scriptNode),
            y: baseY,
          },
          zIndex: z,
          data: buildData({ zIndex: z, ...videoPayload }),
          style: { zIndex: z },
        }
        setNodes((ns) => [...ns, newNode])
        setEdges((es) =>
          addEdge(
            {
              id: `e-${scriptTableNodeId}-${videoGenId}-${Date.now()}`,
              source: scriptTableNodeId,
              target: videoGenId,
              sourceHandle: "src-right",
              targetHandle: "tgt",
              type: "ghost",
              animated: false,
            },
            es
          )
        )
      } else {
        setNodes((ns) =>
          ns.map((n) => (n.id === videoGenId ? { ...n, data: { ...n.data, ...videoPayload } } : n))
        )
      }

      patchScriptTableRow(scriptTableNodeId, rowId, {
        directVideoGenNodeId: videoGenId,
        error: null,
      })
      return true
    },
    [getNode, patchScriptTableRow, bumpZIndex, buildData, setNodes, setEdges, nodesRef]
  )

  const runScriptTableRowVideoGenerate = useCallback(
    async (scriptTableNodeId, rowId, options = {}) => {
      if (options.lane === "direct" || options.direct) {
        return runScriptTableDirectVideoGenerate(scriptTableNodeId, rowId, options)
      }

      const scriptNode =
        nodesRef.current.find((n) => n.id === scriptTableNodeId) || getNode(scriptTableNodeId)
      if (!scriptNode || scriptNode.type !== "script-table") return false

      const rows = sortScriptRows(scriptNode.data.rows || [])
      const rowIndex = rows.findIndex((r) => r.id === rowId)
      const row = rows[rowIndex]
      if (!row) return false

      const beatCard = resolveBeatCard(nodesRef.current, row)
      const kfs = beatCard
        ? asKeyframeArray(beatCard.data?.keyframes)
        : asKeyframeArray(row.keyframes)
      const pseudoRow = { ...row, keyframes: kfs }

      if (!rowStoryboardReady(pseudoRow) && !beatCardStoryboardReady(beatCard?.data)) {
        patchScriptTableRow(scriptTableNodeId, rowId, {
          error: getT()("canvas.script.finishCellsFirst"),
        })
        return false
      }

      const videoModelId = options.videoModelId || scriptNode.data.videoModelId
      if (!videoModelId) {
        patchScriptTableRow(scriptTableNodeId, rowId, {
          error: getT()("canvas.script.selectVideoModel"),
        })
        return false
      }

      const firstKf = kfs[0]
      const lastKf = kfs[kfs.length - 1]
      const durationSec = clampShotDuration(row.duration)

      const beatLines = kfs
        .map((k) => {
          const text = keyframeApiText(k) || keyframeText(k)
          return text ? `${k.label || getT()("canvas.script.cell")}: ${text}` : ""
        })
        .filter(Boolean)
        .join("\n")
      const existingVideoId = beatCard?.data?.videoGenNodeId
      const existingVideo = existingVideoId
        ? nodesRef.current.find((n) => n.id === existingVideoId) || getNode(existingVideoId)
        : null
      const shotStyleRef =
        existingVideo?.data?.styleReference || row.styleReference || null
      const videoPrompt = appendStyleReferenceToDescription(
        [shotPromptText(row), beatLines].filter(Boolean).join("\n\n"),
        shotStyleRef
      )

      const firstRef = buildRefItem({
        nodeId: firstKf.imageGenNodeId || beatCard?.id || scriptTableNodeId,
        imageIndex: 0,
        imageUrl: stripMediaTicket(firstKf.resultUrl),
        label: firstKf.label || getT()("canvas.image.slotFirst"),
      })
      const lastRef = buildRefItem({
        nodeId: lastKf.imageGenNodeId || beatCard?.id || scriptTableNodeId,
        imageIndex: 0,
        imageUrl: stripMediaTicket(lastKf.resultUrl),
        label: lastKf.label || getT()("canvas.image.slotLast"),
      })

      let videoGenId = beatCard?.data?.videoGenNodeId
      const label = getT()("canvas.script.shotVideo", { n: row.shotNumber ?? rowIndex + 1 })
      const videoPayload = {
        label,
        prompt: videoPrompt,
        modelId: videoModelId,
        qualityPresetId: getEffectiveQualityPresetId(row, scriptNode.data),
        keyframes: { first: firstRef, last: lastRef },
        referenceMode: "keyframe",
        vidDuration: `${durationSec}s`,
        vidRatio: "16:9",
        vidQuality: "1080P",
        scriptTableRef: {
          nodeId: scriptTableNodeId,
          rowId,
          lane: "beat",
          beatCardNodeId: beatCard?.id || null,
        },
        pendingTrigger: Date.now(),
      }

      const anchorNode = beatCard || scriptNode
      const baseY = beatCard
        ? beatCard.position.y + Math.max(0, kfs.length - 1) * KEYFRAME_Y_STEP + VIDEO_NODE_EXTRA_Y
        : computeScriptTableShotY(scriptNode, rowIndex)
          + Math.max(0, kfs.length - 1) * KEYFRAME_Y_STEP
          + VIDEO_NODE_EXTRA_Y
      const baseX = computeScriptTableGenX(scriptNode)

      if (!existingVideo || existingVideo.type !== "video-gen") {
        videoGenId = makeId("video-gen")
        const z = bumpZIndex()
        const newNode = {
          id: videoGenId,
          type: "video-gen",
          position: { x: baseX, y: baseY },
          zIndex: z,
          data: buildData({ zIndex: z, ...videoPayload }),
          style: { zIndex: z },
        }
        setNodes((ns) => [...ns, newNode])
        setEdges((es) =>
          addEdge(
            {
              id: `e-${anchorNode.id}-${videoGenId}-${Date.now()}`,
              source: anchorNode.id,
              target: videoGenId,
              sourceHandle: "src-right",
              targetHandle: "tgt",
              type: "ghost",
              animated: false,
            },
            es
          )
        )
      } else {
        setNodes((ns) =>
          ns.map((n) => (n.id === videoGenId ? { ...n, data: { ...n.data, ...videoPayload } } : n))
        )
      }

      if (beatCard) {
        patchBeatCard(beatCard.id, { videoGenNodeId: videoGenId, error: null })
      } else {
        patchScriptTableRow(scriptTableNodeId, rowId, { videoGenNodeId: videoGenId, error: null })
      }
      return true
    },
    [
      getNode,
      patchScriptTableRow,
      patchBeatCard,
      bumpZIndex,
      buildData,
      setNodes,
      setEdges,
      nodesRef,
      runScriptTableDirectVideoGenerate,
    ]
  )

  const runScriptTableGenerateAll = useCallback(
    async (scriptTableNodeId, options = {}) => {
      const scriptNode =
        nodesRef.current.find((n) => n.id === scriptTableNodeId) || getNode(scriptTableNodeId)
      if (!scriptNode || scriptNode.type !== "script-table") return

      const modelId = options.modelId || scriptNode.data.modelId
      if (!modelId) return

      const rows = sortScriptRows(scriptNode.data.rows || []).filter((r) => shotPromptText(r))
      if (rows.length === 0) return

      if (modelId !== scriptNode.data.modelId) {
        setNodes((ns) =>
          ns.map((n) =>
            n.id === scriptTableNodeId ? { ...n, data: { ...n.data, modelId } } : n
          )
        )
      }

      const continuityOn = scriptNode.data.continuityMode !== false
      for (const row of rows) {
        const started = await runScriptTableDirectImageGenerate(scriptTableNodeId, row.id, {
          modelId,
        })
        if (!started) continue
        if (continuityOn) {
          await new Promise((r) => setTimeout(r, 2000))
        }
      }
    },
    [getNode, runScriptTableDirectImageGenerate, setNodes, nodesRef]
  )

  return {
    patchScriptTableRow,
    patchScriptTableKeyframe,
    patchBeatCard,
    patchBeatCardKeyframe,
    runScriptTableRowGenerate,
    runScriptTableDirectImageGenerate,
    runScriptTableDirectVideoGenerate,
    runBeatCardRowGenerate,
    runScriptTableKeyframeGenerate,
    runScriptTableGenerateAll,
    runScriptTableRowVideoGenerate,
  }
}
