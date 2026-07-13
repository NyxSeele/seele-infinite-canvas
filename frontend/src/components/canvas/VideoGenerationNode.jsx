import { useState, useCallback, useEffect, useRef, useMemo } from "react"
import { createPortal } from "react-dom"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_NODE_DOTS_MENU } from "../../utils/zIndexLayers"
import { useModelStore, useCanvasStore } from "../../stores"
import { pushGenHistory } from "../../utils/canvas/genHistory"
import { Handle, Position, useReactFlow, useStore } from "reactflow"
import api from "../../services/api"
import { getCanvasTeamId, teamIdPayload } from "../../utils/teamContext"
import { cancelCanvasTask } from "../../services/cancelTask"
import { buildMediaViewUrl, resolveTaskResultUrl } from "../../utils/mediaViewUrl"
import { ensureMediaUrl, toRelativeMediaUrl } from "../../utils/mediaTicket"
import { downloadMediaUrl } from "../../utils/downloadMedia"
import { pollTaskUntilDone } from "../../utils/canvas/outlineStructureApi"
import MediaFullscreenViewer from "./MediaFullscreenViewer"
import GenerationStopButton from "./GenerationStopButton"
import GenerationBrandLoader from "./GenerationBrandLoader"
import VideoEnhancePanel from "./VideoEnhancePanel"
import {
  setVideoEnhanceBridge,
  notifyVideoEnhanceBridge,
} from "./videoEnhanceBridge"
import { wsManager } from "../../services/ws"
import { useCanvasActions, useReferenceSelect } from "./CanvasActionsContext"
import EditableNodeLabel from "./EditableNodeLabel"
import NodeLastEditedMeta from "./NodeLastEditedMeta"
import {
  buildClearGenerationTaskPatch,
  DEFAULT_KEYFRAMES,
  getImageNodeOutgoingRef,
} from "./videoReferenceHelpers"
import { mergeMentionRefsIntoFreeRefs } from "./promptMentions"
import { isNetworkError, networkErrorMessage, parseGenerationError } from "./taskNetworkError"
import { getRetryPolicy } from "../../utils/canvas/generationRetryPolicy"
import { createStaleProgressGuard, isTerminalTaskStatus, PROGRESS_STALE_MS } from "./taskPollTimeout"
import { normalizeProgressPercent, mergeMonotonicProgress, logVideoPollDebug } from "./videoProgressSync"
import useModelCapabilities from "../../hooks/useModelCapabilities"
import { uploadImageFile } from "../../services/uploadImage"
import { useLocale } from "../../utils/locale"
import { appendStyleReferenceToDescription, styleReferenceSummary } from "../../utils/canvas/styleReferenceFormat"
import { T2V_ONLY } from "../../utils/canvas/videoModelCompat"
import { IconStyleRef, IconZoom, IconEnhance } from "./CanvasTopbarIcons"
import { collectConnectedCharacterFaceUrl } from "../../utils/canvas/entityRefs"
import CameraMotionPicker, {
  CAMERA_MOVE_OPTIONS,
  SHOT_SCALE_OPTIONS,
} from "./CameraMotionPicker"
import "./CameraMotionPicker.css"
import { useCanvasNodeWheel } from "./canvasScrollHelpers"
import { markSuppressPaneMenu } from "../../utils/canvas/suppressPaneMenu"
import { findScriptTableNode, resolveVideoQualityPresetId } from "../../utils/canvas/scriptTableNode"
import { isLutActive, submitVideoLutTask } from "../../services/lutApi"
import "./CanvasShared.css"
import "./GenerationCardNode.css"
import "./VideoGenerationNode.css"
import "./VideoReferencePanel.css"

const POLL_INTERVAL_MS = 2000
const VIDEO_MENU_WIDTH = 200
const VIDEO_MENU_EST_HEIGHT = 280

function computeVideoMenuPos(btnRect) {
  let x = btnRect.right - VIDEO_MENU_WIDTH
  let y = btnRect.bottom + 4
  if (x < 0) x = btnRect.left
  if (y + VIDEO_MENU_EST_HEIGHT > window.innerHeight) {
    y = btnRect.top - VIDEO_MENU_EST_HEIGHT
  }
  return { x, y }
}

/** 阻止 React Flow 选中/拖拽，但保留按钮点击 */
function stopFlowPointer(e) {
  e.stopPropagation()
}

const RESOLUTIONS = [
  { label: "480P", width: 848, height: 480 },
  { label: "720P", width: 1280, height: 720 },
]
const DURATIONS = [3, 5]
const DEFAULT_NEG =
  "worst quality, inconsistent motion, blurry, jittery, distorted"

const VideoPlaceholderIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
    <rect x="4" y="4" width="40" height="40" rx="10" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M20 16l12 8-12 8V16z" fill="currentColor" opacity="0.7"/>
  </svg>
)
const NodeLabelIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <rect x="1" y="2" width="7" height="8" rx="1.2"
      stroke="currentColor" strokeWidth="1.2"/>
    <path d="M8 4.5l3-1.5v5.5l-3-1.5V4.5z"
      stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/>
  </svg>
)
const UploadIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
    <path d="M6.5 9V3M6.5 3L4 5.5M6.5 3L9 5.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 10.5h9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
  </svg>
)
const AssetLibraryIcon = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
    <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
    <path d="M2 6.5h12" stroke="currentColor" strokeWidth="1.2"/>
    <circle cx="5.5" cy="9" r="1.2" fill="currentColor" opacity="0.7"/>
    <path d="M8 11l2-2.2 2.5 3.2" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
)

