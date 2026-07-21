import { useState, useCallback, useEffect, useLayoutEffect, useRef, useMemo } from "react"
import { useReactFlow, useStore, useStoreApi } from "reactflow"
import { useReferenceSelect } from "./CanvasActionsContext"
import VideoReferencePanel from "./VideoReferencePanel"
import VideoStylePicker from "./VideoStylePicker"
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
import { uploadAudioFile, AUDIO_ACCEPT } from "../../services/uploadAudio"
import { Mic } from "lucide-react"
import RefPickerTrigger from "./RefPickerTrigger"
import PromptRefChips from "./PromptRefChips"
import PromptBarShell from "./PromptBarShell"
import PromptExpandCard from "./PromptExpandCard"
import { closeCanvasDropdown, openCanvasDropdown } from "./canvasDropdownCoordinator"
import useRefAssetEntries from "../../hooks/canvas/useRefAssetEntries"
import {
  buildRefItem,
  getReferenceImagesList,
  getResolvedReferenceImagesList,
  appendReferenceImage,
  getImageNodeImages,
  MAX_REFERENCE_IMAGES,
  resolveReferenceImageUrl,
  resolveRefDisplayUrl,
} from "./videoReferenceHelpers"
import { ensureMediaUrl } from "../../utils/mediaTicket"
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
import { IMAGE_ACCEPT } from "../../utils/uploadFileKind"
import { appendStyleReferenceToDescription } from "../../utils/canvas/styleReferenceFormat"
import { findScriptTableNode, resolveImageQualityPresetId } from "../../utils/canvas/scriptTableNode"
import { ModelDropupItem } from "./CanvasModelDropup"
import {
  T2V_ONLY,
  I2V_ONLY,
  defaultVidAudioForModel,
  isVideoModelCompatible,
  preferredModelForMode,
  reconcileVideoModelAndMode,
  referenceModeForVidMode,
  vidModeFromReferenceMode,
  videoModesForCatalog,
} from "../../utils/canvas/videoModelCompat"
import {
  isModelRecommended,
  pickDefaultModel,
  sortModelsForDisplay,
} from "../../utils/canvas/modelCatalog"
import { sizeForAspectRatio, cardDisplayRatio } from "../../utils/canvas/aspectRatioLayout"
import "./NodeBanner.css"
import "./PromptRefChips.css"
import "./VideoReferencePanel.css"
import "./VideoStylePicker.css"

// ── Image config ──────────────────────────────────────────
const DEFAULT_IMAGE_QUALITIES = ["480P", "720P", "1080P"]
const IMAGE_RATIOS = [
  { key: "1:1",   w: 1, h: 1 },
  { key: "16:9",  w: 16, h: 9 },
  { key: "9:16",  w: 9, h: 16 },
  { key: "4:3",   w: 4, h: 3 },
  { key: "3:4",   w: 3, h: 4 },
]
const VIDEO_MODES   = ["文生", "首尾帧", "参考"]
const VIDEO_RATIOS  = [
  { key: "16:9", w: 16, h: 9 },
  { key: "9:16", w: 9, h: 16 },
  { key: "1:1",  w: 1,  h: 1  },
]
const VIDEO_QUALITIES = ["480P", "720P", "1080P"]
const VIDEO_AUDIOS    = ["开启", "关闭"]
const DEFAULT_VIDEO_DURATIONS = [5, 10, 15]

function getVideoQualityOptions(capabilities) {
  return (capabilities?.resolutions?.length ? capabilities.resolutions : VIDEO_QUALITIES)
    .map((q) => normalizeClarity(q))
}

function getVideoDurationOptions(capabilities) {
  const durations = capabilities?.durations?.length
    ? capabilities.durations
    : DEFAULT_VIDEO_DURATIONS
  return durations.map((d) => `${d}s`)
}

function getVideoAspectRatioOptions(capabilities) {
  const keys = capabilities?.aspect_ratios?.length
    ? capabilities.aspect_ratios
    : VIDEO_RATIOS.map((r) => r.key)
  return keys.map(resolveRatioMeta)
}

function inferVideoBackend(modelId, capabilities) {
  const fromCaps = String(capabilities?.video_backend || "").toLowerCase()
  if (fromCaps) return fromCaps
  const id = String(modelId || "").toLowerCase()
  if (id.includes("ltx23")) return "ltx23"
  if (id.includes("ltx2")) return "ltx2"
  return ""
}

function videoSupportsAudio(modelId, capabilities) {
  if (capabilities?.supports_audio != null) return Boolean(capabilities.supports_audio)
  const backend = inferVideoBackend(modelId, capabilities)
  return backend === "ltx2" || backend === "ltx23"
}

function buildVideoParamSummary({
  vidMode,
  vidRatio,
  vidQuality,
  vidDuration,
  vidAudio,
  vidAudioUrl,
  vidModel,
  vidCapabilities,
  t,
}) {
  const backend = inferVideoBackend(vidModel, vidCapabilities)
  const modeLabel =
    vidMode === "文生"
      ? t("canvas.prompt.t2v")
      : vidMode === "参考"
        ? t("canvas.prompt.freeref")
        : t("canvas.prompt.keyframe")
  const parts = [
    modeLabel,
    vidRatio,
    formatClarityLabel(normalizeClarity(vidQuality)),
    vidDuration,
  ]
  if (videoSupportsAudio(vidModel, vidCapabilities)) {
    if (backend === "ltx2") {
      parts.push(vidAudio === "开启" ? t("canvas.prompt.audioOn") : t("canvas.prompt.audioOff"))
    } else if (backend === "ltx23") {
      parts.push(
        vidAudioUrl
          ? t("canvas.prompt.audioUploaded")
          : t("canvas.prompt.audioOptionalNone")
      )
    }
  }
  return parts.filter(Boolean).join(" · ")
}

