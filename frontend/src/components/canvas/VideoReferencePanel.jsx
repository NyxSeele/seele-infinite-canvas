import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useReactFlow, useStore } from "reactflow"
import { useReferenceSelect } from "./CanvasActionsContext"
import RefPickerTrigger from "./RefPickerTrigger"
import AddRefHoverPanel, { RefPickAnchor } from "./AddRefHoverPanel"
import {
  DEFAULT_KEYFRAMES,
  truncateLabel,
  buildRefItem,
  resolveReferenceImageUrl,
  resolveRefDisplayUrl,
} from "./videoReferenceHelpers"
import { uploadImageFile } from "../../services/uploadImage"
import api from "../../services/api"
import { refreshMediaTicket } from "../../utils/mediaTicket"
import useRefAssetEntries from "../../hooks/canvas/useRefAssetEntries"
import { useLocale } from "../../utils/locale"
import VideoStyleReferencePanel from "./VideoStyleReferencePanel"
import VideoStylePicker from "./VideoStylePicker"
import CameraMotionPicker from "./CameraMotionPicker"
import { findScriptTableNode, resolveVideoQualityPresetId } from "../../utils/canvas/scriptTableNode"
import {
  reconcileVideoModelAndMode,
  referenceModeForVidMode,
} from "../../utils/canvas/videoModelCompat"
import { useModelStore } from "../../stores"
import "./VideoStylePicker.css"
import "./CameraMotionPicker.css"
import "./VideoReferencePanel.css"
import "./CanvasImageQuickPicker.css"

const sp = (e) => e.stopPropagation()

function sourceNodeMediaFingerprint(node) {
  if (!node?.data) return ""
  const d = node.data
  const results = Array.isArray(d.results) ? d.results.filter(Boolean).join("|") : ""
  return [
    node.id,
    results,
    d.resultUrl || "",
    d.uploadedImage || "",
    d.imageUrl || "",
    d.generatedImage || "",
  ].join("::")
}

function itemToRefItem(item) {
  return buildRefItem({
    nodeId: item.nodeId,
    imageIndex: item.imageIndex ?? 0,
    imageUrl: item.url || item.imageUrl,
    imageId: item.imageId,
    label: item.label,
  })
}

function RefThumbnail({ refItem, getNode, sourceFingerprint = "", className = "", imgStyle, onLoadFail }) {
  const resolveSrc = useCallback(
    () => resolveRefDisplayUrl(refItem, getNode),
    [refItem, getNode]
  )
  const [src, setSrc] = useState(resolveSrc)
  const retryCountRef = useRef(0)
  const identityKey = [
    refItem?.nodeId || "",
    refItem?.imageIndex ?? 0,
    refItem?.imageUrl || "",
    sourceFingerprint,
  ].join("|")

  useEffect(() => {
    setSrc(resolveSrc())
    retryCountRef.current = 0
  }, [identityKey, resolveSrc])

  const handleError = useCallback(async () => {
    if (retryCountRef.current >= 2) {
      setSrc(null)
      onLoadFail?.()
      return
    }
    retryCountRef.current += 1
    try {
      await refreshMediaTicket(api)
    } catch {
      /* ignore */
    }
    const retry = resolveSrc()
    setSrc(retry || null)
  }, [resolveSrc, onLoadFail])

  if (!src) {
    return <span className={`ref-thumb-fallback${className ? ` ${className}` : ""}`} aria-hidden />
  }

  return (
    <img
      className={className}
      src={src}
      alt=""
      draggable={false}
      onDragStart={(e) => e.preventDefault()}
      onError={handleError}
      style={imgStyle}
    />
  )
}

function RefTag({ refItem, getNode, sourceFingerprint = "", label, onRemove }) {
  if (!refItem) return null
  const displayUrl = resolveRefDisplayUrl(refItem, getNode)
  const [thumbFailed, setThumbFailed] = useState(false)
  const showLabel = !displayUrl || thumbFailed

  useEffect(() => {
    setThumbFailed(false)
  }, [displayUrl, refItem?.nodeId, refItem?.imageUrl, refItem?.imageIndex])

  return (
    <div className="ref-tag nodrag nopan">
      {displayUrl && !thumbFailed ? (
        <RefThumbnail
          refItem={refItem}
          getNode={getNode}
          sourceFingerprint={sourceFingerprint}
          onLoadFail={() => setThumbFailed(true)}
        />
      ) : (
        <span className="ref-thumb-fallback" aria-hidden />
      )}
      {showLabel && label ? <span className="ref-label">{label}</span> : null}
      <button
        type="button"
        className="ref-remove nodrag nopan"
        onClick={(e) => { sp(e); onRemove() }}
      >
        ×
      </button>
    </div>
  )
}

