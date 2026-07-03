import { useState, useCallback, useEffect, useRef, useMemo } from "react"
import { useReactFlow, useStore } from "reactflow"
import { useReferenceSelect } from "./CanvasActionsContext"
import VideoReferencePanel from "./VideoReferencePanel"
import { VideoAtMentionList } from "./VideoAtMentionList"
import VideoEnhancePanel from "./VideoEnhancePanel"
import {
  getVideoEnhanceBridge,
  subscribeVideoEnhanceBridge,
} from "./videoEnhanceBridge"
import MentionTextarea from "./MentionTextarea"
import { useCanvasStore, useModelStore } from "../../stores"
import api, { API_BASE } from "../../services/api"
import { uploadImageFile } from "../../services/uploadImage"
import { Mic } from "lucide-react"
import RefPickerTrigger from "./RefPickerTrigger"
import PromptRefChips from "./PromptRefChips"
import PromptBarShell from "./PromptBarShell"
import { closeCanvasDropdown, openCanvasDropdown } from "./canvasDropdownCoordinator"
import useRefAssetEntries from "../../hooks/canvas/useRefAssetEntries"
import { getPromptExpanded, setPromptExpanded } from "../../utils/canvas/promptBarPrefs"
import {
  buildRefItem,
  getReferenceImagesList,
  getResolvedReferenceImagesList,
  appendReferenceImage,
  getImageNodeImages,
  MAX_REFERENCE_IMAGES,
} from "./videoReferenceHelpers"
import useModelCapabilities from "../../hooks/useModelCapabilities"
import {
  mergeMentionRefsIntoFreeRefs,
  mergeMentionRefsIntoReferenceImages,
  syncFreeRefsWithMentions,
  syncMentionRefsIntoReferenceImages,
  filterMentionsAfterRefRemoved,
  removeMentionFromPrompt,
} from "./promptMentions"
import { TEXT_MODES } from "../../utils/canvas/nodeHelpers"
import { TEXT_CLASSIFY_MIN } from "../../utils/canvas/promptIntentConfig"
import { usePromptIntentGate } from "./PromptIntentGateContext"
import { useLocale } from "../../utils/locale"
import { appendStyleReferenceToDescription } from "../../utils/canvas/styleReferenceFormat"
import "./NodeBanner.css"
import "./PromptRefChips.css"
import "./VideoReferencePanel.css"

// ── Image config ──────────────────────────────────────────
const DEFAULT_IMAGE_RESOLUTIONS = ["1024x1024", "512x512", "768x768"]
const IMAGE_RATIOS = [
  { key: "1:1",   w: 1, h: 1 },
  { key: "4:3",   w: 4, h: 3 },
  { key: "3:4",   w: 3, h: 4 },
  { key: "16:9",  w: 16, h: 9 },
  { key: "9:16",  w: 9, h: 16 },
  { key: "3:2",   w: 3, h: 2 },
  { key: "2:3",   w: 2, h: 3 },
  { key: "21:9",  w: 21, h: 9 },
]
const VIDEO_MODES   = ["首尾帧", "参考"]
const VIDEO_RATIOS  = [
  { key: "16:9", w: 16, h: 9 },
  { key: "9:16", w: 9, h: 16 },
  { key: "1:1",  w: 1,  h: 1  },
]
const VIDEO_QUALITIES = ["720P", "1080P"]
const VIDEO_AUDIOS    = ["开启", "关闭"]

const PARAM_PANEL_CLOSE_EVENT = "canvas-close-param-panels"

// ── Text config ───────────────────────────────────────────
const COUNT_OPTIONS = [1, 2, 3, 4]

const BAR_OFFSET_Y = 16
const BANNER_WIDTH = 680
const sp = (e) => e.stopPropagation()

// ── SVG helpers ───────────────────────────────────────────
const SparkleIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="currentColor">
    <path d="M6.5 0L7.8 4.7 12.5 6.5 7.8 8.3 6.5 13 5.2 8.3 0.5 6.5 5.2 4.7Z"/>
  </svg>
)
const CreditIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <circle cx="6.5" cy="6.5" r="5.5" stroke="currentColor" strokeWidth="1.2"/>
    <path d="M4.5 6.5h4M6.5 4.5v4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
  </svg>
)
const BarChartIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <rect x="1" y="7" width="2.5" height="5" rx="0.8" fill="currentColor" opacity="0.6"/>
    <rect x="5.2" y="4" width="2.5" height="8" rx="0.8" fill="currentColor" opacity="0.8"/>
    <rect x="9.4" y="1" width="2.5" height="11" rx="0.8" fill="currentColor"/>
  </svg>
)
const SpinIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
    <path d="M7 1.5A5.5 5.5 0 1 1 2.5 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    <path d="M2.5 6V9H5.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)
/** 几何居中发送箭头（替代 Lucide ArrowUp，避免视口留白导致偏位） */
const SendArrowIcon = () => (
  <svg width="16" height="16" viewBox="0 0 14 14" fill="none" aria-hidden>
    <path
      d="M7 2.5v9M4.25 5.5L7 2.5 9.75 5.5"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)
const SoundIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <path d="M2 4.5h2l3-3v10l-3-3H2z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
    <path d="M10 3.5c1.2 1 1.2 5 0 6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
    <path d="M8.5 5c.5.5.5 3 0 3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
  </svg>
)
const InfoIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{display:"inline",verticalAlign:"middle",marginLeft:3}}>
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.1" opacity="0.5"/>
    <path d="M6 5.5v3M6 4v.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" opacity="0.5"/>
  </svg>
)

// ── Ratio SVG icon (proportional rectangle) ───────────────
const RatioIcon = ({ w, h, size = 18 }) => {
  const maxD = Math.max(w, h)
  const rw = Math.round((w / maxD) * size)
  const rh = Math.round((h / maxD) * size)
  const vw = size + 4, vh = size + 4
  const x = (vw - rw) / 2, y = (vh - rh) / 2
  return (
    <svg width={vw} height={vh} viewBox={`0 0 ${vw} ${vh}`} fill="none">
      <rect x={x} y={y} width={rw} height={rh} rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
    </svg>
  )
}

// ── Segmented selector ────────────────────────────────────
const SegmentGroup = ({ options, value, onChange, renderLabel }) => (
  <div className="nb-seg-group">
    {options.map((opt) => {
      const key = typeof opt === "string" ? opt : opt.key
      const isActive = value === key
      return (
        <button
          key={key}
          className={`nb-seg-item nodrag${isActive ? " nb-seg-item--active" : ""}`}
          onPointerDown={sp}
          onClick={(e) => { sp(e); onChange(key) }}
        >
          {renderLabel ? renderLabel(opt) : key}
        </button>
      )
    })}
  </div>
)

// Attaches a native (non-passive) wheel listener to block Ctrl+wheel browser zoom
function useBlockCtrlWheel(ref) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const handler = (e) => {
      if (e.ctrlKey) { e.preventDefault(); e.stopPropagation() }
    }
    el.addEventListener("wheel", handler, { passive: false })
    return () => el.removeEventListener("wheel", handler)
  }, [ref])
}

// Returns { shown, closing } – delays unmount by 150ms for exit animation
function usePanelClose(open) {
  const [shown,   setShown]   = useState(open)
  const [closing, setClosing] = useState(false)
  const timerRef = useRef(null)
  useEffect(() => {
    clearTimeout(timerRef.current)
    if (open) { setShown(true); setClosing(false) }
    else if (shown) {
      setClosing(true)
      timerRef.current = setTimeout(() => { setShown(false); setClosing(false) }, 150)
    }
    return () => clearTimeout(timerRef.current)
  }, [open])
  return { shown, closing }
}