/** 归一化图像/视频清晰度到 480P|720P|1080P */
function normalizeClarity(value, fallback = "720P") {
  const raw = String(value || "").trim().toUpperCase().replace("×", "x")
  if (!raw) return fallback
  if (raw === "480" || raw === "720" || raw === "1080") return `${raw}P`
  if (raw === "480P" || raw === "720P" || raw === "1080P") return raw
  if (raw === "2K") return "720P"
  if (raw === "3K") return "1080P"
  // 旧版像素标签（如 1344x768）→ 默认 720
  if (/^\d+x\d+$/i.test(raw)) return fallback
  return fallback
}

/** 清晰度展示：保留 480P / 720P / 1080P */
function formatClarityLabel(q) {
  return normalizeClarity(q)
}

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

  const resolutions = (capabilities?.resolutions?.length
    ? capabilities.resolutions
    : DEFAULT_IMAGE_QUALITIES
  ).map((q) => normalizeClarity(q))
  const aspectKeys = capabilities?.aspect_ratios?.length
    ? capabilities.aspect_ratios
    : IMAGE_RATIOS.map((r) => r.key)

  const ratioOptions = aspectKeys.map(resolveRatioMeta)
  const activeClarity = normalizeClarity(imgResolution)

  return (
    <div ref={panelRef} className="nb-panel nb-panel--image-params" onPointerDown={sp}>
      {resolutions.length > 0 && (
        <>
          <div className="nb-panel-label">{t("canvas.prompt.clarity")}</div>
          <div className="nb-param-seg">
            {resolutions.map((res) => (
              <button
                key={res}
                type="button"
                className={`nb-param-chip nodrag${activeClarity === res ? " nb-param-chip--active" : ""}`}
                onPointerDown={sp}
                onClick={(e) => {
                  sp(e)
                  setImgResolution(res)
                }}
              >
                {formatClarityLabel(res)}
              </button>
            ))}
          </div>
        </>
      )}
      {ratioOptions.length > 0 && (
        <>
          <div className={`nb-panel-label${resolutions.length > 0 ? " nb-panel-label--spaced" : ""}`}>
            {t("canvas.prompt.ratio")}
          </div>
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
        </>
      )}
    </div>
  )
}