export default function VideoGenerationNode({ id, data, selected }) {
  const { t } = useLocale()
  const [status, setStatus] = useState(() => data.status || "input")
  const [prompt, setPrompt] = useState(data.prompt || "")
  const [resIndex, setResIndex] = useState(0)
  const [duration, setDuration] = useState(3)
  const [taskId, setTaskId] = useState(data.taskId || null)
  const taskIdRef = useRef(null)
  const [progress, setProgress] = useState(0)
  const [videoUrl, setVideoUrl] = useState(data.videoUrl || null)
  const [errorMessage, setErrorMessage] = useState(null)
  const [toast, setToast] = useState(null)
  const [sending, setSending] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [playbackProgress, setPlaybackProgress] = useState(0)
  const [playbackDuration, setPlaybackDuration] = useState(0)
  const [isScrubbing, setIsScrubbing] = useState(false)
  const isScrubbingRef = useRef(false)
  const wasPlayingBeforeScrubRef = useRef(false)
  const [videoMenu, setVideoMenu] = useState(null)
  const videoMenuPortalRef = useRef(null)
  const [enhanceUpscaleFactor, setEnhanceUpscaleFactor] = useState(
    () => data.enhanceUpscaleFactor ?? 2
  )
  const [enhanceStrength, setEnhanceStrength] = useState(
    () => data.enhanceStrength || "normal"
  )
  const [enhanceInputNoiseScale, setEnhanceInputNoiseScale] = useState(
    () => data.enhanceInputNoiseScale ?? 0.25
  )
  const [enhanceBatchSize, setEnhanceBatchSize] = useState(
    () => data.enhanceBatchSize ?? 8
  )
  const [enhanceColorCorrection, setEnhanceColorCorrection] = useState(
    () => data.enhanceColorCorrection || "lab"
  )
  const [enhanceModelSize, setEnhanceModelSize] = useState(
    () => data.enhanceModelSize || "7b"
  )
  const [enhanceManualMode, setEnhanceManualMode] = useState(
    () => !!data.enhanceManualMode
  )
  const [enhanceReasoning, setEnhanceReasoning] = useState(
    () => data.enhanceReasoning || ""
  )
  const [enhanceAnalyzing, setEnhanceAnalyzing] = useState(false)
  const [enhanceAdvancedOpen, setEnhanceAdvancedOpen] = useState(false)
  const [enhanceMenuOpen, setEnhanceMenuOpen] = useState(false)
  const [enhancing, setEnhancing] = useState(false)
  const [enhanceError, setEnhanceError] = useState(data.enhanceError || null)
  const enhanceBridgeRef = useRef({})
  const enhancePollTimersRef = useRef(null)
  const lutPollTimersRef = useRef(null)
  const autoApplyLutRef = useRef(null)
  const [videoViewTab, setVideoViewTab] = useState("graded")
  const toastTimerRef = useRef(null)
  const pollTimersRef = useRef(null)
  const staleGuardRef = useRef(null)
  const pollMetaRef = useRef({ taskId: null, startedAt: 0 })
  const completedLatchRef = useRef(false)
  const videoRef = useRef(null)
  const [mediaRevision, setMediaRevision] = useState(0)
  const videoModels = useModelStore((s) => s.videoModels)
  const [modelId, setModelId] = useState(data.modelId || "")
  const generateRef = useRef(null)
  const lastSubmitParamsRef = useRef(null)
  const effectiveModelId = data.modelId || modelId
  const { capabilities: modelCapabilities } = useModelCapabilities(effectiveModelId)
  const [cameraPickerOpen, setCameraPickerOpen] = useState(false)
  const cameraMove = data.cameraMove || "auto"
  const shotScale = data.shotScale || "auto"

  useEffect(() => {
    if (videoModels.length > 0 && !modelId) {
      setModelId(videoModels[0].id || videoModels[0].display_name || "")
    }
  }, [videoModels])

  useEffect(() => {
    if (!data.onUpdate) return
    const patch = {}
    if (data.cameraMove == null) patch.cameraMove = "auto"
    if (data.shotScale == null) patch.shotScale = "auto"
    if (Object.keys(patch).length) data.onUpdate(id, patch)
  }, [id, data.cameraMove, data.shotScale, data.onUpdate])

  useEffect(() => {
    if (effectiveModelId !== "wan-fun-inpaint") return
    if (data.referenceMode === "keyframe" && data.panelMode !== "freeref") return
    data.onUpdate?.(id, {
      referenceMode: "keyframe",
      panelMode: "keyframe",
      vidMode: "首尾帧",
    })
  }, [effectiveModelId, data.referenceMode, data.panelMode, data.onUpdate, id])

  const handleCardCameraMotionChange = useCallback((next) => {
    data.onUpdate?.(id, {
      cameraMove: next.cameraMove ?? "auto",
      shotScale: next.shotScale ?? "auto",
      samplingProfile: next.samplingProfile
        ?? ((next.cameraMove || "auto") !== "auto" ? "quality" : "fast"),
    })
  }, [id, data])

  const cameraSummaryLabel = useMemo(() => {
    const moveLabel = CAMERA_MOVE_OPTIONS.find((o) => o.id === cameraMove)?.label || "自动"
    const scaleLabel = SHOT_SCALE_OPTIONS.find((o) => o.id === shotScale)?.label || "自动"
    return `${moveLabel} · ${scaleLabel}`
  }, [cameraMove, shotScale])

  useEffect(() => {
    if (!modelCapabilities || !data.onUpdate) return
    data.onUpdate(id, { capabilities: modelCapabilities })
  }, [modelCapabilities, id, data.onUpdate])

  useEffect(() => {
    if (data.prompt !== undefined && data.prompt !== prompt) {
      setPrompt(data.prompt)
    }
  }, [data.prompt])

  useEffect(() => {
    if (status === "generating" || sending) return
    if (data.status === "generating" || data.status === "pending" || data.status === "queued") {
      return
    }
    if (data.status === "completed" && data.videoUrl) {
      completedLatchRef.current = true
      setStatus("completed")
      setVideoUrl(data.videoUrl)
      setProgress(data.progress ?? 100)
      setSending(false)
      setErrorMessage(null)
    }
  }, [data.status, data.videoUrl, data.progress, status, sending])

  const stopPolling = useCallback(() => {
    staleGuardRef.current?.stop()
    staleGuardRef.current = null
    const timers = pollTimersRef.current
    if (!timers) return
    if (timers.interval) clearInterval(timers.interval)
    pollTimersRef.current = null
  }, [])

  useEffect(() => {
    if (sending || status === "generating") return
    if (data.status === "generating" || data.status === "completed") return
    const failed =
      data.status === "error" || data.status === "failed" || data.status === "timeout"
    if (!failed) return
    if (status !== "generating" && !sending) {
      stopPolling()
      setStatus(data.status === "timeout" ? "timeout" : "error")
      setErrorMessage(data.error || t("canvas.gen.failed"))
      setSending(false)
    }
  }, [data.status, data.error, status, sending, stopPolling, t])

  const applyProgress = useCallback((pct, { reset = false } = {}) => {
    setProgress((prev) => {
      const next = mergeMonotonicProgress(prev, pct, { allowDecrease: reset })
      staleGuardRef.current?.bump(next)
      data.onUpdate?.(id, { progress: next })
      return next
    })
  }, [id, data])

  const failTask = useCallback((nextStatus, msg) => {
    stopPolling()
    setStatus(nextStatus)
    setErrorMessage(msg)
    setSending(false)
    data.onUpdate?.(id, { status: nextStatus, error: msg })
  }, [stopPolling, id, data])

  const startTaskPolling = useCallback((activeTaskId) => {
    stopPolling()
    pollMetaRef.current = { taskId: activeTaskId, startedAt: Date.now() }
    const terminalRef = { current: false }

    const staleGuard = createStaleProgressGuard((meta) => {
      if (terminalRef.current) return
      logVideoPollDebug({
        taskId: activeTaskId,
        status: "timeout",
        ...staleGuardRef.current?.getDebugState?.(),
        ...meta,
      })
      failTask("timeout", t("canvas.gen.timeout"))
    })
    staleGuard.start()
    staleGuardRef.current = staleGuard

    const pollOnce = async () => {
      try {
        const res = await api.get(`/api/tasks/${activeTaskId}`)
        const task = res.data
        if (isTerminalTaskStatus(task.status)) {
          terminalRef.current = true
          staleGuardRef.current?.stop()
        }
        const pct = normalizeProgressPercent(task.progress)
        if (pct != null) {
          applyProgress(pct)
        }
        logVideoPollDebug({
          taskId: activeTaskId,
          status: task.status,
          progress: pct,
          stage: task.stage,
          message: task.message,
          ...staleGuard.getDebugState(),
          elapsed: Date.now() - pollMetaRef.current.startedAt,
        })
        if (task.status === "completed" && task.result) {
          stopPolling()
          const url = resolveTaskResultUrl(task.result)
          console.log("[video-gen] poll completed, video src=", url, "raw result=", task.result)
          completedLatchRef.current = true
          setMediaRevision((r) => r + 1)
          setVideoUrl(url)
          setStatus("completed")
          setProgress(100)
          setSending(false)
          setErrorMessage(null)
          const completedAt = Date.now()
          data.onUpdate?.(id, {
            status: "completed",
            videoUrl: url,
            taskId: activeTaskId,
            progress: 100,
            error: null,
            completedAt,
          })
          const { canvasId, projectName } = useCanvasStore.getState()
          pushGenHistory({
            title: (data.label && String(data.label).trim()) || "Video",
            prompt: data.prompt || data.displayPrompt || "",
            kind: "video",
            mediaUrl: url,
            nodeId: id,
            ts: completedAt,
            canvasId,
            canvasName: projectName,
            teamId: getCanvasTeamId(),
          })
          autoApplyLutRef.current?.(url)
        } else if (task.status === "failed") {
          failTask("error", parseGenerationError(null, task))
        }
      } catch (err) {
        console.error("poll video task error:", err)
        failTask("error", parseGenerationError(err, null))
      }
    }

    pollOnce()
    const interval = setInterval(pollOnce, POLL_INTERVAL_MS)
    pollTimersRef.current = { interval }
  }, [stopPolling, failTask, id, data, applyProgress, t])

  useEffect(() => {
    const st = data.status
    const savedUrl = data.videoUrl || videoUrl
    const locallyGenerating = status === "generating" || sending
    const persistedGenerating =
      st === "generating" || st === "pending" || st === "queued"

    const zombieGenerating =
      savedUrl &&
      persistedGenerating &&
      !sending &&
      status !== "generating"

    if (
      !locallyGenerating &&
      !persistedGenerating &&
      (status === "completed" ||
        st === "completed" ||
        zombieGenerating)
    ) {
      if (savedUrl && status !== "completed") {
        completedLatchRef.current = true
        setVideoUrl(savedUrl)
        setStatus("completed")
        setSending(false)
        setErrorMessage(null)
      }
      if (status === "completed" && st !== "completed" && savedUrl) {
        data.onUpdate?.(
          id,
          buildClearGenerationTaskPatch({
            status: "completed",
            error: null,
            videoUrl: savedUrl,
            taskId: taskId || data.taskId,
            progress: 100,
          })
        )
      }
      return
    }

    const persistedActive =
      st === "pending" || st === "generating" || st === "queued"
    const locallyActive =
      sending ||
      pollTimersRef.current ||
      status === "generating"

    if (persistedActive && !data.pendingTrigger && !locallyActive) {
      if (savedUrl) {
        completedLatchRef.current = true
        setVideoUrl(savedUrl)
        setStatus("completed")
        setSending(false)
        setErrorMessage(null)
        data.onUpdate?.(id, {
          status: "completed",
          videoUrl: savedUrl,
          error: null,
          progress: data.progress ?? 100,
          taskId: taskId || data.taskId,
        })
        return
      }
      const localTerminal =
        status === "error" || status === "timeout"
      if (localTerminal) {
        data.onUpdate?.(
          id,
          buildClearGenerationTaskPatch({
            status: status === "timeout" ? "timeout" : "error",
            error: errorMessage || data.error || t("canvas.gen.interrupted"),
          })
        )
        return
      }
      stopPolling()
      setStatus("error")
      setErrorMessage(data.error || t("canvas.gen.interrupted"))
      setSending(false)
      data.onUpdate?.(
        id,
        buildClearGenerationTaskPatch({
          status: "error",
          error: data.error || t("canvas.gen.interrupted"),
        })
      )
      return
    }

    const activeTaskId = data.taskId
    if (
      activeTaskId &&
      persistedActive &&
      !pollTimersRef.current &&
      !sending &&
      status !== "error" &&
      status !== "timeout"
    ) {
      setTaskId(activeTaskId)
      taskIdRef.current = data.comfyPromptId || activeTaskId
      setStatus("generating")
      setSending(true)
      setErrorMessage(null)
      if (data.progress != null) {
        setProgress(Math.min(100, Math.max(0, Number(data.progress) || 0)))
      }
      startTaskPolling(activeTaskId)
    }
  }, [
    data.status,
    data.pendingTrigger,
    data.error,
    data.taskId,
    data.comfyPromptId,
    data.progress,
    id,
    data.onUpdate,
    stopPolling,
    sending,
    status,
    errorMessage,
    videoUrl,
    taskId,
    startTaskPolling,
    t,
  ])

  useEffect(() => () => stopPolling(), [stopPolling])

  useEffect(() => {
    if (status !== "generating") return
    const remove = wsManager.addListener((msg) => {
      const msgPromptId = msg.data?.prompt_id
      if (msgPromptId && taskIdRef.current && msgPromptId !== taskIdRef.current) return

      if (msg.type === "progress") {
        const percent = normalizeProgressPercent(
          msg.data?.max
            ? (msg.data.value / msg.data.max) * 100
            : msg.data?.progress
        )
        if (percent != null) {
          applyProgress(percent)
          logVideoPollDebug({
            taskId: taskIdRef.current,
            status: "running",
            progress: percent,
            source: "websocket",
            ...staleGuardRef.current?.getDebugState?.(),
          })
        }

      } else if (msg.type === "executed") {
        const videos = msg.data?.output?.videos || msg.data?.output?.gifs || []
        if (videos.length > 0) {
          stopPolling()
          const url = buildMediaViewUrl(videos[0])
          console.log("[video-gen] websocket executed, video src=", url, "media=", videos[0])
          completedLatchRef.current = true
          setMediaRevision((r) => r + 1)
          setVideoUrl(url)
          setStatus("completed")
          setProgress(100)
          setSending(false)
          setErrorMessage(null)
          data.onUpdate?.(id, {
            status: "completed",
            videoUrl: url,
            error: null,
            progress: 100,
          })
        }

      } else if (msg.type === "execution_error") {
        failTask(
          "error",
          parseGenerationError(msg.data?.exception_message || msg.data, null),
        )
      }
    })
    return remove
  }, [status, failTask, stopPolling, id, data, applyProgress, t])

  const showToast = useCallback((msg) => {
    clearTimeout(toastTimerRef.current)
    setToast(msg)
    toastTimerRef.current = setTimeout(() => setToast(null), 2000)
  }, [])

  const { getNode, getNodes, getEdges } = useReactFlow()
  const canvasActions = useCanvasActions()
  const refSelect = useReferenceSelect()
  const isRefSource = refSelect?.mode?.active && refSelect?.mode?.sourceNodeId === id

  const incomingSource = useStore(
    useCallback((s) => {
      const inEdge = s.edges.find((e) => e.target === id)
      if (!inEdge) return null
      const srcNode = s.nodeInternals.get(inEdge.source)
      return getImageNodeOutgoingRef(srcNode)
    }, [id])
  )

  const lastIncomingKeyRef = useRef(null)

  useEffect(() => {
    if (!incomingSource?.imageUrl || !data.onUpdate) return
    const incomingKey =
      incomingSource.imageId
      || `${incomingSource.nodeId}_${incomingSource.imageIndex ?? 0}`
    if (lastIncomingKeyRef.current === incomingKey) return
    lastIncomingKeyRef.current = incomingKey

    const refItem = { ...incomingSource }
    const mode = data.referenceMode || "keyframe"
    const keyframes = data.keyframes || DEFAULT_KEYFRAMES
    const freeRefs = data.freeRefs || []

    if (mode === "keyframe") {
      if (!keyframes.first) {
        data.onUpdate(id, {
          keyframes: { ...keyframes, first: refItem },
        })
      }
    } else if (
      !freeRefs.some((r) => r.imageId === refItem.imageId)
      && freeRefs.length < 5
    ) {
      data.onUpdate(id, { freeRefs: [...freeRefs, refItem] })
    }
  }, [incomingSource, data.referenceMode, data.keyframes, data.freeRefs, data.onUpdate, id])

  const clearNodeTaskState = useCallback(
    (nextStatus = "generating") => {
      completedLatchRef.current = false
      setMediaRevision((r) => r + 1)
      const el = videoRef.current
      if (el) {
        el.pause()
        el.removeAttribute("src")
        el.load()
      }
      setTaskId(null)
      taskIdRef.current = null
      setProgress(0)
      setErrorMessage(null)
      setStatus(nextStatus === "input" ? "input" : "generating")
      setVideoUrl(null)
      data.onUpdate?.(
        id,
        buildClearGenerationTaskPatch({
          status: nextStatus,
          error: null,
          videoUrl: null,
          progress: 0,
        })
      )
    },
    [id, data]
  )

  const handleGenerate = useCallback(async () => {
    if (sending) return
    if (!prompt.trim()) {
      setErrorMessage(t("canvas.gen.noPrompt"))
      return
    }

    const promptForSubmit = appendStyleReferenceToDescription(
      prompt.trim(),
      data.styleReference
    )

    clearNodeTaskState("generating")
    setSending(true)
    setStatus("generating")
    setProgress(0)
    setErrorMessage(null)
    try {
      const rawDuration = data.vidDuration || "5s"
      const allowedDurations = modelCapabilities?.durations?.length
        ? modelCapabilities.durations.map((d) => Number(d))
        : [5, 10, 15]
      let durationSec = parseInt(rawDuration, 10) || allowedDurations[0]
      if (!allowedDurations.includes(durationSec)) {
        durationSec = allowedDurations[0]
      }
      const refMode =
        data.referenceMode
        || (data.vidMode === "参考" ? "freeref" : data.vidMode === "文生" ? "t2v" : "keyframe")
      const keyframes = data.keyframes || DEFAULT_KEYFRAMES
      const mentionsList = Array.isArray(data.mentions) ? data.mentions : []
      const freeRefs = refMode === "freeref"
        ? mergeMentionRefsIntoFreeRefs(data.freeRefs, mentionsList, getNode)
        : (data.freeRefs || [])

      const scriptTable = (() => {
        const ref = data.scriptTableRef
        if (ref?.nodeId) {
          return getNodes().find((n) => n.id === ref.nodeId) || null
        }
        return findScriptTableNode(getNodes())
      })()
      const qualityPresetId = resolveVideoQualityPresetId(data, scriptTable?.data || null)

      let modelForSubmit = data.modelId || modelId || "wan-2.6"
      // 双帧 + 任意 T2V-only → 自动切 i2v；已选 wan-fun-inpaint 保持不变
      if (
        refMode !== "freeref"
        && refMode !== "t2v"
        && keyframes.first?.imageUrl
        && keyframes.last?.imageUrl
        && modelForSubmit !== "wan-fun-inpaint"
        && (!modelForSubmit || T2V_ONLY.has(modelForSubmit))
      ) {
        modelForSubmit = "wan-i2v"
      }

      if (modelForSubmit === "wan-fun-inpaint") {
        if (refMode === "freeref" || refMode === "t2v" || !keyframes.first?.imageUrl || !keyframes.last?.imageUrl) {
          const msg = "Wan Fun Inpaint 需要首帧与尾帧"
          setErrorMessage(msg)
          data.onUpdate?.(id, { status: "error", error: msg })
          showToast(msg)
          setSending(false)
          return
        }
      }

      const payload = {
        model:           modelForSubmit,
        prompt:          promptForSubmit,
        quality_preset_id: qualityPresetId !== "auto" ? qualityPresetId : undefined,
        sampling_profile: data.samplingProfile === "quality" ? "quality" : "fast",
        mentions:        mentionsList,
        ratio:           data.vidRatio       || "16:9",
        resolution:      data.vidQuality     || "1080P",
        duration:        durationSec,
        audio:           data.vidAudio === "开启",
        count:           data.count          || 1,
        node_id:         id,
        generation_mode: refMode === "freeref" ? "freeref" : "keyframe",
        client_id:       wsManager.getClientId(),
        trace_id:        data.traceId || crypto.randomUUID(),
      }

      // G45: 相连 character-card / 分镜表角色正脸 → 成片后逐帧换脸
      const faceFromCard =
        collectConnectedCharacterFaceUrl(getNodes(), getEdges(), id)
        || (scriptTable?.id
          ? collectConnectedCharacterFaceUrl(getNodes(), getEdges(), scriptTable.id)
          : null)
      const faceFromCast = (() => {
        const cast = scriptTable?.data?.castLibrary || []
        const hit = cast.find((c) => c && c.type !== "scene" && c.imageUrl)
        return hit?.imageUrl || null
      })()
      const reactorFace = faceFromCard || faceFromCast || null
      payload.use_reactor = Boolean(reactorFace)
      if (reactorFace) payload.reactor_face_image = reactorFace

      if (refMode === "freeref") {
        payload.reference_images = freeRefs.map((r) => r.imageUrl).filter(Boolean)
      } else if (refMode !== "t2v") {
        payload.first_frame = keyframes.first?.imageUrl || null
        payload.last_frame = keyframes.last?.imageUrl || null
      }

      console.log("[video-gen] submit payload", JSON.stringify(payload, null, 2))

      lastSubmitParamsRef.current = payload

      const res = await api.post("/api/tasks/video", { ...payload, ...teamIdPayload() })
      console.log("[video-gen] submit response", res.data)
      if (res.data?.task_id) {
        const tid = res.data.task_id
        const comfyPromptId = res.data.comfy_prompt_id || tid
        setTaskId(tid)
        taskIdRef.current = comfyPromptId
        logVideoPollDebug({
          taskId: tid,
          status: res.data.status || "submitted",
          progress: 0,
          clientId: payload.client_id,
          timeoutThreshold: PROGRESS_STALE_MS,
          elapsed: 0,
        })
        data.onUpdate?.(id, {
          status: "generating",
          taskId: tid,
          comfyPromptId,
          progress: 0,
        })
        startTaskPolling(tid)
      }
    } catch (e) {
      stopPolling()
      const msg = parseGenerationError(e, null)
      setStatus("error")
      setErrorMessage(msg)
      data.onUpdate?.(id, { status: "error", error: msg })
      showToast(msg)
      setSending(false)
    }
  }, [
    prompt,
    resIndex,
    duration,
    modelId,
    id,
    data,
    showToast,
    sending,
    modelCapabilities,
    startTaskPolling,
    stopPolling,
    getNode,
    clearNodeTaskState,
  ])

  const handleRetry = useCallback(() => {
    if (sending) return
    const policy = getRetryPolicy(errorMessage || data.error || "")
    if (!policy.retryable) return
    stopPolling()
    setVideoMenu(null)
    setIsPlaying(false)
    clearNodeTaskState("generating")
    setSending(true)
    setStatus("generating")
    generateRef.current?.()
  }, [stopPolling, clearNodeTaskState, sending, errorMessage, data.error])

  const stopEnhancePolling = useCallback(() => {
    const timers = enhancePollTimersRef.current
    if (!timers) return
    if (timers.interval) clearInterval(timers.interval)
    enhancePollTimersRef.current = null
  }, [])

  const startEnhancePolling = useCallback((activeTaskId) => {
    stopEnhancePolling()
    const pollOnce = async () => {
      try {
        const res = await api.get(`/api/tasks/${activeTaskId}`)
        const task = res.data
        const apiStatus = task.status
        if (apiStatus === "completed" && task.result) {
          stopEnhancePolling()
          const url = resolveTaskResultUrl(task.result)
          setEnhancing(false)
          setEnhanceError(null)
          data.onUpdate?.(id, {
            enhanceStatus: "completed",
            enhancedVideoUrl: url,
            enhanceTaskId: activeTaskId,
            enhanceError: null,
          })
          return
        }
        if (apiStatus === "failed") {
          stopEnhancePolling()
          const msg = parseGenerationError(null, task)
          setEnhancing(false)
          setEnhanceError(msg)
          data.onUpdate?.(id, {
            enhanceStatus: "failed",
            enhanceError: msg,
          })
        }
      } catch (e) {
        if (isNetworkError(e)) return
        stopEnhancePolling()
        const msg = parseGenerationError(e, null)
        setEnhancing(false)
        setEnhanceError(msg)
        data.onUpdate?.(id, {
          enhanceStatus: "failed",
          enhanceError: msg,
        })
      }
    }
    pollOnce()
    const interval = setInterval(pollOnce, POLL_INTERVAL_MS)
    enhancePollTimersRef.current = { interval }
  }, [stopEnhancePolling, id, data, t])

  const stopLutPolling = useCallback(() => {
    const timers = lutPollTimersRef.current
    if (!timers) return
    if (timers.interval) clearInterval(timers.interval)
    lutPollTimersRef.current = null
  }, [])

  const startLutPolling = useCallback((activeTaskId) => {
    stopLutPolling()
    const pollOnce = async () => {
      try {
        const res = await api.get(`/api/tasks/${activeTaskId}`)
        const task = res.data
        if (task.status === "completed" && task.result) {
          stopLutPolling()
          const url = resolveTaskResultUrl(task.result)
          data.onUpdate?.(id, {
            lutStatus: "completed",
            lutVideoUrl: url,
            lutTaskId: activeTaskId,
            lutError: null,
          })
          setVideoViewTab("graded")
          return
        }
        if (task.status === "failed") {
          stopLutPolling()
          const msg = parseGenerationError(null, task)
          data.onUpdate?.(id, {
            lutStatus: "failed",
            lutError: msg,
          })
        }
      } catch (e) {
        if (isNetworkError(e)) return
        stopLutPolling()
        data.onUpdate?.(id, {
          lutStatus: "failed",
          lutError: parseGenerationError(e, null),
        })
      }
    }
    pollOnce()
    const interval = setInterval(pollOnce, POLL_INTERVAL_MS)
    lutPollTimersRef.current = { interval }
  }, [stopLutPolling, id, data])

  const autoApplyLut = useCallback(async (sourceUrl) => {
    const st = findScriptTableNode(getNodes())
    if (!st || !isLutActive(st.data)) return
    if (data.lutStatus === "applying") return
    const { canvasId } = useCanvasStore.getState()
    if (!canvasId || !sourceUrl) return
    data.onUpdate?.(id, { lutStatus: "applying", lutError: null })
    try {
      const res = await submitVideoLutTask({
        projectId: canvasId,
        scriptTableNodeId: st.id,
        videoUrl: sourceUrl,
        nodeId: id,
        teamId: getCanvasTeamId(),
      })
      if (res?.task_id) startLutPolling(res.task_id)
    } catch (e) {
      data.onUpdate?.(id, {
        lutStatus: "failed",
        lutError: parseGenerationError(e, null),
      })
    }
  }, [data, getNodes, id, startLutPolling])

  useEffect(() => {
    autoApplyLutRef.current = autoApplyLut
  }, [autoApplyLut])

  useEffect(() => {
    if (!data.lutTaskId || data.lutStatus !== "applying") return undefined
    startLutPolling(data.lutTaskId)
    return () => stopLutPolling()
  }, [data.lutTaskId, data.lutStatus, startLutPolling, stopLutPolling])

  useEffect(() => () => stopLutPolling(), [stopLutPolling])

  const applyEnhanceParams = useCallback((params, reasoning = "") => {
    if (!params) return
    const upscale = Number(params.upscale_factor ?? enhanceUpscaleFactor)
    const strength = params.strength || enhanceStrength
    const noise = Number(params.input_noise_scale ?? enhanceInputNoiseScale)
    const batch = Number(params.batch_size ?? enhanceBatchSize)
    const color = params.color_correction || enhanceColorCorrection
    const modelSize = params.model_size || enhanceModelSize

    setEnhanceUpscaleFactor(upscale)
    setEnhanceStrength(strength)
    setEnhanceInputNoiseScale(noise)
    setEnhanceBatchSize(batch)
    setEnhanceColorCorrection(color)
    setEnhanceModelSize(modelSize)
    if (reasoning) setEnhanceReasoning(reasoning)

    data.onUpdate?.(id, {
      enhanceUpscaleFactor: upscale,
      enhanceStrength: strength,
      enhanceInputNoiseScale: noise,
      enhanceBatchSize: batch,
      enhanceColorCorrection: color,
      enhanceModelSize: modelSize,
      enhanceReasoning: reasoning || data.enhanceReasoning,
    })
    notifyVideoEnhanceBridge()
  }, [
    id,
    data,
    enhanceUpscaleFactor,
    enhanceStrength,
    enhanceInputNoiseScale,
    enhanceBatchSize,
    enhanceColorCorrection,
    enhanceModelSize,
    data.enhanceReasoning,
  ])

  const submitEnhanceTask = useCallback(async (params) => {
    const sourceUrl = toRelativeMediaUrl(videoUrl || data.videoUrl || null)
    if (!sourceUrl || enhancing || enhanceAnalyzing) return
    stopEnhancePolling()
    setEnhancing(true)
    setEnhanceError(null)
    data.onUpdate?.(id, {
      enhanceStatus: "enhancing",
      enhanceError: null,
      enhanceUpscaleFactor: params.upscale_factor,
      enhanceStrength: params.strength,
      enhanceInputNoiseScale: params.input_noise_scale,
      enhanceBatchSize: params.batch_size,
      enhanceColorCorrection: params.color_correction,
      enhanceModelSize: params.model_size,
    })
    try {
      const res = await api.post("/api/tasks/video-enhance", {
        video_url: sourceUrl,
        upscale_factor: params.upscale_factor,
        strength: params.strength,
        workflow: "auto",
        input_noise_scale: params.input_noise_scale,
        batch_size: params.batch_size,
        color_correction: params.color_correction,
        model_size: params.model_size,
        node_id: id,
        client_id: wsManager.getClientId(),
        ...teamIdPayload(),
      })
      const tid = res.data?.task_id
      if (!tid) throw new Error(t("canvas.gen.failed"))
      data.onUpdate?.(id, { enhanceTaskId: tid })
      startEnhancePolling(tid)
    } catch (e) {
      const status = e?.response?.status
      const msg =
        status === 503
          ? t("canvas.video.enhanceUnavailable")
          : parseGenerationError(e, null)
      setEnhancing(false)
      setEnhanceError(msg)
      data.onUpdate?.(id, {
        enhanceStatus: "failed",
        enhanceError: msg,
      })
      showToast(msg)
    }
  }, [
    videoUrl,
    data.videoUrl,
    enhancing,
    enhanceAnalyzing,
    stopEnhancePolling,
    id,
    data,
    startEnhancePolling,
    showToast,
    t,
  ])

  const buildEnhancePayload = useCallback(() => ({
    upscale_factor: enhanceUpscaleFactor,
    strength: enhanceStrength,
    input_noise_scale: enhanceInputNoiseScale,
    batch_size: enhanceBatchSize,
    color_correction: enhanceColorCorrection,
    model_size: enhanceModelSize,
  }), [
    enhanceUpscaleFactor,
    enhanceStrength,
    enhanceInputNoiseScale,
    enhanceBatchSize,
    enhanceColorCorrection,
    enhanceModelSize,
  ])

  const fetchRecommendParams = useCallback(async (sourceUrl) => {
    const { canvasId } = useCanvasStore.getState()
    const scriptTable = findScriptTableNode(getNodes())
    const submit = await api.post(
      "/api/tasks/video-enhance/recommend-params",
      {
        video_url: sourceUrl,
        project_id: canvasId || undefined,
        script_table_node_id: scriptTable?.id || undefined,
      },
      { timeout: 30000 }
    )
    let params = submit.data?.params
    let reasoning = submit.data?.reasoning || ""
    const taskId = submit.data?.task_id
    if (taskId) {
      const task = await pollTaskUntilDone(taskId, {
        timeoutMessage: "视频分析超时，请稍后重试",
      })
      params = task.result?.params
      reasoning = task.result?.reasoning || ""
    }
    if (!params) throw new Error(t("canvas.gen.failed"))
    applyEnhanceParams(params, reasoning)
    return params
  }, [applyEnhanceParams, t, getNodes])

  const handleSmartEnhance = useCallback(async () => {
    const sourceUrl = toRelativeMediaUrl(videoUrl || data.videoUrl || null)
    if (!sourceUrl || enhancing || enhanceAnalyzing) return

    try {
      let params = buildEnhancePayload()
      if (!enhanceManualMode) {
        setEnhanceAnalyzing(true)
        try {
          params = await fetchRecommendParams(sourceUrl)
        } finally {
          setEnhanceAnalyzing(false)
        }
      }
      await submitEnhanceTask(params)
    } catch (e) {
      setEnhanceAnalyzing(false)
      const msg = parseGenerationError(e, null)
      setEnhanceError(msg)
      data.onUpdate?.(id, { enhanceError: msg })
      showToast(msg)
    }
  }, [
    videoUrl,
    data.videoUrl,
    enhancing,
    enhanceAnalyzing,
    enhanceManualMode,
    buildEnhancePayload,
    fetchRecommendParams,
    submitEnhanceTask,
    id,
    data,
    showToast,
  ])

  const handleEnhance = handleSmartEnhance

  const handleEnhanceRetry = useCallback(() => {
    const policy = getRetryPolicy(enhanceError || data.enhanceError || "")
    if (!policy.retryable || enhancing) return
    handleEnhance()
  }, [enhanceError, data.enhanceError, enhancing, handleEnhance])

  const handleEnhanceUpscaleChange = useCallback((factor) => {
    setEnhanceUpscaleFactor(factor)
    data.onUpdate?.(id, { enhanceUpscaleFactor: factor })
    notifyVideoEnhanceBridge()
  }, [id, data])

  const handleEnhanceStrengthChange = useCallback((next) => {
    setEnhanceStrength(next)
    data.onUpdate?.(id, { enhanceStrength: next })
    notifyVideoEnhanceBridge()
  }, [id, data])

  const handleEnhanceInputNoiseScaleChange = useCallback((next) => {
    setEnhanceInputNoiseScale(next)
    data.onUpdate?.(id, { enhanceInputNoiseScale: next })
    notifyVideoEnhanceBridge()
  }, [id, data])

  const handleEnhanceBatchSizeChange = useCallback((next) => {
    setEnhanceBatchSize(next)
    data.onUpdate?.(id, { enhanceBatchSize: next })
    notifyVideoEnhanceBridge()
  }, [id, data])

  const handleEnhanceColorCorrectionChange = useCallback((next) => {
    setEnhanceColorCorrection(next)
    data.onUpdate?.(id, { enhanceColorCorrection: next })
    notifyVideoEnhanceBridge()
  }, [id, data])

  const handleEnhanceModelSizeChange = useCallback((next) => {
    setEnhanceModelSize(next)
    data.onUpdate?.(id, { enhanceModelSize: next })
    notifyVideoEnhanceBridge()
  }, [id, data])

  const handleEnhanceManualModeChange = useCallback((next) => {
    setEnhanceManualMode(next)
    data.onUpdate?.(id, { enhanceManualMode: next })
    notifyVideoEnhanceBridge()
  }, [id, data])

  const handleEnhanceAdvancedOpenChange = useCallback(async (open) => {
    setEnhanceAdvancedOpen(open)
    if (!open || enhanceReasoning) return
    const sourceUrl = toRelativeMediaUrl(videoUrl || data.videoUrl || null)
    if (!sourceUrl) return
    try {
      setEnhanceAnalyzing(true)
      await fetchRecommendParams(sourceUrl)
    } catch {
      // 预填失败时保留默认值，不阻断高级面板
    } finally {
      setEnhanceAnalyzing(false)
    }
  }, [enhanceReasoning, videoUrl, data.videoUrl, fetchRecommendParams])

  const handleDownloadEnhanced = useCallback(async () => {
    const url = ensureMediaUrl(data.enhancedVideoUrl || null)
    if (!url) return
    try {
      await downloadMediaUrl(url, "video-enhanced")
    } catch (err) {
      console.error("[video-gen] enhanced download failed:", err)
      showToast(t("canvas.video.downloadFail"))
    }
  }, [data.enhancedVideoUrl, showToast, t])

  useEffect(() => () => stopEnhancePolling(), [stopEnhancePolling])

  useEffect(() => {
    if (!data.enhanceTaskId || data.enhanceStatus !== "enhancing") return undefined
    if (enhancing) return undefined
    setEnhancing(true)
    startEnhancePolling(data.enhanceTaskId)
    return undefined
  }, [data.enhanceTaskId, data.enhanceStatus, enhancing, startEnhancePolling])

  const handleStopGeneration = useCallback(async () => {
    const activeId = taskId || data.taskId
    stopPolling()
    setSending(false)
    if (activeId) {
      try {
        await cancelCanvasTask(activeId)
      } catch (err) {
        console.error("[video-gen] cancel failed:", err)
      }
    }
    setStatus("error")
    setErrorMessage(t("canvas.gen.stopped"))
    data.onUpdate?.(id, {
      status: "error",
      error: t("canvas.gen.stopped"),
      progress: 0,
    })
  }, [taskId, data, id, stopPolling, t])

  const handleDelete = useCallback(() => {
    if (data.onDelete) data.onDelete(id)
  }, [id, data])

  useEffect(() => { generateRef.current = handleGenerate }, [handleGenerate])

  useEffect(() => {
    if (!data.pendingTrigger) return
    data.onUpdate?.(id, { pendingTrigger: null })
    setTimeout(() => generateRef.current?.(), 30)
  }, [data.pendingTrigger])

  const isIdle = status === "input" && !data.videoUrl && !videoUrl
  const showUploadRow = isIdle && (selected || isRefSource)
  const uploadRef = useRef(null)
  const setAssetLibraryOpen = useCanvasStore((s) => s.setAssetLibraryOpen)

  const openAssetLibrary = useCallback(() => {
    setAssetLibraryOpen(true)
    useCanvasStore.getState().setGenHistoryOpen(false)
  }, [setAssetLibraryOpen])

  const handleTopUpload = useCallback(async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const url = await uploadImageFile(file)
      const kf = data.keyframes || DEFAULT_KEYFRAMES
      data.onUpdate?.(id, {
        referenceMode: "keyframe",
        keyframes: {
          ...kf,
          first: { ...(kf.first || {}), imageUrl: url, enabled: true },
        },
      })
    } catch (err) {
      console.error("上传失败", err)
    }
    e.target.value = ""
  }, [id, data])

  const activeGeneration =
    status === "generating" ||
    sending ||
    data.status === "generating" ||
    data.status === "pending" ||
    data.status === "queued"
  const isGenerating = activeGeneration
  const playbackUrl = activeGeneration
    ? null
    : ensureMediaUrl(videoUrl || data.videoUrl || null)
  const isDone =
    !activeGeneration &&
    !!playbackUrl &&
    status !== "error" &&
    status !== "timeout" &&
    (status === "completed" || data.status === "completed")
  const isError = status === "error"
  const isTimeout = status === "timeout"
  const retryPolicy = useMemo(
    () => getRetryPolicy(errorMessage || data.error || ""),
    [errorMessage, data.error]
  )
  const enhancedPlaybackUrl = data.enhancedVideoUrl
    ? ensureMediaUrl(data.enhancedVideoUrl)
    : null
  const lutPlaybackUrl = data.lutVideoUrl
    ? ensureMediaUrl(data.lutVideoUrl)
    : null
  const displayPlaybackUrl =
    videoViewTab === "graded" && lutPlaybackUrl ? lutPlaybackUrl : playbackUrl
  const enhanceStatus = data.enhanceStatus || "idle"
  const enhanceRetryPolicy = useMemo(
    () => getRetryPolicy(enhanceError || data.enhanceError || ""),
    [enhanceError, data.enhanceError]
  )
  const isEnhancing = enhancing || enhanceStatus === "enhancing"
  const showEnhanceFailed =
    enhanceStatus === "failed" || (!!enhanceError && !enhancedPlaybackUrl)

  useEffect(() => {
    enhanceBridgeRef.current = {
      videoReady: isDone && !!playbackUrl,
      isEnhancing,
      isAnalyzing: enhanceAnalyzing,
      hasEnhanced: !!enhancedPlaybackUrl,
      manualMode: enhanceManualMode,
      advancedOpen: enhanceAdvancedOpen,
      reasoning: enhanceReasoning,
      upscaleFactor: enhanceUpscaleFactor,
      strength: enhanceStrength,
      inputNoiseScale: enhanceInputNoiseScale,
      batchSize: enhanceBatchSize,
      colorCorrection: enhanceColorCorrection,
      modelSize: enhanceModelSize,
      error: enhanceError || data.enhanceError || null,
      onUpscaleChange: handleEnhanceUpscaleChange,
      onStrengthChange: handleEnhanceStrengthChange,
      onInputNoiseScaleChange: handleEnhanceInputNoiseScaleChange,
      onBatchSizeChange: handleEnhanceBatchSizeChange,
      onColorCorrectionChange: handleEnhanceColorCorrectionChange,
      onModelSizeChange: handleEnhanceModelSizeChange,
      onManualModeChange: handleEnhanceManualModeChange,
      onAdvancedOpenChange: handleEnhanceAdvancedOpenChange,
      onOneClick: handleSmartEnhance,
      onCancel: () => {},
    }
    setVideoEnhanceBridge(id, enhanceBridgeRef)
    notifyVideoEnhanceBridge()
  }, [
    id,
    isDone,
    playbackUrl,
    isEnhancing,
    enhancedPlaybackUrl,
    enhanceUpscaleFactor,
    enhanceStrength,
    enhanceInputNoiseScale,
    enhanceBatchSize,
    enhanceColorCorrection,
    enhanceModelSize,
    enhanceManualMode,
    enhanceReasoning,
    enhanceAnalyzing,
    enhanceAdvancedOpen,
    enhanceError,
    data.enhanceError,
    handleEnhanceUpscaleChange,
    handleEnhanceStrengthChange,
    handleEnhanceInputNoiseScaleChange,
    handleEnhanceBatchSizeChange,
    handleEnhanceColorCorrectionChange,
    handleEnhanceModelSizeChange,
    handleEnhanceManualModeChange,
    handleEnhanceAdvancedOpenChange,
    handleSmartEnhance,
  ])

  useEffect(() => () => setVideoEnhanceBridge(id, null), [id])

  const handleDownloadVideo = useCallback(async () => {
    if (!playbackUrl) return
    try {
      await downloadMediaUrl(playbackUrl, "video")
    } catch (err) {
      console.error("[video-gen] download failed:", err)
      showToast(t("canvas.video.downloadFail"))
    }
  }, [playbackUrl, showToast, t])

  const rootRef = useRef(null)
  useCanvasNodeWheel(rootRef)
  const [fullscreenSrc, setFullscreenSrc] = useState(null)
  const [leftVisible, setLeftVisible] = useState(false)
  const [rightVisible, setRightVisible] = useState(false)
  const plusPinned = selected

  const closeVideoMenu = useCallback(() => {
    setVideoMenu(null)
    setEnhanceMenuOpen(false)
  }, [])

  useEffect(() => {
    if (!videoMenu) return undefined
    const onDocDown = (e) => {
      if (videoMenuPortalRef.current?.contains(e.target)) return
      markSuppressPaneMenu()
      closeVideoMenu()
    }
    document.addEventListener("mousedown", onDocDown)
    return () => document.removeEventListener("mousedown", onDocDown)
  }, [videoMenu, closeVideoMenu])

  useEffect(() => {
    if (activeGeneration) {
      setIsPlaying(false)
      return
    }
    setIsPlaying(false)
    if (videoUrl) {
      console.log("[video-gen] videoUrl updated:", videoUrl)
    }
  }, [videoUrl, activeGeneration])

  const handleTogglePlay = useCallback((e) => {
    stopFlowPointer(e)
    const el = videoRef.current
    if (!el) return
    if (el.paused) {
      el.play().then(() => setIsPlaying(true)).catch(() => {})
    } else {
      el.pause()
      setIsPlaying(false)
    }
  }, [])

  const seekFromClientX = useCallback((clientX, barEl) => {
    const el = videoRef.current
    if (!el || !barEl || !playbackDuration || !Number.isFinite(playbackDuration)) return
    const rect = barEl.getBoundingClientRect()
    if (!rect.width) return
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
    el.currentTime = ratio * playbackDuration
    setPlaybackProgress(el.currentTime)
  }, [playbackDuration])

  const handlePlaybackBarPointerDown = useCallback((e) => {
    stopFlowPointer(e)
    e.preventDefault()
    const barEl = e.currentTarget
    const el = videoRef.current
    if (!el || !playbackDuration) return
    wasPlayingBeforeScrubRef.current = !el.paused
    if (!el.paused) {
      el.pause()
      setIsPlaying(false)
    }
    isScrubbingRef.current = true
    setIsScrubbing(true)
    barEl.setPointerCapture(e.pointerId)
    seekFromClientX(e.clientX, barEl)
  }, [playbackDuration, seekFromClientX])

  const handlePlaybackBarPointerMove = useCallback((e) => {
    if (!isScrubbingRef.current) return
    stopFlowPointer(e)
    seekFromClientX(e.clientX, e.currentTarget)
  }, [seekFromClientX])

  const handlePlaybackBarPointerUp = useCallback((e) => {
    if (!isScrubbingRef.current) return
    stopFlowPointer(e)
    isScrubbingRef.current = false
    setIsScrubbing(false)
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      /* already released */
    }
    const el = videoRef.current
    if (el && wasPlayingBeforeScrubRef.current) {
      el.play().then(() => setIsPlaying(true)).catch(() => {})
    }
  }, [])

  const nodeZIndex = data.zIndex ?? 0
  const hasStyleRef = !!data.styleReference
  const styleRefTitle = hasStyleRef ? styleReferenceSummary(data.styleReference) : ""

  return (
    <div
      className={`gn2-wrapper${isRefSource ? " gn2-wrapper--ref-source" : ""}`}
      style={{ zIndex: nodeZIndex }}
    >
      <div className={`gn2-upload-row${showUploadRow ? " gn2-upload-row--visible" : ""}`}>
        <div className="gn2-upload-bar">
          <button type="button" className="gn2-upload-btn nodrag" aria-label={t("canvas.common.upload")} onClick={() => uploadRef.current?.click()}>
            <UploadIcon /> {t("canvas.common.upload")}
          </button>
          <span className="gn2-upload-divider" aria-hidden="true" />
          <button type="button" className="gn2-upload-btn nodrag" aria-label={t("canvas.image.fromLibrary")} onClick={openAssetLibrary}>
            <AssetLibraryIcon /> {t("canvas.image.fromLibrary")}
          </button>
        </div>
        <input ref={uploadRef} type="file" accept="image/*" hidden onChange={handleTopUpload} aria-label={t("canvas.common.upload")} />
      </div>

      <div className="gn2-label-row">
        <NodeLabelIcon />
        <EditableNodeLabel nodeId={id} data={data} defaultLabel="Video" className="gn2-label-text" />
        {hasStyleRef ? (
          <span className="gn2-style-ref-badge nodrag nopan" title={styleRefTitle} aria-label={styleRefTitle}>
            <IconStyleRef />
          </span>
        ) : null}
        <NodeLastEditedMeta meta={data?.meta} />
      </div>

      <div
        ref={rootRef}
        className={`gn2-root gn2-root--video${selected ? " gn2-root--selected" : ""}`}
      >
        {/* Target handle — tgt, top:50% relative to gn2-root */}
        <Handle type="target" position={Position.Left} id="tgt" style={{ position: 'absolute', top: '50%', left: -1, width: 1, height: 1, minWidth: 1, minHeight: 1, background: 'transparent', border: 'none', opacity: 0, transform: 'translateY(-50%)', zIndex: 25 }} />

        {/* Source handles: large hit area centered on card edge */}
        <Handle type="source" position={Position.Left}  id="src-left"  className="gn2-edge-handle gn2-edge-handle--left"
          onMouseEnter={() => setLeftVisible(true)} onMouseLeave={() => { if (!plusPinned) setLeftVisible(false) }} />
        <Handle type="source" position={Position.Right} id="src-right" className="gn2-edge-handle gn2-edge-handle--right"
          onMouseEnter={() => setRightVisible(true)} onMouseLeave={() => { if (!plusPinned) setRightVisible(false) }} />

        {/* Left zone: hover container + sliding visual button */}
        <div
          className={`gn2-plus-left-zone nodrag${leftVisible || plusPinned ? ' gn2-plus-zone--visible' : ''}`}
          onMouseEnter={() => setLeftVisible(true)}
          onMouseLeave={() => { if (!plusPinned) setLeftVisible(false) }}
          onClick={(e) => { e.stopPropagation(); canvasActions?.openPickerAt(e.clientX - 20, e.clientY, { toLeft: true, targetNodeId: id }) }}
        >
          <div className="gn2-plus-btn-visual">+</div>
        </div>

        {/* Right zone: hover container + sliding visual button */}
        <div
          className={`gn2-plus-right-zone nodrag${rightVisible || plusPinned ? ' gn2-plus-zone--visible' : ''}`}
          onMouseEnter={() => setRightVisible(true)}
          onMouseLeave={() => { if (!plusPinned) setRightVisible(false) }}
          onClick={(e) => { e.stopPropagation(); canvasActions?.openPickerAt(e.clientX + 20, e.clientY, { fromEdge: true, sourceNodeId: id, sourceNodeType: 'video-gen' }) }}
        >
          <div className="gn2-plus-btn-visual">+</div>
        </div>

        <div className="gn2-preview">
          {hasStyleRef ? (
            <div
              className="gn2-style-ref-corner nodrag nopan"
              title={styleRefTitle}
              aria-label={styleRefTitle}
            >
              <IconStyleRef />
            </div>
          ) : null}
          {isRefSource && (
            <div className="gn2-ref-source-overlay nodrag nopan">
              <span className="gn2-ref-esc-hint"><kbd>ESC</kbd> {t("canvas.video.escPick")}</span>
            </div>
          )}
          {isIdle && !isRefSource && <div className="gn2-placeholder"><VideoPlaceholderIcon /></div>}
          {isGenerating && (
            <div className="gn2-generating">
              <div className="gn2-progress-fill" style={{ height: `${progress}%` }} />
              <div className="gn2-generating-info">
                <GenerationBrandLoader />
                <span className="gn2-pct">{progress}%</span>
                <GenerationStopButton onStop={handleStopGeneration} />
              </div>
            </div>
          )}
          {isDone && displayPlaybackUrl && (
            <div className="gn2-video-wrap">
              {lutPlaybackUrl && (
                <div className="gn2-lut-tabs nodrag nopan" onPointerDown={stopFlowPointer}>
                  <button
                    type="button"
                    className={`gn2-lut-tab${videoViewTab === "graded" ? " gn2-lut-tab--active" : ""}`}
                    onClick={() => setVideoViewTab("graded")}
                  >
                    {t("canvas.video.lutGraded")}
                  </button>
                  <button
                    type="button"
                    className={`gn2-lut-tab${videoViewTab === "original" ? " gn2-lut-tab--active" : ""}`}
                    onClick={() => setVideoViewTab("original")}
                  >
                    {t("canvas.video.lutOriginal")}
                  </button>
                </div>
              )}
              <video
                key={`${mediaRevision}:${displayPlaybackUrl}`}
                ref={videoRef}
                className="gn2-result-video"
                src={displayPlaybackUrl}
                loop
                muted
                playsInline
                preload="metadata"
                controls={false}
                draggable={false}
                onDragStart={(e) => e.preventDefault()}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
                onLoadedData={() => {
                  console.log("[video-gen] video loaded:", playbackUrl)
                }}
                onLoadedMetadata={(e) => {
                  setPlaybackDuration(e.currentTarget.duration || 0)
                  setPlaybackProgress(0)
                }}
                onTimeUpdate={(e) => {
                  if (isScrubbingRef.current) return
                  setPlaybackProgress(e.currentTarget.currentTime || 0)
                }}
                onError={(e) => {
                  const el = e.currentTarget
                  const code = el?.error?.code
                  const hint =
                    code === 4
                      ? "视频格式无法在浏览器中播放"
                      : "视频加载失败，请检查 /api/view 代理与 Range 支持"
                  console.error("[video-gen] <video> load error", {
                    src: el?.src,
                    networkState: el?.networkState,
                    code,
                    hint,
                    error: el?.error,
                  })
                }}
                style={{ pointerEvents: "none", width: "100%", height: "100%" }}
              />
              <div
                className="gn2-video-play-zone nodrag nopan"
                onPointerDown={stopFlowPointer}
                onMouseDown={stopFlowPointer}
              >
                <button
                  type="button"
                  className="gn2-video-play-btn nodrag nopan"
                  aria-label={isPlaying ? t("canvas.video.pause") : t("canvas.video.play")}
                  onPointerDown={stopFlowPointer}
                  onMouseDown={stopFlowPointer}
                  onClick={handleTogglePlay}
                >
                  {isPlaying ? (
                    <svg width="28" height="28" viewBox="0 0 28 28" fill="currentColor" aria-hidden>
                      <rect x="6" y="5" width="5" height="18" rx="1" />
                      <rect x="17" y="5" width="5" height="18" rx="1" />
                    </svg>
                  ) : (
                    <svg width="28" height="28" viewBox="0 0 28 28" fill="currentColor" aria-hidden>
                      <path d="M9 6l14 8-14 8V6z" />
                    </svg>
                  )}
                </button>
              </div>
              <div
                className={`gn2-video-playback-bar nodrag nopan${isScrubbing ? " gn2-video-playback-bar--scrubbing" : ""}`}
                onPointerDown={handlePlaybackBarPointerDown}
                onPointerMove={handlePlaybackBarPointerMove}
                onPointerUp={handlePlaybackBarPointerUp}
                onPointerCancel={handlePlaybackBarPointerUp}
              >
                <div
                  className="gn2-video-playback-fill"
                  style={{
                    width: playbackDuration
                      ? `${(playbackProgress / playbackDuration) * 100}%`
                      : "0%",
                  }}
                />
              </div>
              <div
                className="gn2-video-dots-wrap nodrag nopan"
                onPointerDown={stopFlowPointer}
                onMouseDown={stopFlowPointer}
                onClick={stopFlowPointer}
              >
                <button
                  type="button"
                  className="cell-dots-btn nodrag nopan"
                  aria-label={t("canvas.video.moreActions")}
                  onPointerDown={stopFlowPointer}
                  onMouseDown={stopFlowPointer}
                  onClick={(e) => {
                    stopFlowPointer(e)
                    const rect = e.currentTarget.getBoundingClientRect()
                    const menuPos = computeVideoMenuPos(rect)
                    setVideoMenu((prev) => (prev ? null : { menuPos, playbackUrl }))
                  }}
                >
                  ⋯
                </button>
              </div>
            </div>
          )}
          {(isError || isTimeout) && (
            <div className="gn2-error-area">
              <span className="gn2-error-icon">⚠</span>
              <span className="gn2-error-msg">
                {isTimeout
                  ? t("canvas.gen.timeout")
                  : (errorMessage === networkErrorMessage()
                    ? t("canvas.gen.failBackend")
                    : (errorMessage || t("canvas.gen.failed")))}
              </span>
              <button
                className="gn2-retry-btn nodrag"
                onClick={handleRetry}
                disabled={sending || !retryPolicy.retryable}
                title={
                  !retryPolicy.retryable
                    ? t("canvas.gen.retryBlocked", { reason: retryPolicy.reason })
                    : undefined
                }
              >
                {t("canvas.gen.retryClick")}
              </button>
            </div>
          )}
        </div>

        {isDone && (showEnhanceFailed || enhancedPlaybackUrl) && (
          <div
            className="gn2-enhance-section nodrag nopan"
            onPointerDown={stopFlowPointer}
            onMouseDown={stopFlowPointer}
          >
            {showEnhanceFailed && (
              <div className="gn2-enhance-error">
                <span>{enhanceError || data.enhanceError}</span>
                <button
                  type="button"
                  className="gn2-retry-btn nodrag nopan"
                  onClick={handleEnhanceRetry}
                  disabled={isEnhancing || !enhanceRetryPolicy.retryable}
                >
                  {t("canvas.video.enhanceRetry")}
                </button>
              </div>
            )}
            {enhancedPlaybackUrl && (
              <div className="gn2-enhance-compare">
                <div className="gn2-enhance-compare-col">
                  <span className="gn2-enhance-compare-label">{t("canvas.video.originalLabel")}</span>
                  <video
                    className="gn2-enhance-compare-video"
                    src={playbackUrl}
                    muted
                    playsInline
                    controls
                    preload="metadata"
                  />
                </div>
                <div className="gn2-enhance-compare-col">
                  <span className="gn2-enhance-compare-label">{t("canvas.video.enhancedLabel")}</span>
                  <video
                    className="gn2-enhance-compare-video"
                    src={enhancedPlaybackUrl}
                    muted
                    playsInline
                    controls
                    preload="metadata"
                  />
                </div>
              </div>
            )}
          </div>
        )}

      </div>

      <div className="gn2-camera-row nodrag nopan" onPointerDown={(e) => e.stopPropagation()}>
        <button
          type="button"
          className={`gn2-camera-summary nodrag nopan${cameraPickerOpen ? " gn2-camera-summary--open" : ""}`}
          onClick={(e) => {
            e.stopPropagation()
            setCameraPickerOpen((v) => !v)
          }}
        >
          {cameraSummaryLabel}
        </button>
        {cameraPickerOpen ? (
          <div className="gn2-camera-picker-pop nodrag nopan">
            <CameraMotionPicker
              cameraMove={cameraMove}
              shotScale={shotScale}
              onChange={handleCardCameraMotionChange}
              readOnly={false}
            />
          </div>
        ) : null}
      </div>

      {toast && (
        <div className="gn2-toast nodrag" onPointerDown={(e) => e.stopPropagation()}>
          {toast}
        </div>
      )}

      <MediaFullscreenViewer
        src={fullscreenSrc}
        kind="video"
        onClose={() => setFullscreenSrc(null)}
      />

      {videoMenu &&
        createPortal(
          <div
            ref={videoMenuPortalRef}
            className={`cell-menu-portal gn2-dots-menu nodrag nopan ${getThemePageClass()}`}
            style={{
              position: "fixed",
              top: videoMenu.menuPos.y,
              left: videoMenu.menuPos.x,
              zIndex: Z_NODE_DOTS_MENU,
            }}
            onPointerDown={stopFlowPointer}
            onMouseDown={stopFlowPointer}
            onClick={stopFlowPointer}
          >
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                stopFlowPointer(e)
                handleTogglePlay(e)
                closeVideoMenu()
              }}
            >
              <span>{isPlaying ? "⏸" : "▶"}</span>
              {isPlaying ? t("canvas.video.pause") : t("canvas.video.play")}
            </button>
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                stopFlowPointer(e)
                setFullscreenSrc(videoMenu.playbackUrl)
                closeVideoMenu()
              }}
            >
              <IconZoom />
              {t("canvas.image.zoom")}
            </button>
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                stopFlowPointer(e)
                handleDownloadVideo()
                closeVideoMenu()
              }}
            >
              <span>⬇</span>{t("canvas.video.download")}
            </button>
            {isDone && (
              <>
                {!enhancedPlaybackUrl && (
                  <div className="gn2-dots-item-row">
                    <button
                      type="button"
                      className={`gn2-dots-item nodrag nopan${enhanceMenuOpen ? " gn2-dots-item--submenu-open" : ""}`}
                      onClick={(e) => {
                        stopFlowPointer(e)
                        setEnhanceMenuOpen((v) => !v)
                      }}
                    >
                      <IconEnhance />
                      {t("canvas.video.enhance")}
                    </button>
                    {enhanceMenuOpen && (
                      <div className="cell-dots-submenu gn2-dots-enhance-submenu nodrag nopan">
                        <VideoEnhancePanel
                          variant="menu"
                          videoReady={isDone && !!playbackUrl}
                          isEnhancing={isEnhancing}
                          isAnalyzing={enhanceAnalyzing}
                          hasEnhanced={!!enhancedPlaybackUrl}
                          manualMode={enhanceManualMode}
                          advancedOpen={enhanceAdvancedOpen}
                          reasoning={enhanceReasoning}
                          upscaleFactor={enhanceUpscaleFactor}
                          strength={enhanceStrength}
                          inputNoiseScale={enhanceInputNoiseScale}
                          batchSize={enhanceBatchSize}
                          colorCorrection={enhanceColorCorrection}
                          modelSize={enhanceModelSize}
                          error={enhanceError}
                          onManualModeChange={handleEnhanceManualModeChange}
                          onAdvancedOpenChange={handleEnhanceAdvancedOpenChange}
                          onUpscaleChange={handleEnhanceUpscaleChange}
                          onStrengthChange={handleEnhanceStrengthChange}
                          onInputNoiseScaleChange={handleEnhanceInputNoiseScaleChange}
                          onBatchSizeChange={handleEnhanceBatchSizeChange}
                          onColorCorrectionChange={handleEnhanceColorCorrectionChange}
                          onModelSizeChange={handleEnhanceModelSizeChange}
                          onOneClick={() => {
                            handleSmartEnhance()
                            setEnhanceMenuOpen(false)
                            closeVideoMenu()
                          }}
                          onCancel={() => setEnhanceMenuOpen(false)}
                        />
                      </div>
                    )}
                  </div>
                )}
                {enhancedPlaybackUrl && (
                  <button
                    type="button"
                    className="gn2-dots-item nodrag nopan"
                    onClick={(e) => {
                      stopFlowPointer(e)
                      handleDownloadEnhanced()
                      closeVideoMenu()
                    }}
                  >
                    <span>⬇</span>{t("canvas.video.downloadEnhanced")}
                  </button>
                )}
              </>
            )}
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                stopFlowPointer(e)
                closeVideoMenu()
                handleRetry()
              }}
            >
              <span>↻</span>{t("canvas.gen.regenerate")}
            </button>
          </div>,
          getThemePortalRoot()
        )}
    </div>
  )
}