function KeyframeSlot({
  slotLabel,
  value,
  getNode,
  sourceFingerprint = "",
  onQuickSelect,
  onCanvasPick,
  onUpload,
  onClear,
  clearAriaLabel,
  assetEntries = [],
  onAssetPick,
}) {
  const hasValue = Boolean(value && (value.nodeId || value.imageUrl))
  const displayUrl = resolveRefDisplayUrl(value, getNode)

  if (hasValue) {
    return (
      <div className="keyframe-slot keyframe-slot--filled nodrag nopan">
        {displayUrl ? (
          <RefThumbnail
            refItem={value}
            getNode={getNode}
            sourceFingerprint={sourceFingerprint}
            imgStyle={{ pointerEvents: "none" }}
          />
        ) : (
          <span className="ref-thumb-fallback" aria-hidden />
        )}
        <span className="keyframe-slot-tag">{slotLabel}</span>
        <button
          type="button"
          className="keyframe-slot-clear nodrag nopan"
          aria-label={clearAriaLabel}
          onClick={(e) => { sp(e); onClear() }}
          onPointerDown={sp}
        >
          ×
        </button>
      </div>
    )
  }

  return (
    <RefPickAnchor
      className="keyframe-slot nodrag nopan"
      showUpload={true}
      onQuickSelect={onQuickSelect}
      onCanvasPick={onCanvasPick}
      onUpload={onUpload}
      assetEntries={assetEntries}
      onAssetPick={onAssetPick}
    >
      <div className="keyframe-slot-empty">
        <span className="keyframe-slot-plus">+</span>
        <span className="keyframe-slot-label">{slotLabel}</span>
      </div>
    </RefPickAnchor>
  )
}