function resolveRatioMeta(key) {
  const known = IMAGE_RATIOS.find((r) => r.key === key)
  if (known) return known
  const parts = String(key).split(":").map(Number)
  if (parts.length === 2 && parts[0] > 0 && parts[1] > 0) {
    return { key, w: parts[0], h: parts[1] }
  }
  return { key: key || "1:1", w: 1, h: 1 }
}

function ImagePanelContent({
  capabilities,
  loading,
  imgRatio,
  setImgRatio,
  imgResolution,
  setImgResolution,
}) {
  const { t } = useLocale()
  const panelRef = useRef(null)
  useBlockCtrlWheel(panelRef)

  if (loading) {
    return (
      <div ref={panelRef} className="nb-panel nb-panel--loading" onPointerDown={sp}>
        {t("canvas.common.loading")}
      </div>
    )
  }

  const resolutions = capabilities?.resolutions?.length
    ? capabilities.resolutions
    : DEFAULT_IMAGE_RESOLUTIONS
  const aspectKeys = capabilities?.aspect_ratios?.length
    ? capabilities.aspect_ratios
    : IMAGE_RATIOS.map((r) => r.key)

  const ratioOptions = aspectKeys.map(resolveRatioMeta)

  return (
    <div ref={panelRef} className="nb-panel nb-panel--image-params" onPointerDown={sp}>
      <div className="nb-panel-label">{t("canvas.prompt.clarity")}</div>
      <div className="nb-param-seg">
        {resolutions.map((res) => (
          <button
            key={res}
            type="button"
            className={`nb-param-chip nodrag${imgResolution === res ? " nb-param-chip--active" : ""}`}
            onPointerDown={sp}
            onClick={(e) => { sp(e); setImgResolution(res) }}
          >
            {res}
          </button>
        ))}
      </div>
      <div className="nb-panel-label nb-panel-label--spaced">{t("canvas.prompt.ratio")}</div>
      <div className="nb-ratio-grid nb-ratio-grid--image">
        {ratioOptions.map((r) => (
          <button
            key={r.key}
            type="button"
            className={`nb-ratio-item nb-ratio-item--image nodrag${imgRatio === r.key ? " nb-ratio-item--active" : ""}`}
            onPointerDown={sp}
            onClick={(e) => { sp(e); setImgRatio(r.key) }}
          >
            <RatioIcon w={r.w} h={r.h} size={22} />
            <span>{r.key}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function VideoPanelContent({
  capabilities,
  loading,
  vidMode,
  setVidMode,
  vidRatio,
  setVidRatio,
  vidQuality,
  setVidQuality,
  vidDuration,
  setVidDuration,
  vidAudio,
  setVidAudio,
}) {
  const { t } = useLocale()
  const panelRef = useRef(null)
  useBlockCtrlWheel(panelRef)

  const renderVidModeLabel = (opt) => (
    <>
      {opt === "参考" ? t("canvas.prompt.freeref") : t("canvas.prompt.keyframe")}
      {opt === "参考" && <InfoIcon />}
    </>
  )

  const renderAudioLabel = (opt) => (
    opt === "开启" ? t("canvas.common.on") : t("canvas.common.off")
  )

  if (loading) {
    return (
      <div ref={panelRef} className="nb-panel nb-panel--loading" onPointerDown={sp}>
        {t("canvas.prompt.loadingModels")}
      </div>
    )
  }

  const aspectKeys = capabilities?.aspect_ratios ?? []
  const ratioOptions = aspectKeys.map(resolveRatioMeta)
  const durationOptions = (capabilities?.durations ?? []).map((d) => `${d}s`)

  return (
    <div ref={panelRef} className="nb-panel" onPointerDown={sp}>
      <div className="nb-panel-label">{t("canvas.prompt.genMode")}</div>
      <SegmentGroup
        options={VIDEO_MODES}
        value={vidMode}
        onChange={setVidMode}
        renderLabel={renderVidModeLabel}
      />
      {ratioOptions.length > 0 && (
        <>
          <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.ratio")}</div>
          <div className="nb-ratio-grid nb-ratio-grid--video">
            {ratioOptions.map((r) => (
              <button
                key={r.key}
                type="button"
                className={`nb-ratio-item nodrag${vidRatio === r.key ? " nb-ratio-item--active" : ""}`}
                onPointerDown={sp}
                onClick={(e) => { sp(e); setVidRatio(r.key) }}
              >
                <RatioIcon w={r.w} h={r.h} size={22} />
                <span>{r.key}</span>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.clarity")}</div>
      <SegmentGroup options={VIDEO_QUALITIES} value={vidQuality} onChange={setVidQuality} />
      {durationOptions.length > 0 && (
        <>
          <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.duration")}</div>
          <SegmentGroup options={durationOptions} value={vidDuration} onChange={setVidDuration} />
        </>
      )}
      <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.audio")}<InfoIcon /></div>
      <SegmentGroup
        options={VIDEO_AUDIOS}
        value={vidAudio}
        onChange={setVidAudio}
        renderLabel={renderAudioLabel}
      />
    </div>
  )
}

export default function CanvasPromptBar({
  selectedNodeId,
  selectedNodeType,
  onGenerate,
  onClearSelection,
  projectId = null,
  readOnly = false,
}) {
  const { getNode, getNodes } = useReactFlow()
  const transform   = useStore((s) => s.transform)
  const textModels  = useModelStore((s) => s.textModels)
  const imageModels = useModelStore((s) => s.imageModels)
  const videoModels = useModelStore((s) => s.videoModels)
  const modelsLoading = useModelStore((s) => s.loading)
  const modelsError   = useModelStore((s) => s.error)
  const [sending, setSending] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const { requestIntentGate } = usePromptIntentGate()
  const { t } = useLocale()

  const isText  = selectedNodeType === "text-note"
  const isVideo = selectedNodeType === "video-gen"
  const isImage = selectedNodeType === "image-gen"
  const isTextResponse = selectedNodeType === "text-response"

  const { assetEntries, ensureLoaded } = useRefAssetEntries()
  useEffect(() => {
    if (isImage || isVideo) ensureLoaded()
  }, [isImage, isVideo, ensureLoaded])

  // ── Shared state ──────────────────────────────────────
  const [prompt,        setPrompt]        = useState("")
  const promptBarSync   = useCanvasStore((s) => s.promptBarSync)
  const [mentions,      setMentions]      = useState([])
  const [visible,       setVisible]       = useState(false)
  const [mounted,       setMounted]       = useState(false)
  const [count,         setCount]         = useState(1)
  const [countDropOpen, setCountDropOpen] = useState(false)
  const [micActive,     setMicActive]     = useState(false)
  // text
  const [textModel,     setTextModel]     = useState("")
  const [textModelOpen, setTextModelOpen] = useState(false)
  // image
  const [imgModel,      setImgModel]      = useState("")
  const [imgModelOpen,  setImgModelOpen]  = useState(false)
  const [imgQuality,    setImgQuality]    = useState("2K")
  const [imgRatio,      setImgRatio]      = useState("1:1")
  const [imgResolution, setImgResolution] = useState("1024x1024")
  const [imgSteps,      setImgSteps]      = useState(20)
  const [imgCfg,        setImgCfg]        = useState(7)
  const [imgPanelOpen,  setImgPanelOpen]  = useState(false)
  // video
  const [vidModel,      setVidModel]      = useState("")
  const [vidModelOpen,  setVidModelOpen]  = useState(false)
  const [vidMode,       setVidMode]       = useState("首尾帧")
  const [vidRatio,      setVidRatio]      = useState("16:9")
  const [vidQuality,    setVidQuality]    = useState("1080P")
  const [vidDuration,   setVidDuration]   = useState("5s")
  const [vidAudio,      setVidAudio]      = useState("开启")
  const [vidPanelOpen,  setVidPanelOpen]  = useState(false)
  const [referenceSlotsExpanded, setReferenceSlotsExpanded] = useState(false)
  const [enhanceBridgeTick, setEnhanceBridgeTick] = useState(0)
  const [atMentionOpen, setAtMentionOpen]   = useState(false)
  const [atMentionQuery, setAtMentionQuery] = useState("")
  const [atMentionAnchor, setAtMentionAnchor] = useState(null)
  const [isExpanded,    setIsExpanded]    = useState(false)
  const [textMode,      setTextMode]      = useState(TEXT_MODES.CHAT)

  const hideTimerRef   = useRef(null)
  const refUploadInputRef = useRef(null)
  const textareaWrapRef = useRef(null)
  const mentionEditorRef = useRef(null)
  const recognitionRef = useRef(null)

  const bottombarRef = useRef(null)

  const refSelect = useReferenceSelect()

  const { capabilities: imgCapabilities, loading: imgCapLoading } = useModelCapabilities(
    isImage ? imgModel : null
  )
  const { capabilities: vidCapabilities, loading: vidCapLoading } = useModelCapabilities(
    isVideo ? vidModel : null
  )

  const exitPickerIfActive = useCallback(() => {
    if (refSelect?.mode?.active) {
      refSelect.resetReferencePickerState?.()
      refSelect.exit()
    }
  }, [refSelect])

  useEffect(() => subscribeVideoEnhanceBridge(() => setEnhanceBridgeTick((n) => n + 1)), [])

  useEffect(() => {
    const anyOpen =
      countDropOpen || textModelOpen || imgModelOpen || imgPanelOpen || vidModelOpen || vidPanelOpen
    if (!anyOpen) return undefined
    const closeSelf = () => {
      setCountDropOpen(false)
      setTextModelOpen(false)
      setImgModelOpen(false)
      setImgPanelOpen(false)
      setVidModelOpen(false)
      setVidPanelOpen(false)
    }
    openCanvasDropdown(closeSelf)
    return () => closeCanvasDropdown(closeSelf)
  }, [countDropOpen, textModelOpen, imgModelOpen, imgPanelOpen, vidModelOpen, vidPanelOpen])

  useEffect(() => {
    if (!atMentionOpen) return undefined
    const handler = (e) => {
      if (e.target.closest?.(".video-at-mention")) return
      if (textareaWrapRef.current?.contains(e.target)) return
      setAtMentionOpen(false)
      setAtMentionQuery("")
      setAtMentionAnchor(null)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [atMentionOpen])

  useEffect(() => {
    clearTimeout(hideTimerRef.current)
    if (selectedNodeId) {
      setMounted(true)
      requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
    } else {
      setVisible(false)
      setSubmitted(false)
      setIsExpanded(false)
      hideTimerRef.current = setTimeout(() => setMounted(false), 280)
    }
    return () => clearTimeout(hideTimerRef.current)
  }, [selectedNodeId])

  useEffect(() => {
    const variant =
      selectedNodeType === "text-note" || selectedNodeType === "text-response"
        ? "text"
        : selectedNodeType === "image-gen"
          ? "image"
          : selectedNodeType === "video-gen"
            ? "video"
            : null
    setIsExpanded(variant ? getPromptExpanded(variant) : false)
    setAtMentionOpen(false)
    setAtMentionQuery("")
    setTextModelOpen(false)
    setImgModelOpen(false)
    setVidModelOpen(false)
    setCountDropOpen(false)
    setImgPanelOpen(false)
    setVidPanelOpen(false)
  }, [selectedNodeId, selectedNodeType])

  useEffect(() => {
    if (!imgCapabilities || !isImage) return
    const ar = imgCapabilities.aspect_ratios
    if (ar?.length && !ar.includes(imgRatio)) setImgRatio(ar[0])
    const res = imgCapabilities.resolutions
    if (res?.length && !res.includes(imgResolution)) setImgResolution(res[0])
  }, [imgCapabilities, isImage, imgRatio, imgResolution])

  const closePromptOverlays = useCallback(() => {
    setTextModelOpen(false)
    setImgModelOpen(false)
    setVidModelOpen(false)
    setCountDropOpen(false)
    setImgPanelOpen(false)
    setVidPanelOpen(false)
    setAtMentionOpen(false)
    setAtMentionQuery("")
  }, [])

  useEffect(() => {
    if (!visible) return undefined
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        closePromptOverlays()
        return
      }
      if (e.key !== "Tab" || !bottombarRef.current) return
      const bar = bottombarRef.current
      if (!bar.contains(document.activeElement)) return
      const focusable = [...bar.querySelectorAll("button:not([disabled])")]
      if (focusable.length < 2) return
      const idx = focusable.indexOf(document.activeElement)
      if (idx === -1) return
      e.preventDefault()
      const next = e.shiftKey
        ? focusable[(idx - 1 + focusable.length) % focusable.length]
        : focusable[(idx + 1) % focusable.length]
      next?.focus()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [visible, closePromptOverlays])

  useEffect(() => {
    if (!vidCapabilities || !isVideo) return
    const ar = vidCapabilities.aspect_ratios
    if (ar?.length && !ar.includes(vidRatio)) setVidRatio(ar[0])
    const durations = (vidCapabilities.durations ?? []).map((d) => `${d}s`)
    if (durations.length && !durations.includes(vidDuration)) setVidDuration(durations[0])
  }, [vidCapabilities, isVideo, vidRatio, vidDuration])

  // 与节点 data.prompt 同步（含旧字段 content）
  useEffect(() => {
    if (!selectedNodeId) return
    const n = getNode(selectedNodeId)
    if (!n) return
    const isPromptNode =
      n.type === "text-note" || n.type === "text-response"
    const fromNode =
      n.data?.prompt ??
      n.data?.displayPrompt ??
      (isPromptNode ? (n.data?.content ?? "") : "") ??
      ""
    setPrompt(fromNode)
    setMentions(Array.isArray(n.data?.mentions) ? n.data.mentions : [])
    if (isPromptNode && fromNode && !n.data?.prompt && n.data?.onUpdate) {
      n.data.onUpdate(selectedNodeId, { prompt: fromNode })
    }
    if (n.data?.modelId) {
      if (isImage) setImgModel(n.data.modelId)
      else if (isVideo) setVidModel(n.data.modelId)
      else if (isText) setTextModel(n.data.modelId)
    }
    if (typeof n.data?.count === "number" && n.data.count >= 1) {
      setCount(n.data.count)
    }
    if (isText) {
      setTextMode(
        n.data?.textMode === TEXT_MODES.SCREENPLAY
          ? TEXT_MODES.SCREENPLAY
          : TEXT_MODES.CHAT
      )
    }
    if (isVideo) {
      if (n.data?.referenceMode === "freeref") setVidMode("参考")
      else if (n.data?.referenceMode === "keyframe") setVidMode("首尾帧")
      else if (n.data?.vidMode) setVidMode(n.data.vidMode)
      setReferenceSlotsExpanded(!!n.data?.referenceSlotsOpen)
      if (n.data?.vidRatio) setVidRatio(n.data.vidRatio)
      if (n.data?.vidQuality) setVidQuality(n.data.vidQuality)
      if (n.data?.vidDuration) setVidDuration(n.data.vidDuration)
      if (n.data?.vidAudio) setVidAudio(n.data.vidAudio)
    }
    if (isImage) {
      if (n.data?.imgQuality) setImgQuality(n.data.imgQuality)
      if (n.data?.imgRatio) setImgRatio(n.data.imgRatio)
      if (n.data?.imgResolution) setImgResolution(n.data.imgResolution)
    }
  }, [selectedNodeId, selectedNodeType, getNode, isImage, isVideo, isText])

  useEffect(() => {
    if (!selectedNodeId || !promptBarSync?.nodeId) return
    if (promptBarSync.nodeId !== selectedNodeId) return
    setPrompt(promptBarSync.text ?? "")
  }, [promptBarSync, selectedNodeId])

  const closeAllParamPanels = useCallback(() => {
    setCountDropOpen(false)
    setTextModelOpen(false)
    setImgModelOpen(false)
    setImgPanelOpen(false)
    setVidModelOpen(false)
    setVidPanelOpen(false)
  }, [])

  // 点击卡片外 / 画布空白 / 非面板区域时收起（capture 避免 nb-banner stopPropagation）
  useEffect(() => {
    const anyOpen = countDropOpen || textModelOpen || imgModelOpen || imgPanelOpen
      || vidModelOpen || vidPanelOpen
    if (!anyOpen) return
    const closeOnOutside = (e) => {
      if (e.target.closest(
        ".nb-dropup-menu, .nb-panel, .nb-model-btn, .nb-speed-btn, .nb-ratio-btn, .nb-model-btn-bare"
      )) return
      closeAllParamPanels()
    }
    document.addEventListener("pointerdown", closeOnOutside, true)
    return () => document.removeEventListener("pointerdown", closeOnOutside, true)
  }, [countDropOpen, textModelOpen, imgModelOpen, imgPanelOpen, vidModelOpen, vidPanelOpen, closeAllParamPanels])

  useEffect(() => {
    window.addEventListener(PARAM_PANEL_CLOSE_EVENT, closeAllParamPanels)
    return () => window.removeEventListener(PARAM_PANEL_CLOSE_EVENT, closeAllParamPanels)
  }, [closeAllParamPanels])

  // Sync model selection when API data arrives or node type changes
  useEffect(() => {
    if (isText  && !textModel  && textModels.length  > 0) setTextModel(textModels[0].id)
    if (isImage && !imgModel   && imageModels.length > 0) setImgModel(imageModels[0].id)
    if (isVideo && !vidModel   && videoModels.length > 0) setVidModel(videoModels[0].id)
  }, [isText, isImage, isVideo, textModels, imageModels, videoModels])

  const node = mounted ? getNode(selectedNodeId) : null

  const syncVideoNodePatch = useCallback((patch) => {
    if (!selectedNodeId || !node?.data?.onUpdate) return
    node.data.onUpdate(selectedNodeId, patch)
  }, [selectedNodeId, node])

  const handleVidModeChange = useCallback((mode) => {
    setVidMode(mode)
    syncVideoNodePatch({
      vidMode: mode,
      referenceMode: mode === "参考" ? "freeref" : "keyframe",
    })
  }, [syncVideoNodePatch])

  const handleTextModeChange = useCallback(
    (mode) => {
      setTextMode(mode)
      if (selectedNodeId && node?.data?.onUpdate) {
        node.data.onUpdate(selectedNodeId, { textMode: mode })
      }
    },
    [selectedNodeId, node]
  )

  const handleCountChange = useCallback((n) => {
    setCount(n)
    if (selectedNodeId && node?.data?.onUpdate) {
      node.data.onUpdate(selectedNodeId, { count: n, expectedCount: n })
    }
  }, [selectedNodeId, node])

  const referenceImages = useMemo(() => {
    if (!isImage || !node?.data) return []
    const synced = syncMentionRefsIntoReferenceImages(
      getReferenceImagesList(node.data),
      mentions,
      getNode
    )
    return getResolvedReferenceImagesList({ referenceImages: synced }, getNode)
  }, [
    isImage,
    node?.data?.referenceImages,
    node?.data?.referenceImageUrl,
    node?.data?.referenceImage,
    mentions,
    getNode,
  ])
  const referenceImageUrl = referenceImages[0]?.imageUrl || null
  const refAtMax = referenceImages.length >= MAX_REFERENCE_IMAGES

  const openReferencePicker = useCallback(() => {
    if (!selectedNodeId || refAtMax) return
    const mode = refSelect?.mode
    if (
      mode?.active
      && mode.sourceNodeId === selectedNodeId
      && mode.pickTarget === "referenceImage"
    ) {
      return
    }
    refSelect?.enter(selectedNodeId, "referenceImage")
  }, [selectedNodeId, refSelect, refAtMax])

  const syncReferenceImages = useCallback(
    (nextList) => {
      if (!selectedNodeId || !node?.data?.onUpdate) return
      const first = nextList[0] || null
      node.data.onUpdate(selectedNodeId, {
        referenceImages: nextList,
        referenceImage: first?.imageUrl ?? null,
        referenceImageUrl: first?.imageUrl ?? null,
        referenceRef: first,
      })
    },
    [selectedNodeId, node]
  )

  const handleQuickRefSelect = useCallback(
    (item) => {
      if (!selectedNodeId || !node?.data?.onUpdate) return
      const refItem = buildRefItem({
        nodeId: item.nodeId,
        imageIndex: item.imageIndex,
        imageUrl: item.url,
        imageId: item.imageId,
        label: item.label,
      })
      const next = appendReferenceImage(getReferenceImagesList(node.data), refItem)
      syncReferenceImages(next)
    },
    [selectedNodeId, node, syncReferenceImages]
  )

  const handleRefUploadFile = useCallback(async (file) => {
    if (!file || refAtMax || !selectedNodeId || !node?.data?.onUpdate) return
    try {
      const url = await uploadImageFile(file)
      const refItem = buildRefItem({
        nodeId: selectedNodeId,
        imageIndex: 0,
        imageUrl: url,
        imageId: `${selectedNodeId}_upload`,
        label: t("canvas.prompt.uploadImage"),
      })
      const next = appendReferenceImage(getReferenceImagesList(node.data), refItem)
      syncReferenceImages(next)
    } catch (err) {
      console.error("参考图上传失败", err)
    }
  }, [selectedNodeId, node, refAtMax, syncReferenceImages, t])

  const handleRefUpload = useCallback(async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (file) await handleRefUploadFile(file)
  }, [handleRefUploadFile])

  const handleAssetRefPick = useCallback(
    (asset) => {
      if (!asset?.imageUrl || refAtMax || !selectedNodeId || !node?.data?.onUpdate) return
      const refItem = buildRefItem({
        nodeId: `asset_${asset.id}`,
        imageIndex: 0,
        imageUrl: asset.imageUrl,
        imageId: asset.id,
        label: asset.name,
      })
      const next = appendReferenceImage(getReferenceImagesList(node.data), refItem)
      syncReferenceImages(next)
    },
    [selectedNodeId, node, refAtMax, syncReferenceImages]
  )

  const modelLabel = (list, selected, fallback) => {
    if (modelsLoading) return t("canvas.common.loading")
    if (modelsError) return t("canvas.prompt.loadFail")
    if (list.length === 0) return t("canvas.prompt.noModels")
    return list.find((m) => m.id === selected)?.display_name || selected || fallback
  }

  const activeModel = isText ? textModel : isImage ? imgModel : vidModel

  const nodeGenerating = node?.data?.status === "pending"
    || node?.data?.status === "generating"

  const isSendDisabled = readOnly || sending || submitted || nodeGenerating || isTextResponse || !prompt?.trim() ||
    (isText  && (textModels.length === 0 || !textModel)) ||
    (isImage && (imageModels.length === 0 || !imgModel)) ||
    (isVideo && (videoModels.length === 0 || !vidModel))

  const syncPromptToNode = useCallback((text, nextMentions) => {
    setPrompt(text)
    setMentions(nextMentions)
    if (selectedNodeId && node?.data?.onUpdate) {
      const patch = { prompt: text, mentions: nextMentions }
      if (isTextResponse) {
        patch.content = text
      }
      const hasImageMentions = (nextMentions || []).some((m) => {
        const t = String(m.type || "image").toLowerCase()
        return t === "image" || t === "image-gen"
      })
      if (isVideo) {
        patch.freeRefs = syncFreeRefsWithMentions(
          node.data.freeRefs,
          nextMentions,
          getNode
        )
        if (hasImageMentions) {
          patch.referenceMode = "freeref"
          patch.referenceSlotsOpen = true
          setReferenceSlotsExpanded(true)
        }
      }
      if (isImage) {
        const nextRefs = syncMentionRefsIntoReferenceImages(
          getReferenceImagesList(node.data),
          nextMentions,
          getNode
        )
        const resolved = getResolvedReferenceImagesList(
          { referenceImages: nextRefs },
          getNode
        )
        const first = resolved[0] || null
        patch.referenceImages = resolved
        patch.referenceImage = first?.imageUrl ?? null
        patch.referenceImageUrl = first?.imageUrl ?? null
        patch.referenceRef = first
      }
      node.data.onUpdate(selectedNodeId, patch)
    }
  }, [selectedNodeId, node, isVideo, isImage, isTextResponse, getNode, setReferenceSlotsExpanded])

  const runGenerate = useCallback(async (finalPrompt, generateParams) => {
    setSending(true)
    try {
      await onGenerate(selectedNodeId, {
        ...generateParams,
        prompt: finalPrompt,
      })
      setSubmitted(true)
      setTimeout(() => setSubmitted(false), 2000)
    } catch (err) {
      console.error("handleSend error:", err)
    } finally {
      setSending(false)
    }
  }, [selectedNodeId, onGenerate])

  const handleSend = useCallback(async () => {
    const model = isText ? textModel : isImage ? imgModel : vidModel
    if (!prompt?.trim() || !selectedNodeId || sending) return
    if (!model) {
      console.warn("handleSend: model 未选择或模型列表未加载")
      return
    }
    const ratio = IMAGE_RATIOS.find(r => r.key === imgRatio) || IMAGE_RATIOS[0]
    let safeVidDuration = vidDuration
    if (isVideo && vidCapabilities?.durations?.length) {
      const opts = vidCapabilities.durations.map((d) => `${d}s`)
      if (!opts.includes(vidDuration)) safeVidDuration = opts[0]
    }

    const mentionPayload = mentions.map(({ id, type, name, image_index }) => ({
      id,
      type,
      ...(name ? { name } : {}),
      ...(image_index != null ? { image_index } : {}),
    }))

    let imageRefs = referenceImages
    if (isImage) {
      const hasImageMentions = mentionPayload.some((m) => {
        const t = String(m.type || "image").toLowerCase()
        return t === "image" || t === "image-gen"
      })
      if (hasImageMentions) {
        imageRefs = mergeMentionRefsIntoReferenceImages(
          getReferenceImagesList(node?.data),
          mentionPayload,
          getNode
        )
        imageRefs = getResolvedReferenceImagesList(
          { referenceImages: imageRefs },
          getNode
        )
        if (node?.data?.onUpdate) {
          const first = imageRefs[0] || null
          node.data.onUpdate(selectedNodeId, {
            referenceImages: imageRefs,
            referenceImage: first?.imageUrl ?? null,
            referenceImageUrl: first?.imageUrl ?? null,
            referenceRef: first,
            mentions: mentionPayload,
          })
        }
      }
    }

    const refUrl = imageRefs[0]?.imageUrl || referenceImageUrl

    let videoPatch = null
    if (isVideo && node?.data?.onUpdate) {
      const hasImageMentions = mentionPayload.some((m) => {
        const t = String(m.type || "image").toLowerCase()
        return t === "image" || t === "image-gen"
      })
      if (hasImageMentions) {
        const freeRefs = mergeMentionRefsIntoFreeRefs(
          node.data.freeRefs,
          mentionPayload,
          getNode
        )
        videoPatch = {
          freeRefs,
          referenceMode: "freeref",
          mentions: mentionPayload,
        }
        node.data.onUpdate(selectedNodeId, videoPatch)
      }
    }

    const basePrompt = prompt.trim()
    const promptForSubmit = isVideo
      ? appendStyleReferenceToDescription(basePrompt, node?.data?.styleReference)
      : basePrompt

    const generationMode = vidMode === "参考" ? "freeref" : "keyframe"
    const refUrls = imageRefs.map((r) => r.imageUrl).filter(Boolean)
    const generateParams = {
      prompt: promptForSubmit,
      mentions: mentionPayload,
      modelId: model,
      count,
      imgQuality, imgRatio, imgResolution, imgSteps, imgCfg,
      vidMode,
      vidRatio,
      vidQuality,
      vidDuration: safeVidDuration,
      vidAudio,
      generationMode,
      referenceMode: generationMode,
      width: isImage ? ratio.w * 256 : 1280,
      height: isImage ? ratio.h * 256 : 720,
      referenceImage: refUrl || null,
      referenceImages: isImage ? imageRefs : undefined,
      reference_images: isImage && refUrls.length ? refUrls : undefined,
      freeRefs: isVideo
        ? (videoPatch?.freeRefs ?? node?.data?.freeRefs ?? [])
        : undefined,
    }

    if (isVideo) {
      console.log("[video-gen] prompt-bar generateParams", JSON.stringify(generateParams, null, 2))
    } else {
      console.log("[image-gen] prompt-bar generateParams", JSON.stringify({
        model,
        prompt: generateParams.prompt,
        count: generateParams.count,
        nodeId: selectedNodeId,
        nodeType: selectedNodeType,
        imgQuality: generateParams.imgQuality,
        imgRatio: generateParams.imgRatio,
        mentions: mentionPayload,
      }, null, 2))
    }

    const trimmed = prompt.trim()
    const shouldClassify = isText && trimmed.length >= TEXT_CLASSIFY_MIN

    if (!shouldClassify) {
      await runGenerate(trimmed, generateParams)
      return
    }

    const finalPrompt = await requestIntentGate({
      text: trimmed,
      context: "text",
      textMode,
      contextLabel: t("canvas.prompt.ctxText"),
    })
    if (finalPrompt === null) return
    syncPromptToNode(finalPrompt, mentions)
    await runGenerate(finalPrompt, generateParams)
  }, [prompt, selectedNodeId, selectedNodeType, isText, isImage, isVideo, sending,
      textModel, imgModel, vidModel, count, imgQuality, imgRatio, imgResolution, imgSteps, imgCfg,
      vidMode, vidRatio, vidQuality, vidDuration, vidAudio, mentions, vidCapabilities, textMode,
      runGenerate, referenceImageUrl, referenceImages, getNode, node, requestIntentGate, syncPromptToNode, t])

  const handleMentionEditorChange = useCallback(({ text, mentions: nextMentions }) => {
    syncPromptToNode(text, nextMentions)
  }, [syncPromptToNode])

  const removeReferenceImage = useCallback(
    (index) => {
      if (!selectedNodeId || !node?.data?.onUpdate) return
      const list = getReferenceImagesList(node.data)
      const removed = list[index]
      if (!removed) return
      if (removed.fromMention) {
        const nextMentions = filterMentionsAfterRefRemoved(mentions, removed)
        const removedMention = (mentions || []).find(
          (m) =>
            m.id === removed.nodeId
            && (m.image_index ?? 0) === (removed.imageIndex ?? 0)
        )
        if (removedMention) {
          const { text: nextText } = removeMentionFromPrompt(prompt, removedMention)
          syncPromptToNode(nextText, nextMentions)
          return
        }
        const next = syncMentionRefsIntoReferenceImages(
          list.filter((_, i) => i !== index),
          nextMentions,
          getNode
        )
        syncReferenceImages(next)
        setMentions(nextMentions)
        return
      }
      syncReferenceImages(list.filter((_, i) => i !== index))
    },
    [selectedNodeId, node, mentions, prompt, getNode, syncReferenceImages, syncPromptToNode]
  )

  const promptRefChipItems = useMemo(() => {
    const items = []
    const seen = new Set()

    if (isImage) {
      referenceImages.forEach((ref, index) => {
        const key = `ref:${ref.imageId || ref.imageUrl || index}`
        if (seen.has(key)) return
        seen.add(key)
        items.push({
          key,
          label: ref.label || t("canvas.prompt.refImage"),
          imageUrl: ref.imageUrl,
          type: "referenceImage",
          index,
          removable: true,
        })
      })
    }

    if (isVideo && node?.data?.referenceMode === "freeref") {
      const freeRefs = Array.isArray(node.data.freeRefs) ? node.data.freeRefs : []
      freeRefs.forEach((ref, index) => {
        const key = `free:${ref.imageId || ref.imageUrl || index}`
        if (seen.has(key)) return
        seen.add(key)
        items.push({
          key,
          label: ref.label || t("canvas.prompt.refImage"),
          imageUrl: ref.imageUrl,
          type: "freeRef",
          index,
          removable: true,
        })
      })
    }

    if (isImage || isVideo) {
      mentions.forEach((m) => {
        if (m.type !== "image" && m.type !== "video") return
        const dedupe = `${m.id}:${m.image_index ?? 0}`
        if (isImage && referenceImages.some(
          (r) => r.nodeId === m.id && (r.imageIndex ?? 0) === (m.image_index ?? 0)
        )) {
          return
        }
        const key = `mention:${dedupe}`
        if (seen.has(key)) return
        const refNode = getNode(m.id)
        let imageUrl = null
        if (refNode?.type === "image-gen" || refNode?.type === "image-upload") {
          const imgs = getImageNodeImages(refNode)
          imageUrl = imgs[m.image_index ?? 0]?.url || imgs[0]?.url
        }
        seen.add(key)
        items.push({
          key,
          label: m.name,
          imageUrl,
          type: "mention",
          mention: m,
          removable: true,
        })
      })
    }

    return items
  }, [isImage, isVideo, referenceImages, mentions, node?.data?.referenceMode, node?.data?.freeRefs, getNode, t])

  const handlePromptChipRemove = useCallback(
    (item) => {
      if (item.type === "referenceImage") {
        removeReferenceImage(item.index)
        return
      }
      if (item.type === "freeRef" && selectedNodeId && node?.data?.onUpdate) {
        const freeRefs = Array.isArray(node.data.freeRefs) ? node.data.freeRefs : []
        node.data.onUpdate(selectedNodeId, {
          freeRefs: freeRefs.filter((_, i) => i !== item.index),
        })
        return
      }
      if (item.type === "mention" && item.mention) {
        const { text: nextText } = removeMentionFromPrompt(prompt, item.mention)
        const nextMentions = (mentions || []).filter(
          (m) =>
            !(
              m.id === item.mention.id
              && (m.image_index ?? 0) === (item.mention.image_index ?? 0)
            )
        )
        syncPromptToNode(nextText, nextMentions)
      }
    },
    [removeReferenceImage, selectedNodeId, node, prompt, mentions, syncPromptToNode]
  )

  const handleToggleExpand = useCallback(() => {
    setIsExpanded((v) => {
      const next = !v
      const variant =
        isText || isTextResponse ? "text" : isImage ? "image" : isVideo ? "video" : null
      if (variant) setPromptExpanded(variant, next)
      return next
    })
  }, [isText, isTextResponse, isImage, isVideo])

  const handleMentionQuery = useCallback(({ active, query, anchorRect }) => {
    if (active) {
      setAtMentionOpen(true)
      setAtMentionQuery(query || "")
      setAtMentionAnchor(anchorRect || null)
    } else {
      setAtMentionOpen(false)
      setAtMentionQuery("")
      setAtMentionAnchor(null)
    }
  }, [])

  const handleAtMentionSelect = useCallback((item) => {
    mentionEditorRef.current?.insertMention(item)
    setAtMentionOpen(false)
    setAtMentionQuery("")
    setAtMentionAnchor(null)
  }, [])

  const toggleMic = useCallback((e) => {
    sp(e)
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return
    if (micActive) { recognitionRef.current?.stop(); setMicActive(false); return }
    const rec = new SR()
    rec.lang = "zh-CN"; rec.continuous = false; rec.interimResults = false
    rec.onresult = (ev) => {
      const transcript = ev.results[0]?.[0]?.transcript || ""
      if (transcript) {
        const next = prompt ? `${prompt} ${transcript}` : transcript
        syncPromptToNode(next, mentions)
      }
    }
    rec.onend = () => setMicActive(false)
    rec.onerror = () => setMicActive(false)
    recognitionRef.current = rec; rec.start(); setMicActive(true)
  }, [micActive, prompt, mentions, syncPromptToNode])

  if (!mounted || !node) return null

  const supportsPromptBar = isText || isTextResponse || isImage || isVideo
  if (!supportsPromptBar) return null

  const [vpX, vpY, zoom] = transform
  const nodeW       = node.width ?? node.data?.cardWidth ?? (
    (isText || isImage || isVideo || isTextResponse) ? 400 : 280
  )
  const nodeH       = node.height ?? 340
  const screenX     = node.position.x * zoom + vpX
  const screenY     = node.position.y * zoom + vpY
  const nodeCenterX = screenX + (nodeW * zoom) / 2
  const left        = nodeCenterX - BANNER_WIDTH / 2
  const top         = screenY + nodeH * zoom + BAR_OFFSET_Y

  // ── Shared sub-components ─────────────────────────────
  const MicBtn = () => (
    <button className={`nb-bottom-icon-btn nodrag${micActive ? " nb-bottom-icon-btn--active" : ""}`}
      onPointerDown={sp} onClick={toggleMic} title={micActive ? t("canvas.prompt.stopRecord") : t("canvas.prompt.voiceInput")}>
      <Mic size={14} />
    </button>
  )

  const CountDropup = () => (
    <div className="nb-dropup-wrap">
      {countDropOpen && (
        <div className="nb-dropup-menu" onPointerDown={sp}>
          {COUNT_OPTIONS.map((n) => (
            <button key={n} className={`nb-dropup-item nodrag${count === n ? " nb-dropup-item--active" : ""}`}
              onClick={(e) => { sp(e); handleCountChange(n); setCountDropOpen(false) }}>{n}×</button>
          ))}
        </div>
      )}
      <button className="nb-speed-btn nodrag" onPointerDown={sp}
        onClick={(e) => { sp(e); setCountDropOpen((v) => !v) }}>{count}×</button>
    </div>
  )

  // Credits + send capsule
  const CreditSend = ({ credits }) => (
    <div className="nb-capsule nodrag">
      <span className="nb-capsule-credits"><CreditIcon />{credits}</span>
      <button
        className={`nb-capsule-send nodrag${sending ? " nb-capsule-send--loading" : ""}${submitted ? " nb-capsule-send--submitted" : ""}`}
        disabled={isSendDisabled}
        onPointerDown={sp}
        onClick={(e) => { sp(e); handleSend() }}
        title={submitted ? t("canvas.prompt.submitted") : sending ? t("canvas.prompt.submitting") : !activeModel ? t("canvas.prompt.selectModel") : t("canvas.prompt.generate")}
      >
        {submitted ? "✓" : sending ? <SpinIcon /> : <SendArrowIcon />}
      </button>
    </div>
  )

  const imageHasParamPanel = isImage

  const videoHasParamPanel = vidCapLoading || (
    vidCapabilities && (
      (vidCapabilities.aspect_ratios?.length > 0)
      || (vidCapabilities.durations?.length > 0)
    )
  )

  const ImagePanelWrapper = () => imgPanelOpen
    ? (
      <ImagePanelContent
        capabilities={imgCapabilities}
        loading={imgCapLoading}
        imgRatio={imgRatio}
        setImgRatio={setImgRatio}
        imgResolution={imgResolution}
        setImgResolution={setImgResolution}
      />
    )
    : null

  const VideoPanelWrapper = () => vidPanelOpen
    ? (
      <VideoPanelContent
        capabilities={vidCapabilities}
        loading={vidCapLoading}
        vidMode={vidMode}
        setVidMode={handleVidModeChange}
        vidRatio={vidRatio}
        setVidRatio={setVidRatio}
        vidQuality={vidQuality}
        setVidQuality={setVidQuality}
        vidDuration={vidDuration}
        setVidDuration={setVidDuration}
        vidAudio={vidAudio}
        setVidAudio={setVidAudio}
      />
    )
    : null

  // ── Topbar ────────────────────────────────────────────
  const isRefSource = refSelect?.mode?.active && refSelect?.mode?.sourceNodeId === node?.id

  const renderImageTopbar = () => (
    <div className="video-top-bar nodrag nopan">
      <div className="add-ref-wrapper">
        <RefPickerTrigger
          label={t("canvas.prompt.addRef")}
          labelWithCount={t("canvas.prompt.addRefWithCount")}
          count={referenceImages.length}
          max={MAX_REFERENCE_IMAGES}
          disabled={refAtMax}
          excludeNodeId={selectedNodeId}
          assetEntries={assetEntries}
          onAssetPick={handleAssetRefPick}
          onQuickSelect={handleQuickRefSelect}
          onCanvasPick={openReferencePicker}
          onUpload={handleRefUploadFile}
        />
      </div>
      <input
        ref={refUploadInputRef}
        type="file"
        accept="image/*"
        hidden
        onChange={handleRefUpload}
      />
    </div>
  )

  const wrapBottombar = (content) => (
    <div ref={bottombarRef} className="nb-bottombar-host">
      {content}
    </div>
  )

  // ── Bottombar ─────────────────────────────────────────
  const renderBottombar = () => {
    if (isTextResponse) {
      return wrapBottombar(
        <div className="nb-bottombar">
          <span className="nb-hint-text">
            {t("canvas.prompt.syncReply")}
          </span>
          <div style={{ flex: 1 }} />
        </div>
      )
    }

    if (isText) return wrapBottombar(
      <div className="nb-bottombar">
        <div className="nb-text-mode nodrag" onPointerDown={sp}>
          <button
            type="button"
            className={`nb-text-mode-btn${textMode === TEXT_MODES.CHAT ? " nb-text-mode-btn--active" : ""}`}
            onClick={(e) => { sp(e); handleTextModeChange(TEXT_MODES.CHAT) }}
          >
            {t("canvas.prompt.chat")}
          </button>
          <button
            type="button"
            className={`nb-text-mode-btn${textMode === TEXT_MODES.SCREENPLAY ? " nb-text-mode-btn--active" : ""}`}
            onClick={(e) => { sp(e); handleTextModeChange(TEXT_MODES.SCREENPLAY) }}
          >
            {t("canvas.prompt.script")}
          </button>
        </div>
        <div className="nb-bottom-sep" />
        <div className="nb-dropup-wrap">
          {textModelOpen && textModels.length > 0 && (
            <div className="nb-dropup-menu" onPointerDown={sp}>
              {textModels.map((m) => (
                <button key={m.id} className={`nb-dropup-item nodrag${textModel === m.id ? " nb-dropup-item--active" : ""}`}
                  onClick={(e) => { sp(e); setTextModel(m.id); setTextModelOpen(false) }}>{m.display_name}</button>
              ))}
            </div>
          )}
          <button className="nb-model-btn-bare nodrag" onPointerDown={sp}
            onClick={(e) => { sp(e); if (textModels.length > 0) setTextModelOpen((v) => !v) }}
            disabled={textModels.length === 0}>
            <SparkleIcon /><span>{modelLabel(textModels, textModel, textModel)}</span>
          </button>
        </div>
        <div className="nb-bottom-sep" />
        <MicBtn />
        <div className="nb-bottom-sep" />
        <CountDropup />
        <div style={{flex:1}} />
        <CreditSend credits="1" />
      </div>
    )

    if (isImage) {
      const ratioMeta = resolveRatioMeta(imgRatio)
      const paramSummary = `${imgResolution} · ${imgRatio}`
      return wrapBottombar(
        <div className="nb-bottombar">
          {/* Model */}
          <div className="nb-dropup-wrap">
            {imgModelOpen && imageModels.length > 0 && (
              <div className="nb-dropup-menu" onPointerDown={sp}>
                {imageModels.map((m) => (
                  <button key={m.id} className={`nb-dropup-item nodrag${imgModel === m.id ? " nb-dropup-item--active" : ""}`}
                    onClick={(e) => { sp(e); setImgModel(m.id); setImgModelOpen(false) }}>{m.display_name}</button>
                ))}
              </div>
            )}
            <button className="nb-model-btn-bare nodrag" onPointerDown={sp}
              onClick={(e) => { sp(e); if (imageModels.length > 0) setImgModelOpen((v) => !v) }}
              disabled={imageModels.length === 0}>
              <BarChartIcon /><span>{modelLabel(imageModels, imgModel, imgModel)}</span>
            </button>
          </div>
          {imageHasParamPanel && (
            <>
              <div className="nb-bottom-sep" />
              <div className="nb-dropup-wrap">
                <ImagePanelWrapper />
                <button
                  type="button"
                  className={`nb-ratio-btn nodrag${imgCapLoading ? " nb-ratio-btn--disabled" : ""}`}
                  onPointerDown={sp}
                  disabled={imgCapLoading}
                  onClick={(e) => { sp(e); if (!imgCapLoading) setImgPanelOpen((v) => !v) }}
                >
                  <RatioIcon w={ratioMeta.w} h={ratioMeta.h} size={13} />
                  <span>{paramSummary}</span>
                </button>
              </div>
            </>
          )}
          <div style={{flex:1}} />
          <MicBtn />
          <div className="nb-bottom-sep" />
          <CountDropup />
          <CreditSend credits="5" />
        </div>
      )
    }

    // video
    return wrapBottombar(
      <div className="nb-bottombar">
        {/* Model */}
        <div className="nb-dropup-wrap">
          {vidModelOpen && videoModels.length > 0 && (
            <div className="nb-dropup-menu" onPointerDown={sp}>
              {videoModels.map((m) => (
                <button key={m.id} className={`nb-dropup-item nodrag${vidModel === m.id ? " nb-dropup-item--active" : ""}`}
                  onClick={(e) => { sp(e); setVidModel(m.id); setVidModelOpen(false) }}>{m.display_name}</button>
              ))}
            </div>
          )}
          <button className="nb-model-btn-bare nodrag" onPointerDown={sp}
            onClick={(e) => { sp(e); if (videoModels.length > 0) setVidModelOpen((v) => !v) }}
            disabled={videoModels.length === 0}>
              <SpinIcon /><span>{modelLabel(videoModels, vidModel, vidModel)}</span>
          </button>
        </div>
        {videoHasParamPanel && (
          <>
            <div className="nb-bottom-sep" />
            <div className="nb-dropup-wrap">
              <VideoPanelWrapper />
              <button
                type="button"
                className={`nb-ratio-btn nodrag${vidCapLoading ? " nb-ratio-btn--disabled" : ""}`}
                onPointerDown={sp}
                disabled={vidCapLoading}
                onClick={(e) => { sp(e); if (!vidCapLoading) setVidPanelOpen((v) => !v) }}
              >
                <span>
                  {[
                    vidMode === "参考" ? t("canvas.prompt.freeref") : t("canvas.prompt.keyframe"),
                    vidCapabilities?.aspect_ratios?.length ? vidRatio : null,
                    vidQuality,
                    vidCapabilities?.durations?.length ? vidDuration : null,
                  ].filter(Boolean).join(" · ")}
                </span>
                <SoundIcon />
              </button>
            </div>
          </>
        )}
        <div style={{flex:1}} />
        <MicBtn />
        <div className="nb-bottom-sep" />
        <CountDropup />
        <CreditSend credits="75~225" />
      </div>
    )
  }

  if (isRefSource) return null

  const promptVariant = isText || isTextResponse ? "text" : isImage ? "image" : isVideo ? "video" : null

  const videoEnhanceBridge = isVideo && selectedNodeId
    ? getVideoEnhanceBridge(selectedNodeId)
    : null
  void enhanceBridgeTick

  const videoEnhancePanelSlot = (
    <VideoEnhancePanel
      variant="panel"
      videoReady={!!videoEnhanceBridge?.videoReady}
      isEnhancing={!!videoEnhanceBridge?.isEnhancing}
      isAnalyzing={!!videoEnhanceBridge?.isAnalyzing}
      hasEnhanced={!!videoEnhanceBridge?.hasEnhanced}
      manualMode={videoEnhanceBridge?.manualMode ?? !!node?.data?.enhanceManualMode}
      advancedOpen={videoEnhanceBridge?.advancedOpen ?? false}
      reasoning={videoEnhanceBridge?.reasoning ?? node?.data?.enhanceReasoning ?? ""}
      upscaleFactor={videoEnhanceBridge?.upscaleFactor ?? node?.data?.enhanceUpscaleFactor ?? 2}
      strength={videoEnhanceBridge?.strength ?? node?.data?.enhanceStrength ?? "normal"}
      inputNoiseScale={
        videoEnhanceBridge?.inputNoiseScale ?? node?.data?.enhanceInputNoiseScale ?? 0.25
      }
      batchSize={videoEnhanceBridge?.batchSize ?? node?.data?.enhanceBatchSize ?? 8}
      colorCorrection={
        videoEnhanceBridge?.colorCorrection ?? node?.data?.enhanceColorCorrection ?? "lab"
      }
      modelSize={videoEnhanceBridge?.modelSize ?? node?.data?.enhanceModelSize ?? "7b"}
      error={videoEnhanceBridge?.error ?? node?.data?.enhanceError ?? null}
      onManualModeChange={videoEnhanceBridge?.onManualModeChange}
      onAdvancedOpenChange={videoEnhanceBridge?.onAdvancedOpenChange}
      onUpscaleChange={videoEnhanceBridge?.onUpscaleChange}
      onStrengthChange={videoEnhanceBridge?.onStrengthChange}
      onInputNoiseScaleChange={videoEnhanceBridge?.onInputNoiseScaleChange}
      onBatchSizeChange={videoEnhanceBridge?.onBatchSizeChange}
      onColorCorrectionChange={videoEnhanceBridge?.onColorCorrectionChange}
      onModelSizeChange={videoEnhanceBridge?.onModelSizeChange}
      onOneClick={() => videoEnhanceBridge?.onOneClick?.()}
    />
  )

  return (
    <PromptBarShell
      visible={visible}
      compact
      promptVariant={promptVariant}
      videoTopbarLayout={isVideo || isImage}
      style={{ position: "absolute", left, top, width: BANNER_WIDTH, marginLeft: 0 }}
      onBannerPointerDown={(e) => { sp(e); exitPickerIfActive() }}
      showTopbar={isImage || isVideo}
      expandInField={isText || isVideo}
      topbarSlot={
        isImage ? renderImageTopbar() : (
          isVideo && selectedNodeId && node ? (
            <VideoReferencePanel
              nodeId={selectedNodeId}
              data={node.data}
              section="promptbar"
              projectId={projectId}
              readOnly={readOnly}
              slotsExpanded={referenceSlotsExpanded}
              onSlotsExpandedChange={setReferenceSlotsExpanded}
              enhancePanelSlot={videoEnhancePanelSlot}
            />
          ) : null
        )
      }
      mediaSlot={
        isVideo ? null : null
      }
      isExpanded={isExpanded}
      onToggleExpand={handleToggleExpand}
      expandTitle={t("canvas.prompt.expand")}
      collapseTitle={t("canvas.prompt.collapse")}
      textareaWrapRef={textareaWrapRef}
      textareaSlot={
        <>
          {(isImage || isVideo) && promptRefChipItems.length > 0 && (
            <PromptRefChips items={promptRefChipItems} onRemove={handlePromptChipRemove} />
          )}
          {(isImage || isVideo) && (
            <VideoAtMentionList
              open={atMentionOpen}
              query={atMentionQuery}
              anchorRect={atMentionAnchor}
              excludeNodeId={null}
              compact
              onSelect={handleAtMentionSelect}
              onClose={() => { setAtMentionOpen(false); setAtMentionQuery(""); setAtMentionAnchor(null) }}
            />
          )}
          {(isImage || isVideo) ? (
            <MentionTextarea
              ref={mentionEditorRef}
              expanded={isExpanded}
              placeholder={
                isImage
                  ? t("canvas.prompt.placeholderImage")
                  : t("canvas.prompt.placeholderVideo")
              }
              value={prompt}
              mentions={mentions}
              onChange={handleMentionEditorChange}
              onMentionQuery={handleMentionQuery}
              onPointerDown={(e) => { sp(e); exitPickerIfActive() }}
              onMouseDown={(e) => { sp(e); exitPickerIfActive() }}
              onFocus={(e) => { sp(e); exitPickerIfActive() }}
              onClick={(e) => { sp(e); exitPickerIfActive() }}
              onKeyDown={(e) => { sp(e); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend() }}
            />
          ) : (
            <textarea
              className={`nb-textarea nodrag nowheel${isExpanded ? " nb-textarea--expanded" : ""}`}
              placeholder={isTextResponse ? t("canvas.prompt.placeholder") : t("canvas.prompt.placeholder")}
              value={prompt}
              onChange={(e) => syncPromptToNode(e.target.value, [])}
              onPointerDown={(e) => { sp(e); exitPickerIfActive() }}
              onMouseDown={(e) => { sp(e); exitPickerIfActive() }}
              onFocus={(e) => { sp(e); exitPickerIfActive() }}
              onClick={(e) => { sp(e); exitPickerIfActive() }}
              onKeyDown={(e) => { sp(e); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend() }}
            />
          )}
        </>
      }
      bottombarSlot={renderBottombar()}
    />
  )
}