function VideoPanelContent({
  capabilities,
  loading,
  modelId,
  videoModels,
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
  vidAudioUrl,
  setVidAudioUrl,
  audioUploading,
  onAudioFileSelect,
}) {
  const { t } = useLocale()
  const panelRef = useRef(null)
  useBlockCtrlWheel(panelRef)

  const renderVidModeLabel = (opt) => (
    <>
      {opt === "文生"
        ? t("canvas.prompt.t2v")
        : opt === "参考"
          ? t("canvas.prompt.freeref")
          : t("canvas.prompt.keyframe")}
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
  const ratioOptions = aspectKeys.length > 0
    ? aspectKeys.map(resolveRatioMeta)
    : getVideoAspectRatioOptions(capabilities)
  const durationOptions = getVideoDurationOptions(capabilities)
  const qualityOptions = getVideoQualityOptions(capabilities)
  const modeOptions = videoModesForCatalog(videoModels)
  const videoBackend = inferVideoBackend(modelId, capabilities)
  const showGenerateAudio =
    videoSupportsAudio(modelId, capabilities) && videoBackend === "ltx2"
  const showUploadAudio =
    videoSupportsAudio(modelId, capabilities) && videoBackend === "ltx23"
  const audioUploadInputRef = useRef(null)

  return (
    <div ref={panelRef} className="nb-panel" onPointerDown={sp}>
      {modeOptions.length > 0 && (
        <>
          <div className="nb-panel-label">{t("canvas.prompt.genMode")}</div>
          <SegmentGroup
            options={modeOptions}
            value={modeOptions.includes(vidMode) ? vidMode : modeOptions[0]}
            onChange={setVidMode}
            renderLabel={renderVidModeLabel}
          />
        </>
      )}
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
      {qualityOptions.length > 0 && (
        <>
          <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.clarity")}</div>
          <SegmentGroup
            options={qualityOptions}
            value={normalizeClarity(vidQuality, qualityOptions[0])}
            onChange={setVidQuality}
            renderLabel={formatClarityLabel}
          />
        </>
      )}
      {durationOptions.length > 0 && (
        <>
          <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.duration")}</div>
          <SegmentGroup options={durationOptions} value={vidDuration} onChange={setVidDuration} />
        </>
      )}
      {showGenerateAudio && (
        <>
          <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.audio")}<InfoIcon /></div>
          <SegmentGroup
            options={VIDEO_AUDIOS}
            value={vidAudio === "关闭" ? "关闭" : "开启"}
            onChange={setVidAudio}
            renderLabel={renderAudioLabel}
          />
        </>
      )}
      {showUploadAudio && (
        <>
          <div className="nb-panel-label" style={{ marginTop: 8 }}>{t("canvas.prompt.uploadAudioOptional")}</div>
          <div className="nb-audio-upload-row">
            <button
              type="button"
              className="nb-audio-upload-btn nodrag"
              disabled={audioUploading}
              onPointerDown={sp}
              onClick={(e) => {
                sp(e)
                audioUploadInputRef.current?.click()
              }}
            >
              {audioUploading
                ? t("canvas.prompt.uploadingAudio")
                : (vidAudioUrl ? t("canvas.prompt.replaceAudio") : t("canvas.prompt.selectAudio"))}
            </button>
            {vidAudioUrl ? (
              <button
                type="button"
                className="nb-audio-upload-clear nodrag"
                onPointerDown={sp}
                onClick={(e) => {
                  sp(e)
                  setVidAudioUrl(null)
                }}
              >
                {t("canvas.common.clear")}
              </button>
            ) : null}
          </div>
          <input
            ref={audioUploadInputRef}
            type="file"
            accept={AUDIO_ACCEPT}
            hidden
            onChange={onAudioFileSelect}
          />
          {!vidAudioUrl ? (
            <p className="nb-audio-upload-hint">{t("canvas.prompt.audioSilentWithoutUpload")}</p>
          ) : null}
        </>
      )}
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
  const storeApi = useStoreApi()
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
  const [imgQuality,    setImgQuality]    = useState("720P")
  const [imgRatio,      setImgRatio]      = useState("1:1")
  const [imgResolution, setImgResolution] = useState("720P")
  const [imgSteps,      setImgSteps]      = useState(20)
  const [imgCfg,        setImgCfg]        = useState(7)
  const [imgPanelOpen,  setImgPanelOpen]  = useState(false)
  // video
  const [vidModel,      setVidModel]      = useState("")
  const [vidModelOpen,  setVidModelOpen]  = useState(false)
  const [vidMode,       setVidMode]       = useState("首尾帧")
  const [vidRatio,      setVidRatio]      = useState("16:9")
  const [vidQuality,    setVidQuality]    = useState("720P")
  const [vidDuration,   setVidDuration]   = useState("5s")
  const [vidAudio,      setVidAudio]      = useState("关闭")
  const [vidAudioUrl,   setVidAudioUrl]   = useState(null)
  const [audioUploading, setAudioUploading] = useState(false)
  const [vidPanelOpen,  setVidPanelOpen]  = useState(false)
  const [referenceSlotsExpanded, setReferenceSlotsExpanded] = useState(false)
  const [enhanceBridgeTick, setEnhanceBridgeTick] = useState(0)
  const [atMentionOpen, setAtMentionOpen]   = useState(false)
  const [atMentionQuery, setAtMentionQuery] = useState("")
  const [atMentionAnchor, setAtMentionAnchor] = useState(null)
  const [expandCardOpen, setExpandCardOpen] = useState(false)
  const [textMode,      setTextMode]      = useState(TEXT_MODES.CHAT)

  const sortedTextModels = useMemo(
    () => sortModelsForDisplay(textModels),
    [textModels],
  )
  const sortedImageModels = useMemo(
    () => sortModelsForDisplay(imageModels),
    [imageModels],
  )
  const compatibleVideoModels = useMemo(
    () => sortModelsForDisplay(
      videoModels.filter((m) => isVideoModelCompatible(m.id, vidMode)),
      { vidMode },
    ),
    [videoModels, vidMode],
  )

  const hideTimerRef   = useRef(null)
  const bannerRef = useRef(null)
  const refUploadInputRef = useRef(null)
  const textareaWrapRef = useRef(null)
  const mentionEditorRef = useRef(null)
  const expandMentionEditorRef = useRef(null)
  const expandTextareaRef = useRef(null)
  const expandTextareaWrapRef = useRef(null)
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

  const videoModeSignature = useStore((state) => {
    if (!selectedNodeId) return ""
    const n = state.nodeInternals.get(selectedNodeId)
    if (!n || n.type !== "video-gen") return ""
    const d = n.data || {}
    return [
      d.referenceMode ?? "",
      d.panelMode ?? "",
      d.vidMode ?? "",
      d.modelId ?? "",
      d.referenceSlotsOpen ? "1" : "0",
    ].join("|")
  })

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
      if (e.target.closest?.(".pec-overlay")) return
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
      setExpandCardOpen(false)
      hideTimerRef.current = setTimeout(() => setMounted(false), 280)
    }
    return () => clearTimeout(hideTimerRef.current)
  }, [selectedNodeId])

  useEffect(() => {
    setExpandCardOpen(false)
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
    const qualities = (imgCapabilities.resolutions?.length
      ? imgCapabilities.resolutions
      : DEFAULT_IMAGE_QUALITIES
    ).map((q) => normalizeClarity(q))
    const nextClarity = normalizeClarity(imgResolution, qualities[0] || "720P")
    if (qualities.length && !qualities.includes(nextClarity)) {
      setImgResolution(qualities[0])
      setImgQuality(qualities[0])
    } else if (nextClarity !== imgResolution) {
      setImgResolution(nextClarity)
      setImgQuality(nextClarity)
    }
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
    if (durations.length && !durations.includes(vidDuration)) {
      setVidDuration(durations.includes("5s") ? "5s" : durations[0])
    }
    const qualities = (vidCapabilities.resolutions ?? []).map((q) => normalizeClarity(q))
    const nextQ = normalizeClarity(vidQuality, qualities[0] || "720P")
    if (qualities.length && !qualities.includes(nextQ)) {
      setVidQuality(qualities[0])
    } else if (nextQ !== vidQuality) {
      setVidQuality(nextQ)
    }
    if (!vidCapabilities.supports_audio && vidAudio === "开启") {
      setVidAudio("关闭")
    }
    const backend = String(vidCapabilities.video_backend || "").toLowerCase()
    const selectedNode = selectedNodeId ? getNode(selectedNodeId) : null
    const modelForDefault = vidModel || selectedNode?.data?.modelId || ""
    const dirtyPatch = {}

    const defAudio = defaultVidAudioForModel(modelForDefault)
    if (!selectedNode?.data?.vidAudio && vidAudio !== defAudio) {
      setVidAudio(defAudio)
      dirtyPatch.vidAudio = defAudio
    } else if (backend !== "ltx2") {
      if (vidAudio !== defAudio) {
        setVidAudio(defAudio)
        dirtyPatch.vidAudio = defAudio
      }
    }

    if (backend !== "ltx23" && vidAudioUrl) {
      setVidAudioUrl(null)
      dirtyPatch.audioUrl = null
    }

    if (Object.keys(dirtyPatch).length > 0 && selectedNodeId && selectedNode?.data?.onUpdate) {
      selectedNode.data.onUpdate(selectedNodeId, dirtyPatch)
    }
  }, [
    vidCapabilities,
    isVideo,
    vidRatio,
    vidDuration,
    vidQuality,
    vidAudio,
    vidAudioUrl,
    selectedNodeId,
    getNode,
    vidModel,
  ])

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
      else if (isText) setTextModel(n.data.modelId)
    }
    if (typeof n.data?.count === "number" && n.data.count >= 1) {
      setCount(n.data.count)
    } else {
      setCount(1)
    }
    if (isText) {
      setTextMode(
        n.data?.textMode === TEXT_MODES.SCREENPLAY
          ? TEXT_MODES.SCREENPLAY
          : TEXT_MODES.CHAT
      )
    }
    if (isVideo) {
      const rawMode = vidModeFromReferenceMode(n.data?.referenceMode, n.data?.vidMode)
      const modelFromNode = n.data?.modelId || ""
      const reconciled = reconcileVideoModelAndMode({
        modelId: modelFromNode,
        vidMode: rawMode,
        models: videoModels,
      })
      const resolvedModel =
        reconciled.modelId
        || pickDefaultModel(videoModels, { vidMode: reconciled.vidMode, category: "video" })
        || ""
      setVidMode(reconciled.vidMode)
      setVidModel(resolvedModel)
      const nextReferenceMode = referenceModeForVidMode(reconciled.vidMode)
      const keepEnhance = n.data?.panelMode === "enhance"
      const nextPanelMode = keepEnhance ? "enhance" : nextReferenceMode
      if (
        n.data?.onUpdate
        && (
          reconciled.vidMode !== rawMode
          || resolvedModel !== modelFromNode
          || n.data?.referenceMode !== nextReferenceMode
          || (!keepEnhance && n.data?.panelMode !== nextReferenceMode)
        )
      ) {
        n.data.onUpdate(selectedNodeId, {
          vidMode: reconciled.vidMode,
          referenceMode: nextReferenceMode,
          panelMode: nextPanelMode,
          ...(resolvedModel ? { modelId: resolvedModel } : {}),
        })
      }
      setReferenceSlotsExpanded(!!n.data?.referenceSlotsOpen)
      if (n.data?.vidRatio) setVidRatio(n.data.vidRatio)
      if (n.data?.vidQuality) setVidQuality(normalizeClarity(n.data.vidQuality))
      if (n.data?.vidDuration) setVidDuration(n.data.vidDuration)
      setVidAudio(n.data?.vidAudio || defaultVidAudioForModel(resolvedModel))
      setVidAudioUrl(n.data?.audioUrl || null)
    }
    if (isImage) {
      if (n.data?.imgQuality) setImgQuality(normalizeClarity(n.data.imgQuality))
      if (n.data?.imgRatio) setImgRatio(n.data.imgRatio)
      else setImgRatio("1:1")
      if (n.data?.imgResolution) {
        const clarity = normalizeClarity(n.data.imgResolution || n.data.imgQuality)
        setImgResolution(clarity)
        setImgQuality(clarity)
      } else if (n.data?.imgQuality) {
        setImgResolution(normalizeClarity(n.data.imgQuality))
      } else {
        setImgResolution("720P")
        setImgQuality("720P")
      }
    }
  }, [selectedNodeId, selectedNodeType, getNode, isImage, isVideo, isText, videoModels, videoModeSignature])

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
    if (isText && !textModel && textModels.length > 0) {
      setTextModel(pickDefaultModel(textModels, { category: "text" }) || textModels[0].id)
    }
    if (isImage && !imgModel && imageModels.length > 0) {
      setImgModel(pickDefaultModel(imageModels, { category: "image" }) || imageModels[0].id)
    }
  }, [isText, isImage, textModels, imageModels, textModel, imgModel])

  const node = mounted ? getNode(selectedNodeId) : null
  const nodePosKey = node
    ? [
        node.position?.x,
        node.position?.y,
        node.width,
        node.height,
        node.data?.cardWidth,
        node.data?.cardHeight,
        node.data?.cardDisplayRatio,
        node.data?.vidRatio,
        node.data?.imgRatio,
      ].join(":")
    : ""

  useLayoutEffect(() => {
    if (!mounted || !selectedNodeId || expandCardOpen) return undefined

    let raf = 0
    const apply = () => {
      raf = 0
      const el = bannerRef.current
      if (!el) return
      const n = getNode(selectedNodeId)
      if (!n) return
      const [vpX, vpY, zoom] = storeApi.getState().transform
      const isImg = n.type === "image-gen"
      const isVid = n.type === "video-gen"
      const isTxt = n.type === "text-note" || n.type === "text-response"
      const imageFallback = sizeForAspectRatio(cardDisplayRatio(n?.data, "image"), 280)
      const videoFallback = sizeForAspectRatio(cardDisplayRatio(n?.data, "video"), 225)
      const w = n.width ?? n.data?.cardWidth ?? (
        isImg ? imageFallback.width
          : isVid ? videoFallback.width
            : isTxt ? 400 : 280
      )
      const h = n.height ?? n.data?.cardHeight ?? (
        isImg ? imageFallback.height + 60
          : isVid ? videoFallback.height + 60
            : 340
      )
      const screenX = n.position.x * zoom + vpX
      const screenY = n.position.y * zoom + vpY
      const left = screenX + (w * zoom) / 2 - BANNER_WIDTH / 2
      const top = screenY + h * zoom + BAR_OFFSET_Y
      el.style.left = `${left}px`
      el.style.top = `${top}px`
    }

    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(apply)
    }

    schedule()
    let prev = storeApi.getState().transform
    const unsub = storeApi.subscribe((state) => {
      if (state.transform !== prev) {
        prev = state.transform
        schedule()
      }
    })
    return () => {
      unsub()
      if (raf) cancelAnimationFrame(raf)
    }
  }, [mounted, selectedNodeId, expandCardOpen, getNode, storeApi, nodePosKey])

  const scriptTableNode = useMemo(() => {
    if (!isImage || !node) return null
    const ref = node.data?.scriptTableRef
    if (ref?.nodeId) {
      return getNodes().find((n) => n.id === ref.nodeId) || null
    }
    return findScriptTableNode(getNodes())
  }, [isImage, node, getNodes])

  const imageQualityPresetId = useMemo(
    () => resolveImageQualityPresetId(node?.data || {}, scriptTableNode?.data || null),
    [node?.data, scriptTableNode?.data]
  )

  const handleImagePresetChange = useCallback(
    (presetId) => {
      if (!selectedNodeId || !node?.data?.onUpdate) return
      node.data.onUpdate(selectedNodeId, { qualityPresetId: presetId })
    },
    [selectedNodeId, node]
  )

  const syncVideoNodePatch = useCallback((patch) => {
    if (!selectedNodeId || !node?.data?.onUpdate) return
    node.data.onUpdate(selectedNodeId, patch)
  }, [selectedNodeId, node])

  // 切换选中节点后，先从节点 hydrate 本地 state，再允许写回，避免用旧比例污染新节点
  const imageParamsReadyRef = useRef(false)
  const videoParamsReadyRef = useRef(false)
  const [imageSyncTick, setImageSyncTick] = useState(0)
  const [videoSyncTick, setVideoSyncTick] = useState(0)
  useEffect(() => {
    imageParamsReadyRef.current = false
    videoParamsReadyRef.current = false
    const t = window.setTimeout(() => {
      imageParamsReadyRef.current = true
      videoParamsReadyRef.current = true
      setImageSyncTick((n) => n + 1)
      setVideoSyncTick((n) => n + 1)
    }, 0)
    return () => window.clearTimeout(t)
  }, [selectedNodeId])

  // 选比例/清晰度时写回节点（供生成使用）；卡片预览尺寸在生成完成后才同步
  useEffect(() => {
    if (!isImage || !selectedNodeId || !node?.data?.onUpdate) return
    if (!imageParamsReadyRef.current) return
    const clarity = normalizeClarity(imgResolution || imgQuality)
    if (
      node.data.imgRatio === imgRatio
      && normalizeClarity(node.data.imgResolution || node.data.imgQuality) === clarity
    ) {
      return
    }
    node.data.onUpdate(selectedNodeId, {
      imgRatio,
      imgResolution: clarity,
      imgQuality: clarity,
    })
  }, [isImage, selectedNodeId, imgRatio, imgResolution, imgQuality, node, imageSyncTick])

  // 视频参数同样实时写回，卡片比例/提交读 node.data
  useEffect(() => {
    if (!isVideo || !selectedNodeId || !node?.data?.onUpdate) return
    if (!videoParamsReadyRef.current) return
    const clarity = normalizeClarity(vidQuality)
    const patch = {
      vidRatio,
      vidQuality: clarity,
      vidDuration,
      vidAudio,
      audioUrl: vidAudioUrl || null,
    }
    if (
      node.data.vidRatio === patch.vidRatio
      && normalizeClarity(node.data.vidQuality) === patch.vidQuality
      && node.data.vidDuration === patch.vidDuration
      && node.data.vidAudio === patch.vidAudio
      && (node.data.audioUrl || null) === patch.audioUrl
    ) {
      return
    }
    node.data.onUpdate(selectedNodeId, patch)
  }, [isVideo, selectedNodeId, vidRatio, vidQuality, vidDuration, vidAudio, vidAudioUrl, node, videoSyncTick])

  const handleVidModeChange = useCallback((mode) => {
    const reconciled = reconcileVideoModelAndMode({
      modelId: vidModel,
      vidMode: mode,
      models: videoModels,
    })
    setVidMode(reconciled.vidMode)
    if (reconciled.modelId && reconciled.modelId !== vidModel) {
      setVidModel(reconciled.modelId)
    }
    syncVideoNodePatch({
      vidMode: reconciled.vidMode,
      referenceMode: referenceModeForVidMode(reconciled.vidMode),
      panelMode: referenceModeForVidMode(reconciled.vidMode),
      ...(reconciled.modelId ? { modelId: reconciled.modelId } : {}),
    })
  }, [syncVideoNodePatch, vidModel, videoModels])

  const handleAudioFileSelect = useCallback(async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAudioUploading(true)
    try {
      const url = await uploadAudioFile(file)
      setVidAudioUrl(url)
    } catch (err) {
      console.error("音频上传失败", err)
      window.alert?.(err?.message || "音频上传失败")
    } finally {
      setAudioUploading(false)
      e.target.value = ""
    }
  }, [])

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
    const forceFunInpaintKeyframe = isVideo && model === "wan-fun-inpaint"
    if (isVideo && node?.data?.onUpdate) {
      const hasImageMentions = mentionPayload.some((m) => {
        const t = String(m.type || "image").toLowerCase()
        return t === "image" || t === "image-gen"
      })
      if (hasImageMentions && !forceFunInpaintKeyframe) {
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
      } else if (forceFunInpaintKeyframe) {
        videoPatch = {
          referenceMode: "keyframe",
          panelMode: "keyframe",
          vidMode: "首尾帧",
          mentions: mentionPayload,
        }
        node.data.onUpdate(selectedNodeId, videoPatch)
        setVidMode("首尾帧")
      }
    }

    const basePrompt = prompt.trim()
    const promptForSubmit = isVideo
      ? appendStyleReferenceToDescription(basePrompt, node?.data?.styleReference)
      : basePrompt

    const generationMode = forceFunInpaintKeyframe
      ? "keyframe"
      : (vidMode === "参考" ? "freeref" : "keyframe")
    const referenceMode = forceFunInpaintKeyframe
      ? "keyframe"
      : referenceModeForVidMode(vidMode)
    const refUrls = imageRefs.map((r) => r.imageUrl).filter(Boolean)
    const clarity = normalizeClarity(imgResolution || imgQuality, "720P")
    const generateParams = {
      prompt: promptForSubmit,
      mentions: mentionPayload,
      modelId: model,
      count,
      imgQuality: clarity,
      imgRatio,
      imgResolution: clarity,
      imgSteps,
      imgCfg,
      vidMode,
      vidRatio,
      vidQuality: normalizeClarity(vidQuality, "720P"),
      vidDuration: safeVidDuration,
      vidAudio,
      audioUrl: vidAudioUrl || null,
      generationMode,
      referenceMode,
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
      vidMode, vidRatio, vidQuality, vidDuration, vidAudio, vidAudioUrl, mentions, vidCapabilities, textMode,
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

    // 图片参考图在顶栏展示；输入区 chips 仅保留 @ 引用

    if (isVideo && node?.data?.referenceMode === "freeref") {
      const freeRefs = Array.isArray(node.data.freeRefs) ? node.data.freeRefs : []
      freeRefs.forEach((ref, index) => {
        const key = `free:${ref.imageId || ref.imageUrl || index}`
        if (seen.has(key)) return
        seen.add(key)
        items.push({
          key,
          label: ref.label || t("canvas.prompt.refImage"),
          imageUrl: resolveRefDisplayUrl(ref, getNode),
          type: "freeRef",
          index,
          nodeId: ref.nodeId,
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
          imageUrl = ensureMediaUrl(
            imgs[m.image_index ?? 0]?.imageUrl || imgs[0]?.imageUrl || null
          )
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

    return items.filter((item) => item.imageUrl)
  }, [isImage, isVideo, referenceImages, mentions, node?.data?.referenceMode, node?.data?.freeRefs, getNode, t])

  const handlePromptChipRemove = useCallback(
    (item) => {
      if (item.type === "referenceImage") {
        removeReferenceImage(item.index)
        return
      }
      if (item.type === "freeRef" && selectedNodeId && node?.data?.onUpdate) {
        const freeRefs = Array.isArray(node.data.freeRefs) ? node.data.freeRefs : []
        const ref = freeRefs[item.index]
        if (ref?.nodeId && node.data.onDisconnectIncomingFromSource) {
          node.data.onDisconnectIncomingFromSource(selectedNodeId, ref.nodeId)
          return
        }
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
    setExpandCardOpen((v) => !v)
  }, [])

  useEffect(() => {
    if (!expandCardOpen) return undefined
    const timer = window.setTimeout(() => {
      if (isImage || isVideo) expandMentionEditorRef.current?.focus()
      else expandTextareaRef.current?.focus()
    }, 80)
    return () => window.clearTimeout(timer)
  }, [expandCardOpen, isImage, isVideo])

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
    const editor = expandCardOpen ? expandMentionEditorRef.current : mentionEditorRef.current
    editor?.insertMention(item)
    setAtMentionOpen(false)
    setAtMentionQuery("")
    setAtMentionAnchor(null)
  }, [expandCardOpen])

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

  const imageFallback = sizeForAspectRatio(cardDisplayRatio(node?.data, "image"), 280)
  const videoFallback = sizeForAspectRatio(cardDisplayRatio(node?.data, "video"), 225)
  const nodeW = node.width ?? node.data?.cardWidth ?? (
    isImage ? imageFallback.width
      : isVideo ? videoFallback.width
        : (isText || isTextResponse) ? 400 : 280
  )
  const nodeH = node.height ?? node.data?.cardHeight ?? (
    isImage ? imageFallback.height + 60
      : isVideo ? videoFallback.height + 60
        : 340
  )

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

  const videoHasParamPanel = isVideo

  const ImagePanelWrapper = () => imgPanelOpen
    ? (
      <ImagePanelContent
        capabilities={imgCapabilities}
        loading={imgCapLoading}
        imgRatio={imgRatio}
        setImgRatio={setImgRatio}
        imgResolution={imgResolution}
        setImgResolution={(v) => {
          const clarity = normalizeClarity(v)
          setImgResolution(clarity)
          setImgQuality(clarity)
        }}
      />
    )
    : null

  const VideoPanelWrapper = () => vidPanelOpen
    ? (
      <VideoPanelContent
        capabilities={vidCapabilities}
        loading={vidCapLoading}
        modelId={vidModel}
        videoModels={videoModels}
        vidMode={vidMode}
        setVidMode={handleVidModeChange}
        vidRatio={vidRatio}
        setVidRatio={setVidRatio}
        vidQuality={vidQuality}
        setVidQuality={(v) => setVidQuality(normalizeClarity(v))}
        vidDuration={vidDuration}
        setVidDuration={setVidDuration}
        vidAudio={vidAudio}
        setVidAudio={setVidAudio}
        vidAudioUrl={vidAudioUrl}
        setVidAudioUrl={setVidAudioUrl}
        audioUploading={audioUploading}
        onAudioFileSelect={handleAudioFileSelect}
      />
    )
    : null

  // ── Topbar ────────────────────────────────────────────
  const isRefSource = refSelect?.mode?.active && refSelect?.mode?.sourceNodeId === node?.id

  const renderImageTopbar = () => (
    <div className="video-top-bar nodrag nopan">
      <div className="image-ref-topbar-row nodrag nopan">
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
        {referenceImages.length > 0 && (
          <div className="image-ref-thumbs nodrag nopan" onPointerDown={sp}>
            {referenceImages.map((ref, index) => (
              <div
                key={`${ref.imageId || ref.imageUrl || index}`}
                className="image-ref-thumb nodrag nopan"
                title={ref.label || t("canvas.prompt.refImage")}
              >
                <img
                  src={resolveRefDisplayUrl(ref, getNode)}
                  alt=""
                  draggable={false}
                />
                <button
                  type="button"
                  className="image-ref-thumb-remove nodrag"
                  onPointerDown={sp}
                  onClick={(e) => {
                    sp(e)
                    removeReferenceImage(index)
                  }}
                  aria-label={t("common.delete")}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      {projectId && (
        <>
          <div className="video-top-divider" aria-hidden />
          <VideoStylePicker
            value={imageQualityPresetId}
            showUploadSection={false}
            readOnly={readOnly}
            title={t("canvas.script.shotStyleTitle")}
            onPresetChange={handleImagePresetChange}
          />
        </>
      )}
      <input
        ref={refUploadInputRef}
        type="file"
        accept={IMAGE_ACCEPT}
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
          {textModelOpen && sortedTextModels.length > 0 && (
            <div className="nb-dropup-menu" onPointerDown={sp}>
              {sortedTextModels.map((m) => (
                <ModelDropupItem
                  key={m.id}
                  model={m}
                  active={textModel === m.id}
                  showRecommended={isModelRecommended(m)}
                  onSelect={(id) => {
                    setTextModel(id)
                    setTextModelOpen(false)
                  }}
                />
              ))}
            </div>
          )}
          <button className="nb-model-btn-bare nodrag" onPointerDown={sp}
            onClick={(e) => { sp(e); if (sortedTextModels.length > 0) setTextModelOpen((v) => !v) }}
            disabled={sortedTextModels.length === 0}>
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
      const paramSummary = `${formatClarityLabel(normalizeClarity(imgResolution))} · ${imgRatio}`
      return wrapBottombar(
        <div className="nb-bottombar">
          {/* Model */}
          <div className="nb-dropup-wrap">
            {imgModelOpen && sortedImageModels.length > 0 && (
              <div className="nb-dropup-menu" onPointerDown={sp}>
                {sortedImageModels.map((m) => (
                  <ModelDropupItem
                    key={m.id}
                    model={m}
                    active={imgModel === m.id}
                    showRecommended={isModelRecommended(m)}
                    onSelect={(id) => {
                      setImgModel(id)
                      setImgModelOpen(false)
                    }}
                  />
                ))}
              </div>
            )}
            <button className="nb-model-btn-bare nodrag" onPointerDown={sp}
              onClick={(e) => { sp(e); if (sortedImageModels.length > 0) setImgModelOpen((v) => !v) }}
              disabled={sortedImageModels.length === 0}>
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
    const videoParamSummary = buildVideoParamSummary({
      vidMode,
      vidRatio,
      vidQuality,
      vidDuration,
      vidAudio,
      vidAudioUrl,
      vidModel,
      vidCapabilities,
      t,
    })
    return wrapBottombar(
      <div className="nb-bottombar">
        {/* Model */}
        <div className="nb-dropup-wrap">
          {vidModelOpen && compatibleVideoModels.length > 0 && (
            <div className="nb-dropup-menu" onPointerDown={sp}>
              {compatibleVideoModels.map((m) => (
                <ModelDropupItem
                  key={m.id}
                  model={m}
                  active={vidModel === m.id}
                  showRecommended={isModelRecommended(m, { vidMode })}
                  onSelect={(id) => {
                      setVidModelOpen(false)
                      if (id === "wan-fun-inpaint") {
                        setVidModel(id)
                        setVidMode("首尾帧")
                        syncVideoNodePatch({
                          modelId: id,
                          referenceMode: "keyframe",
                          panelMode: "keyframe",
                          vidMode: "首尾帧",
                        })
                        return
                      }
                      if (T2V_ONLY.has(id)) {
                        setVidModel(id)
                        setVidMode("文生")
                        syncVideoNodePatch({
                          modelId: id,
                          referenceMode: "t2v",
                          panelMode: "t2v",
                          vidMode: "文生",
                        })
                        return
                      }
                      const reconciled = reconcileVideoModelAndMode({
                        modelId: id,
                        vidMode,
                        models: videoModels,
                      })
                      setVidModel(reconciled.modelId)
                      setVidMode(reconciled.vidMode)
                      syncVideoNodePatch({
                        modelId: reconciled.modelId,
                        vidMode: reconciled.vidMode,
                        referenceMode: referenceModeForVidMode(reconciled.vidMode),
                        panelMode: referenceModeForVidMode(reconciled.vidMode),
                      })
                    }}
                />
              ))}
            </div>
          )}
          <button className="nb-model-btn-bare nodrag" onPointerDown={sp}
            onClick={(e) => { sp(e); if (compatibleVideoModels.length > 0) setVidModelOpen((v) => !v) }}
            disabled={compatibleVideoModels.length === 0}>
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
                <span>{videoParamSummary}</span>
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

  const renderPromptInput = ({ inCard = false } = {}) => {
    const mentionRef = inCard ? expandMentionEditorRef : mentionEditorRef
    const mentionList = (isImage || isVideo) && (
      <VideoAtMentionList
        open={atMentionOpen}
        query={atMentionQuery}
        anchorRect={atMentionAnchor}
        excludeNodeId={null}
        compact={!inCard}
        onSelect={handleAtMentionSelect}
        onClose={() => { setAtMentionOpen(false); setAtMentionQuery(""); setAtMentionAnchor(null) }}
      />
    )
    const chips = (isImage || isVideo) && promptRefChipItems.length > 0 && (
      <PromptRefChips items={promptRefChipItems} onRemove={handlePromptChipRemove} />
    )

    if (isImage || isVideo) {
      return (
        <>
          {chips}
          {mentionList}
          <MentionTextarea
            ref={mentionRef}
            expanded={inCard}
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
        </>
      )
    }

    return (
      <textarea
        ref={inCard ? expandTextareaRef : undefined}
        className="nb-textarea nodrag nowheel"
        placeholder={isTextResponse ? t("canvas.prompt.placeholder") : t("canvas.prompt.placeholder")}
        value={prompt}
        onChange={(e) => syncPromptToNode(e.target.value, [])}
        onPointerDown={(e) => { sp(e); exitPickerIfActive() }}
        onMouseDown={(e) => { sp(e); exitPickerIfActive() }}
        onFocus={(e) => { sp(e); exitPickerIfActive() }}
        onClick={(e) => { sp(e); exitPickerIfActive() }}
        onKeyDown={(e) => { sp(e); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend() }}
      />
    )
  }

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
      availableModelSizes={
        videoEnhanceBridge?.availableModelSizes?.length
          ? videoEnhanceBridge.availableModelSizes
          : ["3b", "7b"]
      }
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

  const renderPromptBarShell = ({ modal = false } = {}) => (
    <PromptBarShell
      visible={modal || visible}
      compact
      modal={modal}
      promptVariant={promptVariant}
      videoTopbarLayout={isVideo || isImage}
      style={
        modal
          ? undefined
          : { position: "absolute", left: 0, top: 0, width: BANNER_WIDTH, marginLeft: 0 }
      }
      onBannerPointerDown={(e) => { sp(e); exitPickerIfActive() }}
      showTopbar={isImage || isVideo}
      expandInField={isText || isTextResponse || isVideo}
      bannerRef={modal ? undefined : bannerRef}
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
      mediaSlot={null}
      expandCardOpen={modal}
      onToggleExpand={modal ? () => setExpandCardOpen(false) : handleToggleExpand}
      showExpandButton={!modal}
      expandTitle={t("canvas.prompt.expand")}
      collapseTitle={t("canvas.prompt.collapse")}
      textareaWrapRef={modal ? expandTextareaWrapRef : textareaWrapRef}
      textareaSlot={renderPromptInput({ inCard: modal })}
      bottombarSlot={renderBottombar()}
    />
  )

  return (
    <>
      {!expandCardOpen && renderPromptBarShell()}
      <PromptExpandCard
        open={expandCardOpen}
        onClose={() => setExpandCardOpen(false)}
      >
        {renderPromptBarShell({ modal: true })}
      </PromptExpandCard>
    </>
  )
}
