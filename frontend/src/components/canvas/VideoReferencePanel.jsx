import { useCallback, useEffect, useState } from "react"
import { useStore } from "reactflow"
import { useReferenceSelect } from "./CanvasActionsContext"
import RefPickerTrigger from "./RefPickerTrigger"
import AddRefHoverPanel, { RefPickAnchor } from "./AddRefHoverPanel"
import { DEFAULT_KEYFRAMES, truncateLabel, buildRefItem } from "./videoReferenceHelpers"
import { useMentionableItems } from "./promptMentions"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { uploadImageFile } from "../../services/uploadImage"
import useRefAssetEntries from "../../hooks/canvas/useRefAssetEntries"
import { useLocale } from "../../utils/locale"
import VideoStyleReferencePanel from "./VideoStyleReferencePanel"
import { styleReferenceSummary } from "../../utils/canvas/styleReferenceFormat"
import { IconStyleRef } from "./CanvasTopbarIcons"
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
}) {
  const { t } = useLocale()
  const refSelect = useReferenceSelect()
  const { assetEntries, ensureLoaded } = useRefAssetEntries()
  const [styleRefOpen, setStyleRefOpen] = useState(false)

  useEffect(() => {
    ensureLoaded()
  }, [ensureLoaded])

  const referenceMode = data.referenceMode || "keyframe"
  const [keyframes, setKeyframes] = useState(data.keyframes || DEFAULT_KEYFRAMES)
  const [freeRefs, setFreeRefs] = useState(data.freeRefs || [])

  const [keyframePick, setKeyframePick] = useState(null)

  useEffect(() => {
    setKeyframes(data.keyframes || DEFAULT_KEYFRAMES)
    setFreeRefs(data.freeRefs || [])
  }, [data.keyframes, data.freeRefs])

  const persist = useCallback((patch) => {
    data.onUpdate?.(nodeId, patch)
  }, [data, nodeId])

  const setMode = useCallback((mode) => {
    persist({
      referenceMode: mode,
      vidMode: mode === "freeref" ? "参考" : "首尾帧",
    })
  }, [persist])

  const updateKeyframes = useCallback((updater) => {
    setKeyframes((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater
      persist({ keyframes: next })
      return next
    })
  }, [persist])

  const updateFreeRefs = useCallback((updater) => {
    setFreeRefs((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater
      persist({ freeRefs: next })
      return next
    })
  }, [persist])

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
  const hasStyleRef = !!styleReference

  const handleStyleReferenceChange = useCallback(
    (ref) => {
      data.onUpdate?.(nodeId, { styleReference: ref ?? null })
    },
    [nodeId, data]
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

  const topBar = (
    <div className="video-top-bar nodrag nopan">
      <div className="mode-tabs nodrag nopan">
        <button
          type="button"
          className={`mode-tab nodrag nopan${referenceMode === "keyframe" ? " active" : ""}`}
          onClick={() => setMode("keyframe")}
        >
          {t("canvas.prompt.keyframe")}
        </button>
        <button
          type="button"
          className={`mode-tab nodrag nopan${referenceMode === "freeref" ? " active" : ""}`}
          onClick={() => setMode("freeref")}
        >
          {t("canvas.image.slotFreeref")}
        </button>
      </div>
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
          assetEntries={assetEntries}
          onAssetPick={handleTopBarAssetPick}
          onQuickSelect={handleTopBarQuickSelect}
          onCanvasPick={openCanvasPicker}
          onUpload={handleTopBarUpload}
        />
      </div>
      {projectId && (
        <button
          type="button"
          className={`video-style-ref-btn nodrag nopan${hasStyleRef ? " video-style-ref-btn--active" : ""}`}
          title={
            hasStyleRef
              ? styleReferenceSummary(styleReference)
              : t("canvas.styleRef.videoBtn")
          }
          onClick={(e) => {
            sp(e)
            setStyleRefOpen(true)
          }}
        >
          <IconStyleRef />
          <span className="video-style-ref-btn-label">{t("canvas.styleRef.videoBtnShort")}</span>
          {hasStyleRef ? <span className="video-style-ref-dot" aria-hidden /> : null}
        </button>
      )}
    </div>
  )

  const slotsSection = referenceMode === "keyframe" ? (
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
        {styleRefModal}
      </>
    )
  }

  if (section === "slots") {
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
      {slotsSection}
      {keyframePickPop}
      {styleRefModal}
    </div>
  )
}

/** 画布可引用元素列表（@ 提及） */
export function VideoAtMentionList({
  open,
  onSelect,
  onClose,
  query = "",
  excludeNodeId = null,
  compact = false,
}) {
  const { t } = useLocale()
  const candidates = useMentionableItems(excludeNodeId)

  const filtered = candidates.filter((c) => {
    const q = (query || "").toLowerCase()
    if (!q) return true
    return c.name.toLowerCase().includes(q)
  })

  if (!open) return null

  return (
    <div
      className={`video-at-mention nodrag nopan${compact ? " video-at-mention--compact" : ""}`}
      onPointerDown={sp}
    >
      {filtered.length === 0 ? (
        <div className="video-at-mention-empty">{t("canvas.video.noRefElements")}</div>
      ) : (
        filtered.slice(0, 8).map((c) => (
          <button
            key={`${c.id}_${c.image_index ?? 0}_${c.type}`}
            type="button"
            className="video-at-mention-item nodrag nopan"
            onClick={() => {
              onSelect?.(c)
              onClose?.()
            }}
          >
            {c.thumbUrl || c.imageUrl ? (
              c.type === "video" ? (
                <span className="video-at-mention-thumb video-at-mention-thumb--video">▶</span>
              ) : (
                <img
                  src={ensureMediaUrl(c.thumbUrl || c.imageUrl)}
                  alt=""
                  draggable={false}
                  style={{ pointerEvents: "none" }}
                />
              )
            ) : (
              <span className="video-at-mention-thumb video-at-mention-thumb--text">T</span>
            )}
            <span className="video-at-mention-label">
              <span className="video-at-mention-name">@{c.name}</span>
              {c.preview && (
                <span className="video-at-mention-preview">{c.preview}</span>
              )}
            </span>
          </button>
        ))
      )}
    </div>
  )
}
