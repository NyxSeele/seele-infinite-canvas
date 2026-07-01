import { useState, useCallback, useEffect, useRef, useMemo } from "react"
import { createPortal } from "react-dom"
import { useModelStore, useCanvasStore } from "../../stores"
import { pushGenHistory } from "../../utils/canvas/genHistory"
import { Handle, Position, useReactFlow, useStore } from "reactflow"
import api from "../../services/api"
import { getCanvasTeamId, teamIdPayload } from "../../utils/teamContext"
import { cancelCanvasTask } from "../../services/cancelTask"
import { buildMediaViewUrl, resolveTaskResultUrl } from "../../utils/mediaViewUrl"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { downloadMediaUrl } from "../../utils/downloadMedia"
import MediaFullscreenViewer from "./MediaFullscreenViewer"
import GenerationStopButton from "./GenerationStopButton"
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
import { normalizeProgressPercent, logVideoPollDebug } from "./videoProgressSync"
import useModelCapabilities from "../../hooks/useModelCapabilities"
import { uploadImageFile } from "../../services/uploadImage"
import { useLocale } from "../../utils/locale"
import { appendStyleReferenceToDescription, styleReferenceSummary } from "../../utils/canvas/styleReferenceFormat"
import { IconStyleRef } from "./CanvasTopbarIcons"
import { useCanvasNodeWheel } from "./canvasScrollHelpers"

const POLL_INTERVAL_MS = 2000
const VIDEO_MENU_WIDTH = 160
const VIDEO_MENU_EST_HEIGHT = 180

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
import "./CanvasShared.css"
import "./GenerationCardNode.css"
import "./VideoGenerationNode.css"
import "./VideoReferencePanel.css"

export { default as VideoReferencePanel } from "./VideoReferencePanel"

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
  const [videoMenu, setVideoMenu] = useState(null)
  const videoMenuPortalRef = useRef(null)
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

  useEffect(() => {
    if (videoModels.length > 0 && !modelId) {
      setModelId(videoModels[0].id || videoModels[0].display_name || "")
    }
  }, [videoModels])

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

  const applyProgress = useCallback((pct) => {
    const p = Math.min(100, Math.max(0, Number(pct) || 0))
    setProgress(p)
    staleGuardRef.current?.bump(p)
    data.onUpdate?.(id, { progress: p })
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
        failTask("error", msg.data?.exception_message || t("canvas.gen.failed"))
      }
    })
    return remove
  }, [status, failTask, stopPolling, id, data, applyProgress, t])

  const showToast = useCallback((msg) => {
    clearTimeout(toastTimerRef.current)
    setToast(msg)
    toastTimerRef.current = setTimeout(() => setToast(null), 2000)
  }, [])

  const { getNode } = useReactFlow()
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
        || (data.vidMode === "参考" ? "freeref" : "keyframe")
      const keyframes = data.keyframes || DEFAULT_KEYFRAMES
      const mentionsList = Array.isArray(data.mentions) ? data.mentions : []
      const freeRefs = refMode === "freeref"
        ? mergeMentionRefsIntoFreeRefs(data.freeRefs, mentionsList, getNode)
        : (data.freeRefs || [])

      const payload = {
        model:           data.modelId        || modelId || "wan-2.6",
        prompt:          promptForSubmit,
        mentions:        mentionsList,
        ratio:           data.vidRatio       || "16:9",
        resolution:      data.vidQuality     || "1080P",
        duration:        durationSec,
        audio:           data.vidAudio === "开启",
        count:           data.count          || 1,
        node_id:         id,
        generation_mode: refMode === "freeref" ? "freeref" : "keyframe",
        client_id:       wsManager.getClientId(),
      }

      if (refMode === "freeref") {
        payload.reference_images = freeRefs.map((r) => r.imageUrl).filter(Boolean)
      } else {
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
  const showUploadRow =
    (isIdle && !isRefSource && selected)
    || isRefSource
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

  const closeVideoMenu = useCallback(() => setVideoMenu(null), [])

  useEffect(() => {
    if (!videoMenu) return undefined
    const onDocDown = (e) => {
      if (videoMenuPortalRef.current?.contains(e.target)) return
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
          <button type="button" className="gn2-upload-btn nodrag" onClick={() => uploadRef.current?.click()}>
            <UploadIcon /> {t("canvas.common.upload")}
          </button>
          <span className="gn2-upload-divider" aria-hidden="true" />
          <button type="button" className="gn2-upload-btn nodrag" onClick={openAssetLibrary}>
            <AssetLibraryIcon /> {t("canvas.image.fromLibrary")}
          </button>
        </div>
        <input ref={uploadRef} type="file" accept="image/*" hidden onChange={handleTopUpload} />
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
          onMouseEnter={() => setLeftVisible(true)} onMouseLeave={() => setLeftVisible(false)} />
        <Handle type="source" position={Position.Right} id="src-right" className="gn2-edge-handle gn2-edge-handle--right"
          onMouseEnter={() => setRightVisible(true)} onMouseLeave={() => setRightVisible(false)} />

        {/* Left zone: hover container + sliding visual button */}
        <div
          className={`gn2-plus-left-zone nodrag${leftVisible ? ' gn2-plus-zone--visible' : ''}`}
          onMouseEnter={() => setLeftVisible(true)}
          onMouseLeave={() => setLeftVisible(false)}
          onClick={(e) => { e.stopPropagation(); canvasActions?.openPickerAt(e.clientX - 20, e.clientY, { toLeft: true, targetNodeId: id }) }}
        >
          <div className="gn2-plus-btn-visual">+</div>
        </div>

        {/* Right zone: hover container + sliding visual button */}
        <div
          className={`gn2-plus-right-zone nodrag${rightVisible ? ' gn2-plus-zone--visible' : ''}`}
          onMouseEnter={() => setRightVisible(true)}
          onMouseLeave={() => setRightVisible(false)}
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
                <span className="gn2-pct">{progress}%</span>
                <span className="gn2-gen-label">{t("canvas.gen.generating")}</span>
                <GenerationStopButton onStop={handleStopGeneration} />
              </div>
            </div>
          )}
          {isDone && playbackUrl && (
            <div className="gn2-video-wrap">
              <video
                key={`${mediaRevision}:${playbackUrl}`}
                ref={videoRef}
                className="gn2-result-video"
                src={playbackUrl}
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
            className="cell-menu-portal gn2-dots-menu nodrag nopan"
            style={{
              position: "fixed",
              top: videoMenu.menuPos.y,
              left: videoMenu.menuPos.x,
              zIndex: 9999,
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
              <span>🔍</span>{t("canvas.image.zoom")}
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
          document.body
        )}
    </div>
  )
}
