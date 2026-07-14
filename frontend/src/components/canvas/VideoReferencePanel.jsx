import { useCallback, useEffect, useMemo, useState } from "react"
import { useReactFlow } from "reactflow"
import { useReferenceSelect } from "./CanvasActionsContext"
import RefPickerTrigger from "./RefPickerTrigger"
import AddRefHoverPanel, { RefPickAnchor } from "./AddRefHoverPanel"
import { DEFAULT_KEYFRAMES, truncateLabel, buildRefItem } from "./videoReferenceHelpers"
import { uploadImageFile } from "../../services/uploadImage"
import useRefAssetEntries from "../../hooks/canvas/useRefAssetEntries"
import { useLocale } from "../../utils/locale"
import VideoStyleReferencePanel from "./VideoStyleReferencePanel"
import VideoStylePicker from "./VideoStylePicker"
import CameraMotionPicker from "./CameraMotionPicker"
import { findScriptTableNode, resolveVideoQualityPresetId } from "../../utils/canvas/scriptTableNode"
import "./VideoStylePicker.css"
import "./CameraMotionPicker.css"
import "./VideoReferencePanel.css"
import "./CanvasImageQuickPicker.css"

const sp = (e) => e.stopPropagation()

function itemToRefItem(item) {
  return buildRefItem({
    nodeId: item.nodeId,
    imageIndex: item.imageIndex ?? 0,
    imageUrl: item.url,
    imageId: item.imageId,
    label: item.label,
  })
}

function KeyframeSlot({
  slotLabel,
  value,
  onQuickSelect,
  onCanvasPick,
  onUpload,
  onClear,
  clearAriaLabel,
  assetEntries = [],
  onAssetPick,
}) {
  if (value) {
    return (
      <div className="keyframe-slot keyframe-slot--filled nodrag nopan">
        <img
          src={value.imageUrl}
          alt=""
          draggable={false}
          onDragStart={(e) => e.preventDefault()}
          style={{ pointerEvents: "none" }}
        />
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
  const { getNodes } = useReactFlow()
  const refSelect = useReferenceSelect()
  const { assetEntries, ensureLoaded } = useRefAssetEntries()
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

  useEffect(() => {
    if (slotsExpanded) ensureLoaded()
  }, [slotsExpanded, ensureLoaded])

  const persist = useCallback((patch, { rememberSlots = false } = {}) => {
    const next = rememberSlots ? { ...patch, referenceSlotsOpen: true } : patch
    onUpdate?.(nodeId, next)
  }, [onUpdate, nodeId])

  const handleModeClick = useCallback((mode) => {
    if (localPanelMode === mode) {
      const nextExpanded = !slotsExpanded
      onSlotsExpandedChange?.(nextExpanded)
      if (!nextExpanded) {
        if (data?.referenceSlotsOpen) {
          persist({ referenceSlotsOpen: false })
        }
        if (mode === "enhance") {
          const refMode = referenceModeFromData || "keyframe"
          setLocalPanelMode(refMode)
          persist({ panelMode: refMode, referenceSlotsOpen: false })
        }
      }
      return
    }
    setLocalPanelMode(mode)
    if (mode === "enhance") {
      persist({ panelMode: "enhance" }, { rememberSlots: true })
      onSlotsExpandedChange?.(true)
      return
    }
    persist({
      panelMode: mode,
      referenceMode: mode,
      vidMode: mode === "freeref" ? "参考" : mode === "t2v" ? "文生" : "首尾帧",
    })
    onSlotsExpandedChange?.(true)
  }, [
    localPanelMode,
    slotsExpanded,
    onSlotsExpandedChange,
    persist,
    data?.referenceSlotsOpen,
    referenceModeFromData,
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
      if (slot === "freeref") {
        updateFreeRefs((refs) => {
          if (refs.length >= 5 || refs.some((r) => r.imageId === refItem.imageId)) return refs
          return [...refs, refItem]
        })
        return
      }
      updateKeyframes((k) => ({ ...k, [slot]: refItem }))
    },
    [updateKeyframes, updateFreeRefs]
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
        const refItem = buildRefItem({
          nodeId,
          imageIndex: 0,
          imageUrl: url,
          imageId: `${nodeId}_upload_${Date.now()}`,
          label: t("canvas.prompt.uploadImage"),
        })
        applyRefItemToSlot(refItem, slot)
      } catch (err) {
        console.error("参考图上传失败", err)
      }
    },
    [nodeId, applyRefItemToSlot, t]
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
    updateFreeRefs((refs) => refs.filter((_, i) => i !== index))
  }, [updateFreeRefs])

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
            onQuickSelect={(item) => applyQuickToSlot(item, "first")}
            onCanvasPick={() => openCanvasPickerFor("first")}
            onUpload={(file) => uploadFileToSlot(file, "first")}
            onAssetPick={(asset) => applyAssetToSlot(asset, "first")}
            assetEntries={assetEntries}
            onClear={() => updateKeyframes((k) => ({ ...k, first: null }))}
            clearAriaLabel={t("canvas.video.clearSlot", { slot: t("canvas.image.slotFirst") })}
          />
          <KeyframeSlot
            slotLabel={t("canvas.image.slotLast")}
            value={keyframes.last}
            onQuickSelect={(item) => applyQuickToSlot(item, "last")}
            onCanvasPick={() => openCanvasPickerFor("last")}
            onUpload={(file) => uploadFileToSlot(file, "last")}
            onAssetPick={(asset) => applyAssetToSlot(asset, "last")}
            assetEntries={assetEntries}
            onClear={() => updateKeyframes((k) => ({ ...k, last: null }))}
            clearAriaLabel={t("canvas.video.clearSlot", { slot: t("canvas.image.slotLast") })}
          />
        </div>
      ) : (
        <div className="ref-tags-scroll nodrag nopan">
          {freeRefs.map((ref, i) => (
            <div key={`${ref.nodeId}-${i}`} className="ref-tag nodrag nopan">
              <img
                src={ref.imageUrl}
                alt=""
                draggable={false}
                onDragStart={(e) => e.preventDefault()}
              />
              <span className="ref-label">{truncateLabel(ref.label)}</span>
              <button
                type="button"
                className="ref-remove nodrag nopan"
                onClick={(e) => { sp(e); removeFreeRef(i) }}
              >
                ×
              </button>
            </div>
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
    return (
      <div className="video-ref-promptbar nodrag nopan">
        {topBar}
        {cameraMotionSlot}
        {slotsExpanded ? (
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