export default function VideoReferencePanel({
  nodeId,
  data,
  section = "all",
  projectId = null,
  readOnly = false,
  slotsExpanded = false,
  onSlotsExpandedChange,
  enhancePanelSlot = null,
}) {
  const { t } = useLocale()
  const { getNodes, getNode } = useReactFlow()
  const refSelect = useReferenceSelect()
  const { assetEntries, ensureLoaded } = useRefAssetEntries()
  const videoModels = useModelStore((s) => s.videoModels)
  const [styleRefOpen, setStyleRefOpen] = useState(false)

  const onUpdate = data?.onUpdate
  const forceKeyframe = (data?.modelId || "") === "wan-fun-inpaint"
  const isT2vMode = !forceKeyframe && (
    data?.referenceMode === "t2v"
    || data?.vidMode === "文生"
    || data?.panelMode === "t2v"
  )
  const referenceModeFromData = forceKeyframe
    ? "keyframe"
    : (data?.referenceMode || "keyframe")
  const panelModeFromData = data?.panelMode ?? null
  const [localPanelMode, setLocalPanelMode] = useState(
    forceKeyframe && panelModeFromData === "freeref" ? "keyframe" : panelModeFromData
  )
  const referenceMode = localPanelMode === "enhance"
    ? referenceModeFromData
    : (localPanelMode || referenceModeFromData)
  const effectivePanelMode =
    localPanelMode || (referenceModeFromData === "enhance" ? "enhance" : referenceModeFromData)

  useEffect(() => {
    if (forceKeyframe) {
      setLocalPanelMode((prev) => (prev === "enhance" ? prev : "keyframe"))
      return
    }
    setLocalPanelMode(data?.panelMode ?? null)
  }, [data?.panelMode, forceKeyframe, nodeId])

  useEffect(() => {
    if (!forceKeyframe || !onUpdate || !nodeId) return
    if (data?.referenceMode === "keyframe" && data?.panelMode !== "freeref") return
    onUpdate(nodeId, {
      referenceMode: "keyframe",
      panelMode: "keyframe",
      vidMode: "首尾帧",
    })
  }, [forceKeyframe, data?.referenceMode, data?.panelMode, onUpdate, nodeId])

  const [keyframes, setKeyframes] = useState(data?.keyframes || DEFAULT_KEYFRAMES)
  const [freeRefs, setFreeRefs] = useState(data?.freeRefs || [])

  const [keyframePick, setKeyframePick] = useState(null)

  useEffect(() => {
    setKeyframes(data?.keyframes || DEFAULT_KEYFRAMES)
    setFreeRefs(data?.freeRefs || [])
  }, [data?.keyframes, data?.freeRefs])

  const sourceNodeIds = useMemo(() => {
    const ids = []
    if (keyframes.first?.nodeId) ids.push(String(keyframes.first.nodeId))
    if (keyframes.last?.nodeId) ids.push(String(keyframes.last.nodeId))
    for (const ref of freeRefs || []) {
      if (ref?.nodeId) ids.push(String(ref.nodeId))
    }
    return [...new Set(ids)]
  }, [keyframes, freeRefs])

  const sourceMediaById = useStore(
    useCallback(
      (s) => {
        const map = {}
        for (const id of sourceNodeIds) {
          const n = s.nodeInternals.get(id)
          map[id] = sourceNodeMediaFingerprint(n)
        }
        return map
      },
      [sourceNodeIds]
    ),
    (a, b) => {
      if (a === b) return true
      const keys = new Set([...Object.keys(a || {}), ...Object.keys(b || {})])
      for (const k of keys) {
        if ((a || {})[k] !== (b || {})[k]) return false
      }
      return true
    }
  )

  // Touch fingerprints so React re-renders when source node media changes
  void sourceMediaById

  useEffect(() => {
    if (slotsExpanded) ensureLoaded()
  }, [slotsExpanded, ensureLoaded])

  const persist = useCallback((patch, { rememberSlots = false } = {}) => {
    const next = rememberSlots ? { ...patch, referenceSlotsOpen: true } : patch
    onUpdate?.(nodeId, next)
  }, [onUpdate, nodeId])

  const handleModeClick = useCallback((mode) => {
    // 已选中 Tab 再点：保持当前功能区，不折叠
    if (localPanelMode === mode) return
    setLocalPanelMode(mode)
    if (mode === "enhance") {
      persist({ panelMode: "enhance" }, { rememberSlots: true })
      onSlotsExpandedChange?.(true)
      return
    }
    const nextVidMode = mode === "freeref" ? "参考" : mode === "t2v" ? "文生" : "首尾帧"
    const reconciled = reconcileVideoModelAndMode({
      modelId: data?.modelId || "",
      vidMode: nextVidMode,
      models: videoModels,
    })
    const refMode = referenceModeForVidMode(reconciled.vidMode)
    const modePatch = {
      panelMode: refMode,
      referenceMode: refMode,
      vidMode: reconciled.vidMode,
      ...(reconciled.modelId ? { modelId: reconciled.modelId } : {}),
    }
    if (mode === "freeref") {
      const currentKeyframes = data?.keyframes || keyframes || DEFAULT_KEYFRAMES
      const currentFreeRefs = Array.isArray(data?.freeRefs) ? data.freeRefs : freeRefs
      if (currentFreeRefs.length === 0 && currentKeyframes.first) {
        const migrated = resolveReferenceImageUrl(currentKeyframes.first, getNode)
        if (migrated?.imageUrl) {
          modePatch.freeRefs = [migrated]
        }
      }
    }
    // 文生无参考槽：折叠并持久化，避免空白展开区；其余模式一并写入 referenceSlotsOpen
    if (mode === "t2v") {
      persist({ ...modePatch, referenceSlotsOpen: false })
      onSlotsExpandedChange?.(false)
      return
    }
    persist(modePatch, { rememberSlots: true })
    onSlotsExpandedChange?.(true)
  }, [
    localPanelMode,
    onSlotsExpandedChange,
    persist,
    data?.modelId,
    data?.keyframes,
    data?.freeRefs,
    keyframes,
    freeRefs,
    getNode,
    videoModels,
  ])

  const setMode = useCallback((mode) => {
    if (forceKeyframe && (mode === "freeref" || mode === "t2v")) return
    handleModeClick(mode)
  }, [handleModeClick, forceKeyframe])

  const updateKeyframes = useCallback((updater) => {
    setKeyframes((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater
      persist({ keyframes: next }, { rememberSlots: true })
      onSlotsExpandedChange?.(true)
      return next
    })
  }, [persist, onSlotsExpandedChange])

  const updateFreeRefs = useCallback((updater) => {
    setFreeRefs((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater
      persist({ freeRefs: next }, { rememberSlots: true })
      onSlotsExpandedChange?.(true)
      return next
    })
  }, [persist, onSlotsExpandedChange])

  const openCanvasPickerFor = useCallback((target) => {
    refSelect?.enter(nodeId, target)
  }, [refSelect, nodeId])

  const openCanvasPicker = useCallback(() => {
    if (referenceMode === "freeref") {
      if (freeRefs.length < 5) openCanvasPickerFor("freeref")
      return
    }
    if (!keyframes.first) openCanvasPickerFor("first")
    else if (!keyframes.last) openCanvasPickerFor("last")
    else openCanvasPickerFor("first")
  }, [referenceMode, keyframes, freeRefs.length, openCanvasPickerFor])

  const applyRefItemToSlot = useCallback(
    (refItem, slot) => {
      const resolved = resolveReferenceImageUrl(refItem, getNode)
      if (!resolved?.imageUrl) return
      if (!resolveRefDisplayUrl(refItem, getNode)) {
        console.warn("参考图 URL 无法展示", resolved.imageUrl)
        return
      }
      if (slot === "freeref") {
        updateFreeRefs((refs) => {
          if (refs.length >= 5 || refs.some((r) => r.imageId === resolved.imageId)) return refs
          return [...refs, resolved]
        })
        return
      }
      updateKeyframes((k) => ({ ...k, [slot]: resolved }))
    },
    [updateKeyframes, updateFreeRefs, getNode]
  )

  const applyQuickToSlot = useCallback(
    (item, slot) => {
      applyRefItemToSlot(itemToRefItem(item), slot)
    },
    [applyRefItemToSlot]
  )

  const uploadFileToSlot = useCallback(
    async (file, slot) => {
      if (!file) return
      try {
        const url = await uploadImageFile(file)
        const uploadId = `upload_${Date.now()}`
        const baseName = file.name?.replace(/\.[^.]+$/, "").trim()
        const refItem = buildRefItem({
          nodeId: uploadId,
          imageIndex: 0,
          imageUrl: url,
          imageId: `${uploadId}_${Math.random().toString(36).slice(2, 8)}`,
          label: baseName || t("canvas.prompt.refImage"),
        })
        applyRefItemToSlot(refItem, slot)
      } catch (err) {
        console.error("参考图上传失败", err)
      }
    },
    [applyRefItemToSlot, t]
  )

  const applyAssetToSlot = useCallback(
    (asset, slot) => {
      if (!asset?.imageUrl) return
      const refItem = buildRefItem({
        nodeId: `asset_${asset.id}`,
        imageIndex: 0,
        imageUrl: asset.imageUrl,
        imageId: asset.id,
        label: asset.name,
      })
      applyRefItemToSlot(refItem, slot)
    },
    [applyRefItemToSlot]
  )

  const resolveTopBarSlot = useCallback(() => {
    if (referenceMode === "freeref") return "freeref"
    if (!keyframes.first) return "first"
    if (!keyframes.last) return "last"
    return "first"
  }, [referenceMode, keyframes])

  const handleTopBarUpload = useCallback(
    (file) => uploadFileToSlot(file, resolveTopBarSlot()),
    [uploadFileToSlot, resolveTopBarSlot]
  )

  const handleTopBarAssetPick = useCallback(
    (asset) => applyAssetToSlot(asset, resolveTopBarSlot()),
    [applyAssetToSlot, resolveTopBarSlot]
  )

  const handleTopBarQuickSelect = useCallback(
    (item) => {
      if (referenceMode === "freeref") {
        applyQuickToSlot(item, "freeref")
        return
      }
      if (!keyframes.first) applyQuickToSlot(item, "first")
      else if (!keyframes.last) applyQuickToSlot(item, "last")
      else applyQuickToSlot(item, "first")
    },
    [referenceMode, keyframes, applyQuickToSlot]
  )

  const removeFreeRef = useCallback((index) => {
    const ref = freeRefs[index]
    if (ref?.nodeId && data?.onDisconnectIncomingFromSource) {
      data.onDisconnectIncomingFromSource(nodeId, ref.nodeId)
      return
    }
    updateFreeRefs((refs) => refs.filter((_, i) => i !== index))
  }, [freeRefs, data, nodeId, updateFreeRefs])

  const clearKeyframeSlot = useCallback((slot) => {
    const ref = keyframes[slot]
    const sourceId = ref?.nodeId
    updateKeyframes((k) => ({ ...k, [slot]: null }))
    // 仅外部画布源、且首尾帧/freeRefs 都不再引用该源时，再断开连线
    if (
      !sourceId
      || sourceId === nodeId
      || String(sourceId).startsWith("upload_")
      || String(sourceId).startsWith("asset_")
      || !data?.onDisconnectIncomingFromSource
    ) {
      return
    }
    const otherSlot = slot === "first" ? "last" : "first"
    const otherStillUses = keyframes[otherSlot]?.nodeId === sourceId
    const freeStillUses = (Array.isArray(freeRefs) ? freeRefs : []).some(
      (r) => r?.nodeId === sourceId
    )
    if (!otherStillUses && !freeStillUses) {
      data.onDisconnectIncomingFromSource(nodeId, sourceId)
    }
  }, [keyframes, freeRefs, data, nodeId, updateKeyframes])

  const applyKeyframePick = useCallback((slot, refItem) => {
    updateKeyframes((k) => ({ ...k, [slot]: refItem }))
    setKeyframePick(null)
  }, [updateKeyframes])

  const styleReference = data.styleReference || null
  const scriptTableNode = useMemo(() => {
    const ref = data.scriptTableRef
    if (ref?.nodeId) {
      return getNodes().find((n) => n.id === ref.nodeId) || null
    }
    return findScriptTableNode(getNodes())
  }, [data.scriptTableRef, getNodes])

  const qualityPresetId = resolveVideoQualityPresetId(
    data,
    scriptTableNode?.data || null
  )

  const handlePresetChange = useCallback(
    (presetId) => {
      data?.onUpdate?.(nodeId, { qualityPresetId: presetId, referenceSlotsOpen: true })
      onSlotsExpandedChange?.(true)
    },
    [data, nodeId, onSlotsExpandedChange]
  )

  const handleCameraMotionChange = useCallback(
    ({ cameraMove, shotScale, samplingProfile }) => {
      data?.onUpdate?.(nodeId, {
        cameraMove: cameraMove || "auto",
        shotScale: shotScale || "auto",
        samplingProfile: samplingProfile || "fast",
      })
    },
    [data, nodeId]
  )

  const cameraMove = data?.cameraMove || "auto"
  const shotScale = data?.shotScale || "auto"

  const cameraMotionSlot =
    localPanelMode === "enhance" ? null : (
      <CameraMotionPicker
        cameraMove={cameraMove}
        shotScale={shotScale}
        readOnly={readOnly}
        onChange={handleCameraMotionChange}
      />
    )

  const handleStyleReferenceChange = useCallback(
    (ref) => {
      onUpdate?.(nodeId, { styleReference: ref ?? null, referenceSlotsOpen: true })
      onSlotsExpandedChange?.(true)
    },
    [nodeId, onUpdate, onSlotsExpandedChange]
  )

  const styleRefModal = projectId ? (
    <VideoStyleReferencePanel
      open={styleRefOpen}
      onClose={() => setStyleRefOpen(false)}
      projectId={projectId}
      nodeId={nodeId}
      scriptTableRef={data.scriptTableRef || null}
      styleReference={styleReference}
      readOnly={readOnly}
      onStyleReferenceChange={handleStyleReferenceChange}
    />
  ) : null

  const tabExpandedClass = slotsExpanded ? " expanded" : ""

  const topBar = (
    <div className="video-top-bar nodrag nopan">
      <div className="mode-tabs nodrag nopan">
        <button
          type="button"
          className={`mode-tab nodrag nopan${effectivePanelMode === "t2v" ? ` active${tabExpandedClass}` : ""}`}
          onClick={() => setMode("t2v")}
          disabled={forceKeyframe}
          title={forceKeyframe ? "Wan Fun Inpaint 需使用首尾帧" : undefined}
        >
          {t("canvas.prompt.t2v")}
        </button>
        <button
          type="button"
          className={`mode-tab nodrag nopan${effectivePanelMode === "keyframe" ? ` active${tabExpandedClass}` : ""}`}
          onClick={() => setMode("keyframe")}
        >
          {t("canvas.prompt.keyframe")}
        </button>
        <button
          type="button"
          className={`mode-tab nodrag nopan${effectivePanelMode === "freeref" ? ` active${tabExpandedClass}` : ""}`}
          onClick={() => setMode("freeref")}
          disabled={forceKeyframe}
          title={forceKeyframe ? "Wan Fun Inpaint 需使用首尾帧" : undefined}
        >
          {t("canvas.image.slotFreeref")}
        </button>
        <button
          type="button"
          className={`mode-tab nodrag nopan${effectivePanelMode === "enhance" ? ` active${tabExpandedClass}` : ""}`}
          onClick={() => setMode("enhance")}
        >
          {t("canvas.video.enhance")}
        </button>
      </div>
      {effectivePanelMode !== "enhance" && !isT2vMode && (
        <>
          <div className="video-top-divider" aria-hidden />
          <div className="add-ref-wrapper">
            <RefPickerTrigger
              label={t("canvas.video.addRef")}
              labelWithCount={
                referenceMode === "freeref" ? t("canvas.video.addRefWithCount") : undefined
              }
              count={referenceMode === "freeref" ? freeRefs.length : 0}
              max={referenceMode === "freeref" ? 5 : undefined}
              disabled={referenceMode === "freeref" && freeRefs.length >= 5}
              showUpload={true}
              assetEntries={slotsExpanded ? assetEntries : []}
              onAssetPick={handleTopBarAssetPick}
              onQuickSelect={handleTopBarQuickSelect}
              onCanvasPick={openCanvasPicker}
              onUpload={handleTopBarUpload}
            />
          </div>
          {projectId && (
            <VideoStylePicker
              value={qualityPresetId}
              styleReference={styleReference}
              readOnly={readOnly}
              onPresetChange={handlePresetChange}
              onUploadClick={() => setStyleRefOpen(true)}
            />
          )}
        </>
      )}
      {isT2vMode && projectId && effectivePanelMode !== "enhance" && (
        <>
          <div className="video-top-divider" aria-hidden />
          <VideoStylePicker
            value={qualityPresetId}
            styleReference={styleReference}
            readOnly={readOnly}
            onPresetChange={handlePresetChange}
            onUploadClick={() => setStyleRefOpen(true)}
          />
        </>
      )}
    </div>
  )

  const slotsSection = (!slotsExpanded || isT2vMode || referenceMode === "t2v") ? null : referenceMode === "keyframe" ? (
        <div className="keyframe-slots nodrag nopan">
          <KeyframeSlot
            slotLabel={t("canvas.image.slotFirst")}
            value={keyframes.first}
            getNode={getNode}
            sourceFingerprint={sourceMediaById[keyframes.first?.nodeId] || ""}
            onQuickSelect={(item) => applyQuickToSlot(item, "first")}
            onCanvasPick={() => openCanvasPickerFor("first")}
            onUpload={(file) => uploadFileToSlot(file, "first")}
            onAssetPick={(asset) => applyAssetToSlot(asset, "first")}
            assetEntries={assetEntries}
            onClear={() => clearKeyframeSlot("first")}
            clearAriaLabel={t("canvas.video.clearSlot", { slot: t("canvas.image.slotFirst") })}
          />
          <KeyframeSlot
            slotLabel={t("canvas.image.slotLast")}
            value={keyframes.last}
            getNode={getNode}
            sourceFingerprint={sourceMediaById[keyframes.last?.nodeId] || ""}
            onQuickSelect={(item) => applyQuickToSlot(item, "last")}
            onCanvasPick={() => openCanvasPickerFor("last")}
            onUpload={(file) => uploadFileToSlot(file, "last")}
            onAssetPick={(asset) => applyAssetToSlot(asset, "last")}
            assetEntries={assetEntries}
            onClear={() => clearKeyframeSlot("last")}
            clearAriaLabel={t("canvas.video.clearSlot", { slot: t("canvas.image.slotLast") })}
          />
        </div>
      ) : (
        <div className="ref-tags-scroll nodrag nopan">
          {freeRefs.map((ref, i) => (
            <RefTag
              key={`${ref.nodeId}-${i}`}
              refItem={ref}
              getNode={getNode}
              sourceFingerprint={sourceMediaById[ref?.nodeId] || ""}
              label={truncateLabel(ref.label)}
              onRemove={() => removeFreeRef(i)}
            />
          ))}
          {freeRefs.length < 5 && (
            <RefPickAnchor
              className="freeref-add nodrag nopan"
              showUpload={true}
              assetEntries={assetEntries}
              onAssetPick={(asset) => applyAssetToSlot(asset, "freeref")}
              onQuickSelect={(item) => applyQuickToSlot(item, "freeref")}
              onCanvasPick={() => openCanvasPickerFor("freeref")}
              onUpload={(file) => uploadFileToSlot(file, "freeref")}
            >
              <span className="freeref-add-plus">+</span>
              <span className="freeref-add-text">{t("canvas.video.addRefShort")}</span>
            </RefPickAnchor>
          )}
        </div>
      )

  const keyframePickPop = keyframePick ? (
    <div className="keyframe-pick-pop nodrag nopan" onPointerDown={sp}>
      <p className="keyframe-pick-title">{t("canvas.video.pickSlot")}</p>
      <div className="keyframe-pick-actions">
        <button
          type="button"
          className="keyframe-pick-btn nodrag nopan"
          onClick={() => applyKeyframePick("first", keyframePick.ref)}
        >
          {t("canvas.image.slotFirst")}
        </button>
        <button
          type="button"
          className="keyframe-pick-btn nodrag nopan"
          onClick={() => applyKeyframePick("last", keyframePick.ref)}
        >
          {t("canvas.image.slotLast")}
        </button>
        <button
          type="button"
          className="keyframe-pick-btn keyframe-pick-btn--ghost nodrag nopan"
          onClick={() => setKeyframePick(null)}
        >
          {t("canvas.common.cancel")}
        </button>
      </div>
    </div>
  ) : null

  if (section === "topbar") {
    return (
      <>
        {topBar}
        {cameraMotionSlot}
        {styleRefModal}
      </>
    )
  }

  if (section === "promptbar") {
    const showSlotsMedia =
      slotsExpanded
      && localPanelMode !== "t2v"
      && !isT2vMode
      && (localPanelMode === "enhance" || slotsSection || keyframePickPop)
    return (
      <div className="video-ref-promptbar nodrag nopan">
        {topBar}
        {cameraMotionSlot}
        {showSlotsMedia ? (
          <div className="video-ref-promptbar-media">
            {localPanelMode === "enhance" ? (
              enhancePanelSlot
            ) : (
              <div className="video-ref-panel video-ref-panel--slots">
                {slotsSection}
                {keyframePickPop}
              </div>
            )}
          </div>
        ) : null}
        {styleRefModal}
      </div>
    )
  }

  if (section === "slots") {
    if (!slotsExpanded) return null
    if (localPanelMode === "t2v" || isT2vMode) return null
    if (localPanelMode === "enhance") {
      return enhancePanelSlot ? (
        <div className="video-ref-panel video-ref-panel--slots nodrag nopan" onPointerDown={sp} onClick={sp}>
          {enhancePanelSlot}
        </div>
      ) : null
    }
    return (
      <div className="video-ref-panel video-ref-panel--slots nodrag nopan" onPointerDown={sp} onClick={sp}>
        {slotsSection}
        {keyframePickPop}
      </div>
    )
  }

  return (
    <div className="video-ref-panel nodrag nopan" onPointerDown={sp} onClick={sp}>
      {topBar}
      {cameraMotionSlot}
      {slotsSection}
      {keyframePickPop}
      {styleRefModal}
    </div>
  )
}
