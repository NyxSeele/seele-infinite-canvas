import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useReactFlow } from "reactflow"
import { useVirtualizer } from "@tanstack/react-virtual"
import { createPortal } from "react-dom"
import { useModelStore, useCanvasStore } from "../../stores"
import { uploadImageFile } from "../../services/uploadImage"
import { useLocale } from "../../utils/locale"
import { scriptTableToExportText } from "../../utils/canvas/cardExportText"
import NodeCardDotsMenu from "./NodeCardDotsMenu"
import ExportProjectModal from "./ExportProjectModal"
import { normalizeCastLibrary } from "../../utils/canvas/castLibrary"
import { normalizeSceneLibrary } from "../../utils/canvas/sceneLibrary"
import { applyCastLibraryAutoLink } from "../../utils/canvas/castLibrarySync"
import {
  stripCastImagesFromCompositionRefs,
  stripRemovedCastFromRows,
} from "../../utils/canvas/castLibrary"
import { BEAT_CARD_NODE_TYPE } from "../../utils/canvas/scriptBeatCard"
import {
  normalizeScriptRow,
  normalizeScriptRows,
  applyBeatsToRow,
  clampShotDuration,
  MAX_SHOT_DURATION,
  rowHasBeatPrompts,
  rowHasGeneratableContent,
  syncRowFromKeyframes,
  syncRowKeyframesToDuration,
  redistributeKeyframeTimes,
} from "../../utils/canvas/scriptTableKeyframes"
import ScriptShotCard from "./ScriptShotCard"
import CanvasModelDropup from "./CanvasModelDropup"
import ScriptSegmentHeader from "./ScriptSegmentHeader"
import NodeLoadingState from "./NodeLoadingState"
import TextWorkflowEdgePlugs from "./TextWorkflowEdgePlugs"
import {
  buildGroupedShotList,
  normalizeScriptSegments,
  patchSegmentInList,
  resolveScriptTableSegments,
} from "../../utils/canvas/scriptTableSegments"
import { formatDurationSec } from "../../utils/canvas/videoDurationIntent"
import {
  SCRIPT_QUALITY_PRESETS,
  applyQualityPresetToRow,
  withDefaultQualityPresetRows,
} from "../../utils/canvas/scriptQualityPresets"
import {
  buildLocalPromptPackage,
  expandShotPromptPackage,
  normalizePromptPackage,
  splitShotBeats,
} from "../../utils/canvas/scriptPromptApi"
import { touchLibraryById } from "../../utils/canvas/libraryUsage"
import ScriptShotPreviewModal from "./ScriptShotPreviewModal"
import { useCanvasActions, useReferenceSelect } from "./CanvasActionsContext"
import ScriptCastLibrary from "./ScriptCastLibrary"
import ScriptSceneLibrary from "./ScriptSceneLibrary"
import MediaLightbox from "./MediaLightbox"
import { useBlockCtrlWheel, handleNodeWheel } from "./canvasScrollHelpers"
import "./CanvasShared.css"
import "./canvasNodeLayout.css"
import "./canvasTypography.css"
import "./ScriptTableNode.css"
import "./NodeBanner.css"
import "./ScriptKeyframeCard.css"
import "./ScriptShotCard.css"
import "./ScriptBeatTimeline.css"

const SHOT_REORDER_MIME = "application/x-st-shot-reorder"

const ImageModelIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <rect x="1.5" y="2.5" width="10" height="8" rx="1.2" stroke="currentColor" strokeWidth="1.1"/>
    <circle cx="4.5" cy="5.5" r="1.2" fill="currentColor"/>
    <path d="M2 9.5l2.5-2 2 1.5 2-2.5 2.5 3" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/>
  </svg>
)

const VideoModelIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <rect x="1" y="3" width="7.5" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.1"/>
    <path d="M8.5 5.5l3.5-2v7l-3.5-2v-3z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/>
  </svg>
)

const PresetIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <rect x="1" y="2" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.1"/>
    <rect x="7" y="2" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.1"/>
    <rect x="1" y="7" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.1"/>
    <rect x="7" y="7" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.1"/>
  </svg>
)

function ProjectSettingsChevron({ open }) {
  return (
    <svg
      className="st-project-settings-chevron"
      width="10"
      height="10"
      viewBox="0 0 10 10"
      aria-hidden
    >
      {open ? (
        <path d="M2 6.5 L5 3.5 L8 6.5" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <path d="M2 3.5 L5 6.5 L8 3.5" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  )
}

function deferNodePatch(updateData, patch) {
  queueMicrotask(() => updateData(patch))
}

function makeRowId() {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function makeEmptyScriptRow(shotNumber = 1) {
  const duration = 8
  return normalizeScriptRow(
    applyQualityPresetToRow(
      {
        id: makeRowId(),
        shotNumber,
        duration,
        camera: "",
        movement: "",
        lighting: "",
        composition: "",
        colorGrade: "",
        lens: "",
        performance: "",
        soundDesign: "",
        soundNote: "",
        atmosphereNote: "",
        qualityPresetId: "",
        prompt: "",
        description: "",
        promptMentions: [],
        keyframes: [],
        beatCardNodeId: null,
        directImageGenNodeId: null,
        directResultUrl: null,
        directStatus: "idle",
        directVideoGenNodeId: null,
        status: "idle",
        error: null,
      },
      "auto"
    )
  )
}

export default function ScriptTableNode({ id, data, selected }) {
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)
  const wrapperRef = useRef(null)
  const shotListRef = useRef(null)
  useBlockCtrlWheel(wrapperRef)
  const readOnly = data.readOnly === true
  const canvasActions = useCanvasActions()
  const { getNode } = useReactFlow()
  const imageModels = useModelStore((s) => s.imageModels)
  const videoModels = useModelStore((s) => s.videoModels)
  const initialRows =
    Array.isArray(data.rows) && data.rows.length > 0
      ? data.rows
      : [makeEmptyScriptRow(1)]
  const [rows, setRows] = useState(() =>
    withDefaultQualityPresetRows(normalizeScriptRows(initialRows))
  )
  const [segments, setSegments] = useState(() =>
    resolveScriptTableSegments(initialRows, data.segments)
  )
  const [castLibrary, setCastLibrary] = useState(() =>
    normalizeCastLibrary(data.castLibrary || [], { requireImage: false })
  )
  const [sceneLibrary, setSceneLibrary] = useState(() =>
    normalizeSceneLibrary(data.sceneLibrary || [], { requireImage: false })
  )
  const [continuityMode, setContinuityMode] = useState(data.continuityMode !== false)
  const [visualContinuity, setVisualContinuity] = useState(data.visualContinuity === true)
  const [modelId, setModelId] = useState(data.modelId || "")
  const [batchRunning, setBatchRunning] = useState(false)
  const [lightboxUrl, setLightboxUrl] = useState(null)
  const [qualityPresetId, setQualityPresetId] = useState("auto")
  const [previewState, setPreviewState] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [projectSettingsOpen, setProjectSettingsOpen] = useState(false)
  const [dragRowId, setDragRowId] = useState(null)
  const [dragOverRowId, setDragOverRowId] = useState(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [continuityInfoOpen, setContinuityInfoOpen] = useState(false)
  const [visualInfoOpen, setVisualInfoOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [splittingRowId, setSplittingRowId] = useState(null)
  const [videoModelId, setVideoModelId] = useState(data.videoModelId || "")
  const refSelect = useReferenceSelect()

  useEffect(() => {
    if (Array.isArray(data.rows)) {
      setRows(normalizeScriptRows(data.rows))
      if (Array.isArray(data.segments)) {
        setSegments(normalizeScriptSegments(data.segments))
      } else {
        setSegments(resolveScriptTableSegments(data.rows, []))
      }
    }
  }, [data.rows, data.segments])

  const tableLoading = data.loading === true

  useEffect(() => {
    if (Array.isArray(data.castLibrary)) {
      setCastLibrary(normalizeCastLibrary(data.castLibrary, { requireImage: false }))
    }
  }, [data.castLibrary])

  useEffect(() => {
    if (Array.isArray(data.sceneLibrary)) {
      setSceneLibrary(normalizeSceneLibrary(data.sceneLibrary, { requireImage: false }))
    }
  }, [data.sceneLibrary])

  const updateData = useCallback(
    (patch) => {
      if (readOnly) return
      if (data.onUpdate) data.onUpdate(id, patch)
    },
    [id, data, readOnly]
  )

  const castStripInitRef = useRef(false)
  useEffect(() => {
    if (castStripInitRef.current) return
    castStripInitRef.current = true
    const lib = normalizeCastLibrary(data.castLibrary || [])
    if (!lib.length) return
    setRows((prev) => {
      const next = stripCastImagesFromCompositionRefs(prev, lib)
      if (JSON.stringify(prev) === JSON.stringify(next)) return prev
      deferNodePatch(updateData, { rows: next })
      return next
    })
  }, [data.castLibrary, updateData])

  useEffect(() => {
    if (imageModels.length > 0 && !modelId) {
      const defaultId = imageModels[0].id || ""
      if (defaultId) {
        setModelId(defaultId)
        updateData({ modelId: defaultId })
      }
    }
  }, [imageModels, modelId, updateData])

  useEffect(() => {
    if (videoModels.length > 0 && !videoModelId) {
      const defaultVid = videoModels[0].id || videoModels[0].display_name || ""
      if (defaultVid) {
        setVideoModelId(defaultVid)
        updateData({ videoModelId: defaultVid })
      }
    }
  }, [videoModels, videoModelId, updateData])

  const syncRows = useCallback(
    (nextRows, extra = {}) => {
      if (readOnly) return
      const normalized = normalizeScriptRows(nextRows)
      setRows(normalized)
      const nextSegments =
        extra.segments !== undefined
          ? normalizeScriptSegments(extra.segments)
          : segments
      if (extra.segments !== undefined) {
        setSegments(nextSegments)
      }
      updateData({ rows: normalized, segments: nextSegments, ...extra })
    },
    [updateData, segments, readOnly]
  )

  const updateSegment = useCallback(
    (segmentId, patch) => {
      if (readOnly) return
      setSegments((prev) => {
        const next = patchSegmentInList(prev, segmentId, patch)
        deferNodePatch(updateData, { segments: next })
        return next
      })
    },
    [updateData, readOnly]
  )

  const groupedItems = useMemo(
    () => buildGroupedShotList(rows, segments),
    [rows, segments]
  )

  const SHOT_LIST_VIRTUAL_THRESHOLD = 15
  const useVirtualShotList = groupedItems.length > SHOT_LIST_VIRTUAL_THRESHOLD

  const shotListVirtualizer = useVirtualizer({
    count: groupedItems.length,
    getScrollElement: () => shotListRef.current,
    estimateSize: (index) =>
      groupedItems[index]?.kind === "segment" ? 28 : 210,
    gap: 12,
    overscan: 3,
    enabled: useVirtualShotList,
  })

  const updateRow = useCallback(
    (rowId, patch) => {
      if (readOnly) return
      if (Object.prototype.hasOwnProperty.call(patch, "locationId") && patch.locationId) {
        setSceneLibrary((prev) => {
          const next = touchLibraryById(prev, patch.locationId)
          deferNodePatch(updateData, { sceneLibrary: next })
          return next
        })
      }
      setRows((prev) => {
        const next = prev.map((r) => {
          if (r.id !== rowId) return r
          let merged = { ...r, ...patch }
          if (
            Object.prototype.hasOwnProperty.call(patch, "duration")
            && (merged.keyframes || []).length > 0
          ) {
            merged = syncRowKeyframesToDuration(merged)
          }
          return syncRowFromKeyframes(merged)
        })
        deferNodePatch(updateData, { rows: next })
        return next
      })
    },
    [updateData, readOnly]
  )

  const updateKeyframe = useCallback(
    (rowId, keyframeId, patch) => {
      if (readOnly) return
      setRows((prev) => {
        const next = prev.map((r) => {
          if (r.id !== rowId) return r
          const keyframes = (r.keyframes || []).map((kf) =>
            kf.id === keyframeId ? { ...kf, ...patch } : kf
          )
          return syncRowFromKeyframes({ ...r, keyframes })
        })
        deferNodePatch(updateData, { rows: next })
        return next
      })
    },
    [updateData, readOnly]
  )

  const handleAddRow = useCallback(() => {
    const nextShot = rows.length > 0 ? Math.max(...rows.map((r) => r.shotNumber || 0)) + 1 : 1
    const lastRow = rows[rows.length - 1]
    const defaultSegmentId =
      lastRow?.segmentId || segments[segments.length - 1]?.id || undefined
    const row = applyQualityPresetToRow(
      { ...makeEmptyScriptRow(nextShot), segmentId: defaultSegmentId },
      qualityPresetId
    )
    syncRows([...rows, row])
  }, [rows, segments, syncRows, qualityPresetId])

  const handleDeleteRow = useCallback(
    (rowId) => {
      if (rows.length <= 1) return
      syncRows(rows.filter((r) => r.id !== rowId))
    },
    [rows, syncRows]
  )

  const handleAddKeyframe = useCallback(
    (rowId) => {
      setRows((prev) => {
        const next = prev.map((r) => {
          if (r.id !== rowId) return r
          const kfs = r.keyframes || []
          const idx = kfs.length
          return redistributeKeyframeTimes(
            syncRowFromKeyframes({
              ...r,
              keyframes: [...kfs, makeEmptyKeyframe(idx)],
            })
          )
        })
        deferNodePatch(updateData, { rows: next })
        return next
      })
    },
    [updateData]
  )

  const handleDeleteKeyframe = useCallback(
    (rowId, keyframeId) => {
      setRows((prev) => {
        const next = prev.map((r) => {
          if (r.id !== rowId) return r
          const kfs = (r.keyframes || []).filter((kf) => kf.id !== keyframeId)
          if (kfs.length === 0) return r
          return redistributeKeyframeTimes(
            syncRowFromKeyframes({
              ...r,
              keyframes: kfs.map((kf, i) => ({ ...kf, index: i })),
            })
          )
        })
        deferNodePatch(updateData, { rows: next })
        return next
      })
    },
    [updateData]
  )

  const handleCastLibraryChange = useCallback(
    (next) => {
      const normalized = normalizeCastLibrary(next, { requireImage: false }).filter(
        (c) => c.type !== "scene"
      )
      const removed = castLibrary.filter(
        (c) => !normalized.some((n) => n.id === c.id)
      )
      setCastLibrary(normalized)
      setRows((prev) => {
        let updated = stripRemovedCastFromRows(prev, removed)
        updated = applyCastLibraryAutoLink(updated, segments, normalized)
        updated = stripCastImagesFromCompositionRefs(updated, normalized)
        deferNodePatch(updateData, { castLibrary: normalized, rows: updated })
        return updated
      })
    },
    [updateData, segments, castLibrary]
  )

  const handleSceneLibraryChange = useCallback(
    (next) => {
      const normalized = normalizeSceneLibrary(next, { requireImage: false })
      setSceneLibrary(normalized)
      deferNodePatch(updateData, { sceneLibrary: normalized })
    },
    [updateData]
  )

  const reorderRows = useCallback(
    (fromId, toId) => {
      if (!fromId || !toId || fromId === toId || readOnly) return
      setRows((prev) => {
        const fromIdx = prev.findIndex((r) => r.id === fromId)
        const toIdx = prev.findIndex((r) => r.id === toId)
        if (fromIdx < 0 || toIdx < 0) return prev
        const next = [...prev]
        const [moved] = next.splice(fromIdx, 1)
        next.splice(toIdx, 0, moved)
        const renumbered = next.map((r, i) => ({ ...r, shotNumber: i + 1 }))
        deferNodePatch(updateData, { rows: renumbered })
        return renumbered
      })
    },
    [updateData, readOnly]
  )

  const handleShotDragStart = useCallback((rowId, e) => {
    setDragRowId(rowId)
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData(SHOT_REORDER_MIME, rowId)
    const blank = new Image()
    blank.src = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    e.dataTransfer.setDragImage(blank, 0, 0)
  }, [])

  useEffect(() => {
    if (!dragRowId) return undefined
    const onDragOver = (e) => {
      e.preventDefault()
      const el = shotListRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const zone = 72
      if (e.clientY < rect.top + zone) {
        const intensity = (zone - (e.clientY - rect.top)) / zone
        el.scrollTop -= Math.max(6, Math.round(18 * intensity))
      } else if (e.clientY > rect.bottom - zone) {
        const intensity = (zone - (rect.bottom - e.clientY)) / zone
        el.scrollTop += Math.max(6, Math.round(18 * intensity))
      }
    }
    document.addEventListener("dragover", onDragOver)
    return () => document.removeEventListener("dragover", onDragOver)
  }, [dragRowId])

  const handleContinuityToggle = useCallback(
    (e) => {
      const value = e.target.checked
      setContinuityMode(value)
      updateData({ continuityMode: value })
    },
    [updateData]
  )

  const handleVisualContinuityToggle = useCallback(
    (e) => {
      const value = e.target.checked
      setVisualContinuity(value)
      updateData({ visualContinuity: value })
    },
    [updateData]
  )

  const handleGenerateShot = useCallback(
    async (row, genOptions = {}) => {
      if (readOnly) return
      if (!modelId) {
        updateRow(row.id, { directStatus: "failed", error: t("canvas.script.selectImageModel") })
        return
      }
      if (!canvasActions?.runScriptTableDirectImageGenerate) {
        updateRow(row.id, { error: t("canvas.script.storyboardGenFail") })
        return
      }
      updateData({ modelId, castLibrary, continuityMode, visualContinuity })
      await canvasActions.runScriptTableDirectImageGenerate(id, row.id, {
        modelId,
        ...genOptions,
      })
    },
    [readOnly, modelId, canvasActions, id, updateData, castLibrary, continuityMode, visualContinuity, updateRow, t]
  )

  const handleGenerateKeyframe = useCallback(
    async (row, keyframeId, genOptions = {}) => {
      if (readOnly) return
      if (!modelId) return
      if (!canvasActions?.runScriptTableKeyframeGenerate) return
      updateData({ modelId, castLibrary, continuityMode, visualContinuity })
      await canvasActions.runScriptTableKeyframeGenerate(id, row.id, keyframeId, {
        modelId,
        ...genOptions,
      })
    },
    [id, modelId, castLibrary, continuityMode, visualContinuity, updateData, canvasActions, readOnly]
  )

  const openPreview = useCallback(
    (row, keyframeId = null) => {
      const pkg = buildLocalPromptPackage(row, castLibrary, keyframeId, sceneLibrary)
      setPreviewState({
        rowId: row.id,
        keyframeId,
        pkg,
        source: "rule",
      })
    },
    [castLibrary]
  )

  const handleExpandPrompt = useCallback(
    async (row, keyframeId = null) => {
      if (readOnly) return
      setPreviewLoading(true)
      try {
        const res = await expandShotPromptPackage(row, castLibrary, {
          keyframeId,
          useLlm: true,
          sceneLibrary,
        })
        const pkg = normalizePromptPackage(res)
        if (keyframeId) {
          updateKeyframe(row.id, keyframeId, { compiledPromptPackage: pkg })
        } else {
          const kfs = (row.keyframes || []).map((kf) => ({
            ...kf,
            compiledPromptPackage: buildLocalPromptPackage(
              { ...row, compiledPromptPackage: pkg },
              castLibrary,
              kf.id,
              sceneLibrary
            ),
          }))
          updateRow(row.id, { compiledPromptPackage: pkg, keyframes: kfs })
        }
      } finally {
        setPreviewLoading(false)
      }
    },
    [castLibrary, sceneLibrary, updateKeyframe, updateRow, readOnly]
  )

  const handlePreviewLlmExpand = useCallback(async () => {
    if (readOnly || !previewState) return
    const row = rows.find((r) => r.id === previewState.rowId)
    if (!row) return
    setPreviewLoading(true)
    try {
      const res = await expandShotPromptPackage(row, castLibrary, {
        keyframeId: previewState.keyframeId,
        useLlm: true,
        sceneLibrary,
      })
      const pkg = normalizePromptPackage(res)
      setPreviewState((s) => ({
        ...s,
        pkg,
        source: pkg.source || "llm",
      }))
    } finally {
      setPreviewLoading(false)
    }
  }, [previewState, rows, castLibrary, sceneLibrary, readOnly])

  const handlePreviewConfirm = useCallback(
    async (pkg) => {
      if (readOnly || !previewState) return
      const row = rows.find((r) => r.id === previewState.rowId)
      if (!row) return
      const apiDesc = (pkg.apiDescription || pkg.fullText || "").trim()
      const { rowId, keyframeId } = previewState
      setPreviewState(null)

      if (keyframeId) {
        updateKeyframe(rowId, keyframeId, { compiledPromptPackage: pkg })
        await handleGenerateKeyframe(row, keyframeId, {
          descriptionOverride: apiDesc,
          compiledPackage: pkg,
        })
        return
      }

      const updatedRow = { ...row, compiledPromptPackage: pkg }
      updateRow(rowId, { compiledPromptPackage: pkg })
      await handleGenerateShot(updatedRow, {
        descriptionOverride: apiDesc,
        compiledPackage: pkg,
      })
    },
    [previewState, rows, castLibrary, sceneLibrary, updateKeyframe, updateRow, handleGenerateKeyframe, handleGenerateShot, readOnly]
  )

  const applyPresetToAllRows = useCallback(() => {
    syncRows(rows.map((r) => applyQualityPresetToRow(r, qualityPresetId)))
  }, [rows, qualityPresetId, syncRows])

  const handleOpenBeatCard = useCallback(
    async (row, options = {}) => {
      if (readOnly) return
      let beatId = row.beatCardNodeId
      if (!beatId || !getNode(beatId)) {
        beatId = canvasActions?.createBeatCardForRow?.(id, row.id)
      }
      if (beatId) {
        canvasActions?.focusBeatCard?.(beatId)
      }
    },
    [readOnly, id, canvasActions, getNode]
  )

  const handleGenerateDirectImage = useCallback(
    async (row) => {
      if (readOnly) return
      if (!modelId) {
        updateRow(row.id, { error: t("canvas.script.selectImageModel") })
        return
      }
      await handleGenerateShot(row)
    },
    [readOnly, modelId, updateRow, handleGenerateShot, t]
  )

  const handleGenerateDirectVideo = useCallback(
    async (row) => {
      if (readOnly) return
      if (!videoModelId) {
        updateRow(row.id, { error: t("canvas.script.selectVideoModelToolbar") })
        return
      }
      updateData({ videoModelId, modelId, castLibrary, continuityMode, visualContinuity })
      await canvasActions?.runScriptTableDirectVideoGenerate?.(id, row.id, { videoModelId })
    },
    [
      readOnly,
      id,
      videoModelId,
      modelId,
      castLibrary,
      continuityMode,
      visualContinuity,
      updateData,
      updateRow,
      canvasActions,
      t,
    ]
  )

  const handleRetryDirect = useCallback(
    async (row) => {
      if (readOnly) return
      updateRow(row.id, { error: null, directStatus: "idle" })
      await handleGenerateDirectImage(row)
    },
    [readOnly, updateRow, handleGenerateDirectImage]
  )

  const handleGenerateAll = useCallback(async () => {
    if (readOnly) return
    if (!modelId) return
    if (!canvasActions?.runScriptTableGenerateAll) return
    setBatchRunning(true)
    updateData({ modelId, castLibrary, continuityMode, visualContinuity })
    try {
      await canvasActions.runScriptTableGenerateAll(id, { modelId })
    } finally {
      setBatchRunning(false)
    }
  }, [id, modelId, castLibrary, continuityMode, visualContinuity, updateData, canvasActions, readOnly])

  const summary = useMemo(() => {
    const totalShots = rows.length
    const totalDuration = rows.reduce((s, r) => s + (Number(r.duration) || 0), 0)
    const totalFrames = rows.reduce(
      (s, r) => s + (r.keyframes?.length || 0),
      0
    )
    return { totalShots, totalDuration, totalFrames }
  }, [rows])

  const sp = (e) => e.stopPropagation()

  const stopWheelBubble = handleNodeWheel

  const targetVideoDurationSec = data.targetVideoDurationSec ?? null
  const durationWarning = data.durationWarning || null
  const tableError = data.error || null

  const renderShotCard = (row) => {
    const beatCard = row.beatCardNodeId ? getNode(row.beatCardNodeId) : null
    const beatCardKeyframeCount =
      beatCard?.type === BEAT_CARD_NODE_TYPE
        ? (beatCard.data?.keyframes || []).length
        : 0
    return (
    <ScriptShotCard
      key={row.id}
      row={row}
      rowsCount={rows.length}
      castLibrary={castLibrary}
      sceneLibrary={sceneLibrary}
      batchRunning={batchRunning}
      beatCardKeyframeCount={beatCardKeyframeCount}
      onUpdateRow={updateRow}
      onDeleteRow={handleDeleteRow}
      onOpenBeatCard={handleOpenBeatCard}
      onGenerateDirectImage={handleGenerateDirectImage}
      onGenerateDirectVideo={handleGenerateDirectVideo}
      onRetryDirect={handleRetryDirect}
      onOpenPreview={openPreview}
      onExpandPrompt={handleExpandPrompt}
      readOnly={readOnly}
      dragOver={dragOverRowId === row.id && dragRowId !== row.id}
      onDragHandleStart={(e) => handleShotDragStart(row.id, e)}
      onDragOver={(e) => {
        if (!dragRowId || dragRowId === row.id) return
        e.preventDefault()
        e.dataTransfer.dropEffect = "move"
        setDragOverRowId(row.id)
      }}
      onDrop={(e) => {
        e.preventDefault()
        const fromId = dragRowId || e.dataTransfer.getData(SHOT_REORDER_MIME)
        reorderRows(fromId, row.id)
        setDragRowId(null)
        setDragOverRowId(null)
      }}
      onDragEnd={() => {
        setDragRowId(null)
        setDragOverRowId(null)
      }}
    />
    )
  }

  const renderGroupedItem = (item) =>
    item.kind === "segment" ? (
      <ScriptSegmentHeader
        key={`seg-${item.segment.id}`}
        segment={item.segment}
        readOnly={readOnly}
        onUpdateSegment={updateSegment}
      />
    ) : (
      renderShotCard(item.row)
    )
  const exportText = useMemo(
    () => scriptTableToExportText({ rows, segments }),
    [rows, segments]
  )

  const hasDescRows = rows.some((r) => rowHasGeneratableContent(r))
  const anyGenerating =
    rows.some((r) => r.status === "generating")
    || rows.some((r) => (r.keyframes || []).some((k) => k.status === "generating"))
    || batchRunning

  const projectSettingsSummary = useMemo(() => {
    const castCount = castLibrary.filter((c) => c.type !== "scene").length
    const sceneCount = sceneLibrary.length
    return t("canvas.script.projectSettingsSummary", {
      cast: castCount,
      scene: sceneCount,
    })
  }, [castLibrary, sceneLibrary, t])

  const toggleProjectSettings = useCallback(() => {
    setProjectSettingsOpen((open) => !open)
  }, [])

  return (
    <div
      ref={wrapperRef}
      className={`st-wrapper st-wrapper--simple${selected ? " st-wrapper--selected" : ""}`}
    >
      <TextWorkflowEdgePlugs nodeId={id} nodeType="script-table" disabled={readOnly} />
      <div className="st-header">
        <h2 className="st-header-title cn-title">{t("canvas.script.table")}</h2>
        <NodeCardDotsMenu
          text={exportText}
          filenamePrefix={t("canvas.script.table")}
          visible={!tableLoading}
          extraItems={[
            {
              key: "export-full",
              label: t("canvas.export.fullProject"),
              onClick: () => setExportOpen(true),
            },
          ]}
        />
      </div>

      <div
        className={`st-root${readOnly ? " st-root--readonly" : ""}`}
        onDoubleClick={sp}
        onContextMenu={(e) => e.stopPropagation()}
      >
        <div className="st-summary-bar nodrag">
          <div className="st-summary-stats cn-body">
            <span className="st-summary-stat">
              {t("canvas.script.summaryShots", { n: summary.totalShots })}
            </span>
            <span className="st-summary-stat">
              {t("canvas.script.summaryDuration")}{" "}
              <span
                className={
                  targetVideoDurationSec && summary.totalDuration > targetVideoDurationSec
                    ? "st-duration-over"
                    : "cn-emphasis"
                }
              >
                {formatDurationSec(summary.totalDuration)}
              </span>
              {targetVideoDurationSec && (
                <>
                  {" "}
                  {t("canvas.script.summaryTargetPrefix")}{" "}
                  <span className="cn-emphasis">{formatDurationSec(targetVideoDurationSec)}</span>
                </>
              )}
            </span>
          </div>
          <span className="st-summary-hint cn-muted">
            {t("canvas.script.tableWorkflowHint")}
          </span>
        </div>
        {durationWarning && (
          <p className="st-duration-warning nodrag cn-body">{durationWarning}</p>
        )}
        {tableError && (
          <p className="st-duration-warning nodrag cn-body st-table-error">{tableError}</p>
        )}

        <button
          type="button"
          className="st-project-settings-summary nodrag"
          onClick={toggleProjectSettings}
          onPointerDown={sp}
        >
          <span className="st-project-settings-summary-text cn-muted">{projectSettingsSummary}</span>
          <ProjectSettingsChevron open={projectSettingsOpen} />
        </button>

        {projectSettingsOpen && (
        <div className="st-lib-compact nodrag">
          <div className="st-lib-card nodrag">
            <h3 className="st-lib-section-title cn-param-key">{t("canvas.script.castLib")}</h3>
            <ScriptCastLibrary
              nodeId={id}
              castLibrary={castLibrary}
              readOnly={readOnly}
              onChange={handleCastLibraryChange}
            />
          </div>
          <div className="st-lib-card nodrag">
            <h3 className="st-lib-section-title cn-param-key">{t("canvas.script.sceneLib")}</h3>
            <ScriptSceneLibrary
              nodeId={id}
              sceneLibrary={sceneLibrary}
              readOnly={readOnly}
              onChange={handleSceneLibraryChange}
            />
          </div>
        </div>
        )}

        <div className="st-toolbar nodrag st-toolbar--simple">
          <div className="st-toolbar-main">
            <div className="st-toolbar-pills">
            {imageModels.length > 0 && (
              <CanvasModelDropup
                tag={t("canvas.script.image")}
                icon={ImageModelIcon}
                models={imageModels}
                value={modelId}
                direction="down"
                disabled={readOnly}
                onChange={(mid) => {
                  setModelId(mid)
                  updateData({ modelId: mid })
                }}
                title={t("canvas.script.imageModelTitle")}
              />
            )}
            {videoModels.length > 0 && (
              <CanvasModelDropup
                tag={t("canvas.script.video")}
                icon={VideoModelIcon}
                models={videoModels.map((m) => ({
                  ...m,
                  id: m.id || m.display_name,
                }))}
                value={videoModelId}
                direction="down"
                disabled={readOnly}
                onChange={(mid) => {
                  setVideoModelId(mid)
                  updateData({ videoModelId: mid })
                }}
                title={t("canvas.script.videoModelTitle")}
              />
            )}
            <CanvasModelDropup
              tag={t("canvas.script.defaultStyle")}
              icon={PresetIcon}
              models={SCRIPT_QUALITY_PRESETS.map((p) => ({
                id: p.id,
                display_name: p.name,
              }))}
              value={qualityPresetId}
              direction="down"
              disabled={readOnly}
              onChange={(pid) => setQualityPresetId(pid)}
              title={t("canvas.script.defaultStyleTitle")}
            />
            <button
              type="button"
              className="st-preset-apply-btn"
              disabled={readOnly}
              onClick={applyPresetToAllRows}
              onPointerDown={sp}
            >
              {t("canvas.script.applyAll")}
            </button>
            </div>
          <div className="st-toolbar-row st-toolbar-row--actions">
            <button
              type="button"
              className="st-gen-all-btn st-gen-all-btn--primary"
              disabled={readOnly || !hasDescRows || anyGenerating}
              onClick={handleGenerateAll}
              onPointerDown={sp}
            >
              {batchRunning ? t("canvas.script.batchGenerating") : t("canvas.script.genAll")}
            </button>
            <button
              type="button"
              className="st-shot-edit-toggle"
              onClick={() => setAdvancedOpen((v) => !v)}
              onPointerDown={sp}
            >
              {advancedOpen ? t("canvas.script.collapseAdvanced") : t("canvas.script.advanced")}
            </button>
          </div>
          </div>
          {advancedOpen && (
            <div className="st-advanced-toolbar st-advanced-toolbar--open">
              <div className="st-advanced-toggles">
                <div className="st-continuity-row">
                  <label className="st-continuity-toggle" onPointerDown={sp}>
                    <input
                      type="checkbox"
                      checked={continuityMode}
                      disabled={readOnly}
                      onChange={handleContinuityToggle}
                    />
                    <span>{t("canvas.script.plotContinuity")}</span>
                  </label>
                  <button
                    type="button"
                    className="st-continuity-info-btn nodrag"
                    onClick={() => {
                      setContinuityInfoOpen((v) => {
                        const next = !v
                        if (next) setVisualInfoOpen(false)
                        return next
                      })
                    }}
                    onPointerDown={sp}
                    aria-label={t("canvas.script.plotContinuity")}
                  >
                    ⓘ
                  </button>
                </div>
                <div className="st-continuity-row">
                  <label className="st-continuity-toggle" onPointerDown={sp}>
                    <input
                      type="checkbox"
                      checked={visualContinuity}
                      disabled={readOnly}
                      onChange={handleVisualContinuityToggle}
                    />
                    <span>{t("canvas.script.visualRefPrev")}</span>
                  </label>
                  <button
                    type="button"
                    className="st-continuity-info-btn nodrag"
                    onClick={() => {
                      setVisualInfoOpen((v) => {
                        const next = !v
                        if (next) setContinuityInfoOpen(false)
                        return next
                      })
                    }}
                    onPointerDown={sp}
                    aria-label={t("canvas.script.visualRefPrev")}
                  >
                    ⓘ
                  </button>
                </div>
              </div>
              {(continuityInfoOpen || visualInfoOpen) && (
                <div className="st-advanced-info-banners">
                  {continuityInfoOpen && (
                    <div className="st-continuity-info-banner">
                      {t("canvas.script.plotContinuityDesc")}
                    </div>
                  )}
                  {visualInfoOpen && (
                    <div className="st-continuity-info-banner">
                      {t("canvas.script.visualRefPrevDesc")}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {tableLoading ? (
          <div className="st-loading-wrap nodrag">
            <NodeLoadingState
              message={
                data.generatingFromOutline
                  ? t("canvas.script.genFromOutline")
                  : t("canvas.script.tableLoading")
              }
            />
          </div>
        ) : (
          <div
            ref={shotListRef}
            className={`st-shot-list scrollable-content nowheel${
              useVirtualShotList ? " st-shot-list--virtual" : ""
            }`}
            onWheel={stopWheelBubble}
          >
            {useVirtualShotList ? (
              <div
                className="st-shot-list-inner"
                style={{
                  height: shotListVirtualizer.getTotalSize(),
                  position: "relative",
                  width: "100%",
                }}
              >
                {shotListVirtualizer.getVirtualItems().map((vi) => {
                  const item = groupedItems[vi.index]
                  return (
                    <div
                      key={vi.key}
                      data-index={vi.index}
                      ref={shotListVirtualizer.measureElement}
                      className="st-shot-list-item"
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        transform: `translateY(${vi.start}px)`,
                      }}
                    >
                      {renderGroupedItem(item)}
                    </div>
                  )
                })}
              </div>
            ) : (
              groupedItems.map((item) => renderGroupedItem(item))
            )}
          </div>
        )}

        <button
          type="button"
          className="st-add-row nodrag"
          disabled={readOnly}
          onClick={handleAddRow}
          onPointerDown={sp}
        >
          {t("canvas.script.addShot")}
        </button>
      </div>

      <MediaLightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />

      {dragRowId && createPortal(
        <div className={`st-shot-drag-banner st-shot-drag-banner--${theme}`} role="status">
          {t("canvas.script.dragShotDropHint")}
        </div>,
        document.body
      )}

      <ScriptShotPreviewModal
        open={Boolean(previewState?.pkg)}
        title={
          previewState?.keyframeId
            ? t("canvas.script.previewCell", {
                n: rows.find((r) => r.id === previewState?.rowId)?.shotNumber ?? "",
              })
            : t("canvas.script.previewShot", {
                n: rows.find((r) => r.id === previewState?.rowId)?.shotNumber ?? "",
              })
        }
        pkg={previewState?.pkg}
        loading={previewLoading}
        sourceLabel={
          previewState?.source === "llm" ? t("canvas.script.llmExpandTag") : t("canvas.script.ruleAssemble")
        }
        confirmLabel={
          previewState?.keyframeId ? t("canvas.script.confirmCell") : t("canvas.script.confirmShot")
        }
        onClose={() => setPreviewState(null)}
        onExpandLlm={handlePreviewLlmExpand}
        onConfirmGenerate={handlePreviewConfirm}
        commitDisabled={readOnly}
      />
      <ExportProjectModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        defaultScriptTableNodeId={id}
      />
    </div>
  )
}
