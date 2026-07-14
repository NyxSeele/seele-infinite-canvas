import { useState, useCallback, useEffect, useRef, useMemo } from "react"
import { createPortal } from "react-dom"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_NODE_DOTS_MENU, Z_REF_HOVER } from "../../utils/zIndexLayers"
import { useModelStore, useCanvasStore } from "../../stores"
import { useAssetStore } from "../../stores/assetStore"
import { pushGenHistory } from "../../utils/canvas/genHistory"
import { Handle, Position, useStore, useReactFlow } from "reactflow"
import api, { API_BASE } from "../../services/api"
import { resolveReferenceUrlForApi } from "../../services/uploadImage"
import { useCanvasActions, useReferenceSelect } from "./CanvasActionsContext"
import EditableNodeLabel from "./EditableNodeLabel"
import NodeLastEditedMeta from "./NodeLastEditedMeta"
import { getCanvasTeamId, teamIdPayload } from "../../utils/teamContext"
import MediaFullscreenViewer from "./MediaFullscreenViewer"
import GenerationStopButton from "./GenerationStopButton"
import GenerationBrandLoader from "./GenerationBrandLoader"
import TaskRatingBar from "./TaskRatingBar"
import { cancelCanvasTask } from "../../services/cancelTask"
import {
  buildClearGenerationTaskPatch,
  buildRefItem,
  getConnectedVideoNodesFromEdges,
  buildIncomingEdgeDataPatch,
  getReferenceImagesList,
  getResolvedReferenceImagesList,
} from "./videoReferenceHelpers"
import { mergeMentionRefsIntoReferenceImages } from "./promptMentions"
import useModelCapabilities from "../../hooks/useModelCapabilities"
import { createStaleProgressGuard } from "./taskPollTimeout"
import { MENU_SUBMENU_CLOSE_MS } from "../../utils/menuFlyoutTiming"
import { parseGenerationError, isNetworkError } from "./taskNetworkError"
import { getRetryPolicy } from "../../utils/canvas/generationRetryPolicy"
import { markSuppressPaneMenu } from "../../utils/canvas/suppressPaneMenu"
import { findScriptTableNode, resolveImageQualityPresetId } from "../../utils/canvas/scriptTableNode"
import { BEAT_CARD_NODE_TYPE } from "../../utils/canvas/scriptBeatCard"
import { collectConnectedCharacterFaceUrl } from "../../utils/canvas/entityRefs"
import { uploadImageFileWithMeta, buildUploadedImageNodePatch } from "../../services/uploadImage"
import { ensureMediaUrl, stripMediaTicket } from "../../utils/mediaTicket"
import { useLocale } from "../../utils/locale"
import { useCanvasNodeWheel } from "./canvasScrollHelpers"
import {
  cssAspectRatio,
  sizeForAspectRatio,
  normalizeClarityLabel,
  cardDisplayRatio,
  ratioStringFromDimensions,
} from "../../utils/canvas/aspectRatioLayout"
import { isRealProjectId } from "../../utils/canvas/projectId"
import "./CanvasShared.css"
import "./GenerationCardNode.css"

const POLL_INTERVAL_MS = 2000
const PROGRESS_HINT_INTERVAL_MS = 5000

function useProgressHints() {
  const { t } = useLocale()
  return useMemo(
    () => [
      t("canvas.gen.queued"),
      t("canvas.gen.inProgress"),
      t("canvas.gen.rendering"),
      t("canvas.gen.almostDone"),
    ],
    [t]
  )
}

function isInlineImageUrl(url) {
  return typeof url === "string" && (url.startsWith("data:") || url.startsWith("blob:"))
}

/** 任务结果 URL：data:/blob:/http 原样保留，仅相对路径拼 API_BASE */
function resolveTaskResultUrl(raw) {
  if (!raw || typeof raw !== "string") return ""
  const s = raw.trim()
  if (
    s.startsWith("http://")
    || s.startsWith("https://")
    || s.startsWith("data:")
    || s.startsWith("blob:")
  ) {
    return s
  }
  return `${API_BASE}${s.startsWith("/") ? s : `/${s}`}`
}

/** 将 data:/blob: 参考图上传为 http URL，仅放入 POST body，避免超大 header/body 触发 431 */
function mediaUrlForDisplay(url) {
  if (!url) return url
  if (isInlineImageUrl(url)) return url
  return ensureMediaUrl(url)
}

async function resolvePayloadReferenceUrls(payload) {
  const next = { ...payload }
  let single = next.reference_image
  const multi = Array.isArray(next.reference_images) ? [...next.reference_images] : []

  if (isInlineImageUrl(single)) {
    single = await resolveReferenceUrlForApi(single)
    next.reference_image = single
  }

  if (multi.length > 0) {
    const resolved = []
    for (const url of multi) {
      if (!url) continue
      if (isInlineImageUrl(url)) {
        resolved.push(await resolveReferenceUrlForApi(url))
      } else {
        resolved.push(url)
      }
    }
    next.reference_images = resolved.filter(Boolean)
    if (!next.reference_image && next.reference_images[0]) {
      next.reference_image = next.reference_images[0]
    }
  }

  return next
}

/** 宫格单格状态：waiting=排队等待 ComfyUI，generating=本格生成中，done=已完成 */
const SLOT_PHASE = {
  WAITING: "waiting",
  GENERATING: "generating",
  DONE: "done",
  FAILED: "failed",
}

function deriveSlotPhase(task) {
  if (!task) return SLOT_PHASE.WAITING
  if (task.status === "completed") return SLOT_PHASE.DONE
  if (task.status === "failed") return SLOT_PHASE.FAILED
  if (task.status === "running") return SLOT_PHASE.GENERATING
  const pct = Number(task.progress) || 0
  if (pct > 0) return SLOT_PHASE.GENERATING
  return SLOT_PHASE.WAITING
}

function logImageGen(step, detail) {
  if (detail !== undefined) {
    console.log(`[image-gen] ${step}`, detail)
  } else {
    console.log(`[image-gen] ${step}`)
  }
}

const CELL = 280
const GAP = 8
const CELL_MENU_WIDTH = 160
const CELL_MENU_EST_HEIGHT = 200
const CELL_SUBMENU_WIDTH = 140
const REF_MENU_ITEM_OFFSET_Y = 36

function computeGridLayout(slotCount, ratioStr = "1:1") {
  const { width: cellW, height: cellH } = sizeForAspectRatio(ratioStr, CELL)
  if (slotCount <= 1) {
    return {
      cols: 1,
      rows: 1,
      gridWidth: cellW,
      gridHeight: cellH,
      cellW,
      cellH,
    }
  }
  // 3 图：首格 span-full 占满第一行，下方两格 → 2×2 网格高度
  if (slotCount === 3) {
    const cols = 2
    const rows = 2
    const gridWidth = cols * cellW + (cols - 1) * GAP
    const gridHeight = rows * cellH + (rows - 1) * GAP
    return { cols, rows, gridWidth, gridHeight, cellW, cellH }
  }
  const cols = slotCount <= 2 ? 2 : 3
  const rows = Math.ceil(slotCount / cols)
  const gridWidth = cols * cellW + (cols - 1) * GAP
  const gridHeight = rows * cellH + (rows - 1) * GAP
  return { cols, rows, gridWidth, gridHeight, cellW, cellH }
}

const ImagePlaceholderIcon = () => (
  <svg width="44" height="44" viewBox="0 0 44 44" fill="none">
    <rect x="4" y="7" width="36" height="30" rx="4" stroke="currentColor" strokeWidth="1.6"/>
    <circle cx="15" cy="17" r="3.5" stroke="currentColor" strokeWidth="1.6"/>
    <path d="M4 31l11-10 7 7 5-5 13 9" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>
  </svg>
)
const NodeLabelIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <rect x="1" y="1.5" width="10" height="9" rx="1.5"
      stroke="currentColor" strokeWidth="1.2"/>
    <circle cx="4" cy="5.5" r="1.2" fill="currentColor" opacity=".5"/>
    <path d="M1.5 9l2.5-2.5 2 2 1.5-1.5 3 2.5"
      stroke="currentColor" strokeWidth="1" strokeLinejoin="round"/>
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

function normalizeInitialImageStatus(raw) {
  if (raw === "pending" || raw === "generating" || raw === "queued") {
    return "failed"
  }
  return raw || "input"
}

export default function GenerationCardNode({ id, data, selected, isConnectable }) {
  const { t } = useLocale()
  const { getNodes, getEdges, setNodes } = useReactFlow()
  const progressHints = useProgressHints()
  const [status, setStatus] = useState(() => normalizeInitialImageStatus(data.status))
  const [prompt, setPrompt] = useState(data.prompt || "")
  const [sizeIndex, setSizeIndex] = useState(data.sizeIndex || 0)
  const [taskId, setTaskId] = useState(data.taskId || null)
  const [taskIds, setTaskIds] = useState(data.taskIds || (data.taskId ? [data.taskId] : []))
  const initResults = () => {
    if (Array.isArray(data.results) && data.results.length) return data.results
    if (data.imageUrl) return [data.imageUrl]
    return []
  }
  const [results, setResults] = useState(initResults)
  const [expectedCount, setExpectedCount] = useState(data.expectedCount || data.count || 1)
  const [errorMessage, setErrorMessage] = useState(null)
  const [toast, setToast] = useState(null)
  const [sending, setSending] = useState(false)
  const toastTimerRef = useRef(null)
  const pollTimersRef = useRef(null)
  const staleGuardRef = useRef(null)
  const lastSubmitParamsRef = useRef(null)
  const [progressHint, setProgressHint] = useState(() => progressHints[0])
  /** 单图模式沿用；宫格模式用 slotProgress / slotPhases */
  const [pollProgress, setPollProgress] = useState(0)
  const [slotPhases, setSlotPhases] = useState([])
  const [slotProgress, setSlotProgress] = useState([])
  const imageModels = useModelStore((s) => s.imageModels)
  const [modelId, setModelId] = useState(data.modelId || "")
  const generateRef = useRef(null)
  const effectiveModelId = data.modelId || modelId
  const { capabilities: modelCapabilities } = useModelCapabilities(effectiveModelId)

  useEffect(() => {
    if (imageModels.length > 0 && !modelId) {
      setModelId(imageModels[0].id || imageModels[0].display_name || "")
    }
  }, [imageModels])

  useEffect(() => {
    if (!modelCapabilities || !data.onUpdate) return
    data.onUpdate(id, { capabilities: modelCapabilities })
  }, [modelCapabilities, id, data.onUpdate])

  // 换模型后裁剪不兼容的比例 / 清晰度
  useEffect(() => {
    if (!modelCapabilities || !data.onUpdate) return
    const patch = {}
    const ar = modelCapabilities.aspect_ratios
    const currentRatio = data.imgRatio || "1:1"
    if (ar?.length && !ar.includes(currentRatio)) {
      patch.imgRatio = ar[0]
    }
    const qualities = (modelCapabilities.resolutions?.length
      ? modelCapabilities.resolutions
      : ["480P", "720P", "1080P"]
    ).map((q) => normalizeClarityLabel(q))
    const rawClarity = data.imgResolution || data.imgQuality || "720P"
    const clarity = normalizeClarityLabel(rawClarity, qualities[0] || "720P")
    if (qualities.length && !qualities.includes(clarity)) {
      patch.imgResolution = qualities[0]
      patch.imgQuality = qualities[0]
    } else if (clarity !== rawClarity) {
      patch.imgResolution = clarity
      patch.imgQuality = clarity
    }
    if (Object.keys(patch).length) data.onUpdate(id, patch)
  }, [
    modelCapabilities,
    id,
    data.onUpdate,
    data.imgRatio,
    data.imgResolution,
    data.imgQuality,
  ])

  useEffect(() => {
    if (data.prompt !== undefined && data.prompt !== prompt) {
      setPrompt(data.prompt)
    }
  }, [data.prompt])

  const stopPolling = useCallback(() => {
    staleGuardRef.current?.stop()
    staleGuardRef.current = null
    const timers = pollTimersRef.current
    if (!timers) return
    timers.intervals?.forEach((iv) => clearInterval(iv))
    pollTimersRef.current = null
  }, [])

  // 仅当画布持久化 status 为失败时同步到本地；勿用 data.error 触发（重试时 error 可能尚未清空）
  useEffect(() => {
    if (sending || status === "pending" || status === "generating") return
    if (
      data.status === "pending" ||
      data.status === "generating" ||
      data.status === "queued" ||
      data.status === "completed"
    ) {
      return
    }
    const failed = data.status === "failed" || data.status === "error"
    if (!failed) return
    stopPolling()
    setStatus("failed")
    setErrorMessage(data.error || t("canvas.gen.failed"))
    setSending(false)
  }, [data.status, data.error, status, sending, stopPolling, t])

  const patchNodeData = useCallback((patch, reason = "update") => {
    logImageGen("onUpdate → setNodes", { nodeId: id, reason, patch })
    data.onUpdate?.(id, patch)
  }, [id, data])

  const startMultiPolling = useCallback((activeTaskIds, totalCount) => {
    stopPolling()
    logImageGen("轮询启动", {
      taskIds: activeTaskIds,
      totalCount,
      intervalMs: POLL_INTERVAL_MS,
    })

    const slots = Array(totalCount).fill(null)
    const slotsRef = { current: [...slots] }
    const phasesRef = { current: Array(totalCount).fill(SLOT_PHASE.WAITING) }
    const progressRef = { current: Array(totalCount).fill(0) }
    setSlotPhases([...phasesRef.current])
    setSlotProgress([...progressRef.current])
    let finished = 0
    let lastFailureMsg = null
    const doneSlots = new Set()

    const syncSlotUi = () => {
      setSlotPhases([...phasesRef.current])
      setSlotProgress([...progressRef.current])
    }

    const finalizeBatch = () => {
      const snapshot = [...slotsRef.current]
      const filled = snapshot.filter(Boolean)
      const isSingleOutput = snapshot.length <= 1
      const completedAt = Date.now()
      if (filled.length === 0) {
        const msg = lastFailureMsg || t("canvas.gen.failed")
        setStatus("failed")
        setErrorMessage(msg)
        setSending(false)
        phasesRef.current = snapshot.map(() => SLOT_PHASE.FAILED)
        progressRef.current = snapshot.map(() => 0)
        syncSlotUi()
        patchNodeData(
          { status: "failed", error: msg, taskIds: activeTaskIds, results: snapshot },
          "finalizeBatch-allFailed"
        )
        return
      }
      const patch = {
        status: "completed",
        results: snapshot,
        imageUrl: isSingleOutput ? (filled[0] || null) : null,
        resultUrl: null,
        taskIds: activeTaskIds,
        taskId: activeTaskIds[0],
        prompt,
        completedAt,
        cardDisplayRatio: data.imgRatio || "1:1",
        error: filled.length < snapshot.length ? (lastFailureMsg || null) : null,
      }
      logImageGen("回填完成 finalizeBatch", {
        snapshot,
        patch,
        filledCount: filled.length,
      })
      setResults(snapshot)
      setStatus("completed")
      setSending(false)
      setPollProgress(100)
      if (lastFailureMsg && filled.length < snapshot.length) {
        setErrorMessage(lastFailureMsg)
      }
      phasesRef.current = snapshot.map((url) =>
        url ? SLOT_PHASE.DONE : SLOT_PHASE.FAILED
      )
      progressRef.current = snapshot.map((url) => (url ? 100 : 0))
      syncSlotUi()
      patchNodeData(patch, "finalizeBatch")
      const firstUrl = filled[0]
      if (firstUrl) {
        const cardLabel =
          (data.label && String(data.label).trim()) || "Image"
        const multi = filled.length > 1
        const { canvasId, projectName } = useCanvasStore.getState()
        pushGenHistory({
          title: multi ? `${cardLabel} #1` : cardLabel,
          prompt: prompt || data.prompt || "",
          kind: "image",
          mediaUrl: firstUrl,
          nodeId: id,
          imageIndex: 0,
          ts: completedAt,
          canvasId,
          canvasName: projectName,
          teamId: getCanvasTeamId(),
        })
      }
    }

    const markSlotDone = () => {
      finished += 1
      if (finished === activeTaskIds.length) {
        stopPolling()
        finalizeBatch()
      }
    }

    const terminalRef = { current: false }
    const staleGuard = createStaleProgressGuard(() => {
      if (terminalRef.current) return
      // 超时：未完成的格子记为失败，已完成的保留
      activeTaskIds.forEach((_, index) => {
        if (doneSlots.has(index)) return
        doneSlots.add(index)
        phasesRef.current[index] = SLOT_PHASE.FAILED
        lastFailureMsg = t("canvas.gen.timeout")
        markSlotDone()
      })
      syncSlotUi()
    })
    staleGuard.start()
    staleGuardRef.current = staleGuard
    const intervals = []
    activeTaskIds.forEach((activeTaskId, index) => {
      let timerId = null
      const pollOnce = async () => {
        if (doneSlots.has(index)) return
        const pollUrl = `${API_BASE}/api/tasks/${activeTaskId}`
        try {
          logImageGen(`轮询 #${index} 请求`, { url: pollUrl, taskId: activeTaskId })
          const res = await api.get(`/api/tasks/${activeTaskId}`)
          const task = res.data
          staleGuardRef.current?.touch?.()
          logImageGen(`轮询 #${index} 响应`, {
            httpStatus: res.status,
            taskId: activeTaskId,
            status: task.status,
            progress: task.progress,
            hasResult: Boolean(task.result),
            result: task.result,
            error: task.error,
          })
          const phase = deriveSlotPhase(task)
          phasesRef.current[index] = phase
          if (phase === SLOT_PHASE.GENERATING && typeof task.progress === "number") {
            const prev = progressRef.current[index] || 0
            const next = Math.max(prev, Math.min(100, Math.max(0, Number(task.progress) || 0)))
            progressRef.current[index] = next
            staleGuardRef.current?.bump(next)
          } else if (phase === SLOT_PHASE.WAITING) {
            progressRef.current[index] = 0
          }
          if (totalCount <= 1 && typeof task.progress === "number") {
            setPollProgress((prev) => Math.max(prev, Math.min(100, Math.max(0, Number(task.progress) || 0))))
          }
          syncSlotUi()

          if (task.status === "completed") {
            if (timerId) clearInterval(timerId)
            doneSlots.add(index)
            const raw = task.result || ""
            const imageUrl = resolveTaskResultUrl(raw)
            slotsRef.current[index] = imageUrl
            phasesRef.current[index] = SLOT_PHASE.DONE
            progressRef.current[index] = 100
            logImageGen(`轮询 #${index} 单格完成`, { imageUrl })
            setResults([...slotsRef.current])
            syncSlotUi()
            if (doneSlots.size === activeTaskIds.length) {
              terminalRef.current = true
              staleGuardRef.current?.stop()
            }
            markSlotDone()
          } else if (task.status === "failed") {
            if (timerId) clearInterval(timerId)
            doneSlots.add(index)
            phasesRef.current[index] = SLOT_PHASE.FAILED
            lastFailureMsg = parseGenerationError(null, task)
            syncSlotUi()
            if (doneSlots.size === activeTaskIds.length) {
              terminalRef.current = true
              staleGuardRef.current?.stop()
            }
            markSlotDone()
          }
        } catch (err) {
          console.error("[image-gen] poll error:", err)
          logImageGen(`轮询 #${index} 异常`, {
            message: err.message,
            status: err.response?.status,
            detail: err.response?.data,
          })
          if (isNetworkError(err)) return
          if (timerId) clearInterval(timerId)
          doneSlots.add(index)
          phasesRef.current[index] = SLOT_PHASE.FAILED
          lastFailureMsg = parseGenerationError(err, null)
          syncSlotUi()
          markSlotDone()
        }
      }
      pollOnce()
      timerId = setInterval(pollOnce, POLL_INTERVAL_MS)
      intervals.push(timerId)
    })

    pollTimersRef.current = { intervals }
  }, [stopPolling, id, patchNodeData, prompt, t])

  useEffect(() => () => stopPolling(), [stopPolling])

  useEffect(() => {
    const st = data.status

    // 本地或画布已 completed：切勿再判「中断」（否则会覆盖 finalizeSuccess）
    if (status === "completed" || st === "completed") {
      if (status === "completed" && st !== "completed") {
        const filled = results.filter(Boolean)
        patchNodeData(
          buildClearGenerationTaskPatch({
            status: "completed",
            error: null,
            results,
            imageUrl: filled.length === 1 ? filled[0] : data.imageUrl,
            taskIds: taskIds.length ? taskIds : data.taskIds,
            taskId: taskId || data.taskId,
          }),
          "sync-completed-persist"
        )
      }
      return
    }

    const persistedActive = st === "pending" || st === "generating" || st === "queued"
    const locallyActive =
      sending ||
      pollTimersRef.current ||
      status === "pending" ||
      status === "generating" ||
      status === "completed"

    // 仅页面恢复：持久化仍是进行中，但本地未在提交/轮询
    if (persistedActive && !locallyActive) {
      const localTerminal = status === "failed" || status === "error"
      if (localTerminal) {
        // 本地已失败/超时，纠正画布上仍为 pending 的僵尸状态，避免挡住重试
        patchNodeData(
          buildClearGenerationTaskPatch({
            status: "failed",
            error: errorMessage || data.error || t("canvas.gen.interrupted"),
          }),
          "reconcile-zombie-persist"
        )
        return
      }
      if (status !== "failed") {
        stopPolling()
        setStatus("failed")
        setErrorMessage(data.error || t("canvas.gen.interrupted"))
        setSending(false)
        patchNodeData(
          buildClearGenerationTaskPatch({
            status: "failed",
            error: data.error || t("canvas.gen.interrupted"),
          }),
          "stale-status-guard"
        )
      }
      return
    }

    const ids = data.taskIds || (data.taskId ? [data.taskId] : [])
    const stRecoverable = st === "pending" || st === "generating" || st === "queued"
    if (ids.length && stRecoverable && !pollTimersRef.current && !sending) {
      setTaskIds(ids)
      setTaskId(ids[0])
      setStatus("pending")
      setSending(true)
      const total = data.expectedCount || ids.length
      setExpectedCount(total)
      if (!data.results?.length) setResults(Array(total).fill(null))
      setSlotPhases(Array(total).fill(SLOT_PHASE.WAITING))
      setSlotProgress(Array(total).fill(0))
      startMultiPolling(ids, total)
    }
  }, [
    data.taskIds,
    data.taskId,
    data.status,
    data.expectedCount,
    data.results,
    data.error,
    sending,
    status,
    startMultiPolling,
    stopPolling,
    patchNodeData,
    errorMessage,
    results,
    taskIds,
    taskId,
    data.imageUrl,
    data.taskIds,
    data.taskId,
    t,
  ])

  const clearNodeTaskState = useCallback(
    (nextStatus = "pending") => {
      setTaskId(null)
      setTaskIds([])
      setErrorMessage(null)
      setPollProgress(0)
      setStatus(
        nextStatus === "failed"
          ? "failed"
          : nextStatus === "completed"
            ? "completed"
            : nextStatus === "input"
              ? "input"
              : "pending"
      )
      setResults([])
      setSlotPhases([])
      setSlotProgress([])
      patchNodeData(
        buildClearGenerationTaskPatch({
          status: nextStatus,
          error: null,
          results: [],
          imageUrl: null,
        }),
        "clear-task-state"
      )
    },
    [patchNodeData]
  )

  const showToast = useCallback((msg) => {
    clearTimeout(toastTimerRef.current)
    setToast(msg)
    toastTimerRef.current = setTimeout(() => setToast(null), 2000)
  }, [])

  const getNodeRef = useRef(null)

  const buildSubmitPayload = useCallback(() => {
    const mentionsList = Array.isArray(data.mentions) ? data.mentions : []
    const merged = mergeMentionRefsIntoReferenceImages(
      getReferenceImagesList(data),
      mentionsList,
      getNodeRef.current
    )
    const refs = getResolvedReferenceImagesList(
      { referenceImages: merged },
      getNodeRef.current
    )
    const refUrls = refs
      .map((r) => r.imageUrl)
      .filter((url) => url && !isInlineImageUrl(url))
    const characterFaceUrl = collectConnectedCharacterFaceUrl(getNodes(), getEdges(), id)
    const pulidFaceUrl = characterFaceUrl && !isInlineImageUrl(characterFaceUrl) ? characterFaceUrl : null
    const generationPrompt = (data.generationPrompt || "").trim()
    const displayPrompt = (data.displayPrompt || prompt || data.prompt || "").trim()
    const rawRef = pulidFaceUrl || refUrls[0] || data.referenceImageUrl || null
    const selectedModel = pulidFaceUrl ? "flux-pulid" : (data.modelId || modelId)
    const hasFaceRef = Boolean(pulidFaceUrl || (selectedModel === "flux-pulid" && rawRef))
    const payload = {
      model: selectedModel,
      prompt: generationPrompt || displayPrompt,
      display_prompt: displayPrompt || undefined,
      mentions: mentionsList,
      reference_image: rawRef && !isInlineImageUrl(rawRef) ? rawRef : null,
      reference_images: pulidFaceUrl
        ? [pulidFaceUrl]
        : refUrls.length
          ? refUrls
          : undefined,
      _inlineReferenceUrls: refs
        .map((r) => r.imageUrl)
        .filter((url) => url && isInlineImageUrl(url)),
      quality: (() => {
        const raw = data.imgResolution || data.imgQuality || "720P"
        const s = String(raw).trim().toUpperCase().replace("×", "x")
        if (s === "480" || s === "720" || s === "1080") return `${s}P`
        if (s === "480P" || s === "720P" || s === "1080P") return s
        if (s === "2K") return "720P"
        if (s === "3K") return "1080P"
        // 旧像素标签交给后端按 ratio+720 解析
        if (/^\d+x\d+$/i.test(s)) return "720P"
        return "720P"
      })(),
      ratio: data.imgRatio || "1:1",
      count: data.count || 1,
      node_id: id,
      use_reactor: hasFaceRef || Boolean(data.use_reactor),
    }
    const denoise = data.img2imgDenoise
    if (denoise != null && Number.isFinite(Number(denoise))) {
      payload.denoise = Number(denoise)
    }
    const negative = (data.negativePrompt || "").trim()
    if (negative) payload.negative_prompt = negative
    const scriptTable = (() => {
      const ref = data.scriptTableRef
      if (ref?.nodeId) {
        return getNodes().find((n) => n.id === ref.nodeId) || null
      }
      return findScriptTableNode(getNodes())
    })()
    const qualityPresetId = resolveImageQualityPresetId(data, scriptTable?.data || null)
    if (qualityPresetId && qualityPresetId !== "auto") {
      payload.quality_preset_id = qualityPresetId
    }
    if (data.traceId) payload.trace_id = data.traceId
    const { canvasId } = useCanvasStore.getState()
    if (isRealProjectId(canvasId)) payload.project_id = canvasId
    return payload
  }, [data, modelId, prompt, id, getNodes, getEdges])

  const submitImageTask = useCallback(async (payload) => {
    stopPolling()
    clearNodeTaskState("pending")
    setSending(true)
    setStatus("pending")
    setPollProgress(0)
    setErrorMessage(null)
    const batchCount = Math.max(1, Math.min(payload.count || 1, 4))
    setExpectedCount(batchCount)
    setResults(Array(batchCount).fill(null))
    setSlotPhases(Array(batchCount).fill(SLOT_PHASE.WAITING))
    setSlotProgress(Array(batchCount).fill(0))
    setProgressHint(progressHints[0])
    lastSubmitParamsRef.current = payload

    const { _inlineReferenceUrls, ...payloadForApi } = payload
    let requestBody = { ...payloadForApi, count: batchCount }
    if (
      _inlineReferenceUrls?.length ||
      isInlineImageUrl(requestBody.reference_image)
    ) {
      requestBody = await resolvePayloadReferenceUrls(requestBody)
    }
    const submitUrl = `${API_BASE}/api/tasks/image`
    logImageGen("POST 即将发送", { url: submitUrl, payload: requestBody })

    try {
      const res = await api.post(
        "/api/tasks/image",
        { ...requestBody, ...teamIdPayload() },
        { timeout: 30000 },
      )
      logImageGen("POST 收到响应", {
        httpStatus: res.status,
        statusText: res.statusText,
        body: res.data,
      })
      const ids = res.data?.task_ids || (res.data?.task_id ? [res.data.task_id] : [])
      if (ids.length > 0) {
        logImageGen("任务已创建，启动轮询", { taskIds: ids, batchCount })
        setTaskIds(ids)
        setTaskId(ids[0])
        patchNodeData({
          status: "pending",
          taskIds: ids,
          taskId: ids[0],
          generationPrompt: payload.prompt,
          sizeIndex,
          results: Array(batchCount).fill(null),
          expectedCount: batchCount,
          imageUrl: null,
          error: null,
        }, "submitImageTask")
        startMultiPolling(ids, batchCount)
      } else {
        throw new Error(t("canvas.gen.noTaskId"))
      }
    } catch (error) {
      logImageGen("POST 失败", {
        message: error.message,
        status: error.response?.status,
        detail: error.response?.data,
      })
      const msg = parseGenerationError(error, null)
      setStatus("failed")
      setErrorMessage(msg)
      showToast(msg)
      setSending(false)
      patchNodeData({ status: "failed", error: msg }, "submitImageTask-catch")
    }
  }, [stopPolling, clearNodeTaskState, id, sizeIndex, startMultiPolling, showToast, patchNodeData, t, progressHints])

  const handleGenerate = useCallback(async () => {
    logImageGen("handleGenerate 点击")
    if (sending) {
      logImageGen("handleGenerate 跳过：sending=true")
      return
    }
    const payload = buildSubmitPayload()
    if (!payload.prompt) {
      logImageGen("handleGenerate 跳过：提示词为空")
      setErrorMessage(t("canvas.gen.noPrompt"))
      return
    }

    logImageGen("handleGenerate → submitImageTask", payload)
    await submitImageTask(payload)
  }, [
    sending,
    buildSubmitPayload,
    submitImageTask,
    data.displayPrompt,
    data.prompt,
    id,
    prompt,
    patchNodeData,
    t,
  ])

  const handleRetry = useCallback(async () => {
    if (sending) return
    const errText = errorMessage || data.error || ""
    const policy = getRetryPolicy(errText)
    if (!policy.retryable) return
    const payload = lastSubmitParamsRef.current || buildSubmitPayload()
    if (!payload.prompt?.trim()) {
      setErrorMessage(t("canvas.gen.noPrompt"))
      return
    }
    stopPolling()
    clearNodeTaskState("pending")
    await submitImageTask(payload)
  }, [sending, buildSubmitPayload, submitImageTask, clearNodeTaskState, stopPolling, errorMessage, data.error])

  const handleStopGeneration = useCallback(async () => {
    stopPolling()
    const ids = [
      ...(taskIds.length ? taskIds : []),
      ...(data.taskIds?.length ? data.taskIds : []),
      ...(taskId ? [taskId] : []),
      ...(data.taskId ? [data.taskId] : []),
    ]
    const unique = [...new Set(ids.filter(Boolean))]
    for (const tid of unique) {
      try {
        await cancelCanvasTask(tid)
      } catch (err) {
        console.error("[image-gen] cancel failed:", tid, err)
      }
    }
    setSending(false)
    setStatus("failed")
    setErrorMessage(t("canvas.gen.stopped"))
    patchNodeData(
      buildClearGenerationTaskPatch({
        status: "failed",
        error: t("canvas.gen.stopped"),
      }),
      "user-cancel"
    )
  }, [stopPolling, taskIds, taskId, data.taskIds, data.taskId, patchNodeData, t])

  const handleDelete = useCallback(() => {
    if (data.onDelete) data.onDelete(id)
  }, [id, data])

  const handleDownload = useCallback(() => {
    const src = data.uploadedImage || results.find(Boolean)
    if (!src) return
    const link = document.createElement("a")
    link.href = src
    link.download = `image-${Date.now()}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [results, data.uploadedImage])

  const [referenceImage, setReferenceImage] = useState(data.referenceImage || null)
  const uploadRef = useRef(null)
  const canvasActions = useCanvasActions()
  const refSelect = useReferenceSelect()
  const { getNode } = useReactFlow()
  getNodeRef.current = getNode

  const resolvedReferenceImages = useMemo(
    () => getResolvedReferenceImagesList(data, getNode),
    [data, getNode]
  )

  useEffect(() => {
    console.log("[image-gen] referenceImages", {
      raw: getReferenceImagesList(data),
      resolved: resolvedReferenceImages,
    })
  }, [data, resolvedReferenceImages])

  const isRefSelectActive = refSelect?.mode?.active
  const isRefSource = refSelect?.mode?.sourceNodeId === id
  const refPickTarget = refSelect?.mode?.pickTarget
  const useCanvasRefPick = isRefSelectActive && refPickTarget !== "referenceImage"
  const isRefImagePicker = isRefSelectActive && refPickTarget === "referenceImage"
  const hasDisplayImage = !!(data.uploadedImage || results.some(Boolean))

  const connectedVideoNodes = useStore(
    useCallback((s) => {
      return getConnectedVideoNodesFromEdges(s.edges, s.nodeInternals, id).map((v) => {
        const videoNode = s.nodeInternals.get(v.id)
        return {
          ...v,
          referenceMode: videoNode?.data?.referenceMode || "keyframe",
        }
      })
    }, [id])
  )

  const incomingLink = useStore(
    useCallback((s) => {
      const inEdge = s.edges.find((e) => e.target === id)
      if (!inEdge) return null
      const srcNode = s.nodeInternals.get(inEdge.source)
      if (!srcNode) return null
      return { inEdge, srcNode }
    }, [id])
  )

  const lastIncomingKeyRef = useRef(null)

  useEffect(() => {
    if (!incomingLink?.srcNode || !data.onUpdate) return
    const incomingKey = `${incomingLink.inEdge.source}:${incomingLink.inEdge.id}`
    if (lastIncomingKeyRef.current === incomingKey) return

    const patch = buildIncomingEdgeDataPatch(incomingLink.srcNode, "image-gen", data)
    const hasNewRef = Array.isArray(patch.referenceImages) && patch.referenceImages.length > 0
    const hasNewPrompt = patch.prompt && !String(data.prompt || "").trim()
    if (!hasNewRef && !hasNewPrompt) return

    lastIncomingKeyRef.current = incomingKey
    data.onUpdate(id, patch)
  }, [incomingLink, data, id])

  const [cellMenu, setCellMenu] = useState(null)
  const [subMenu, setSubMenu] = useState(null)
  const cellMenuPortalRef = useRef(null)
  const subMenuPortalRef = useRef(null)
  const submenuHoverTimerRef = useRef(null)
  const [lightboxSrc, setLightboxSrc] = useState(null)

  const computeMenuPos = useCallback((btnRect) => {
    let x = btnRect.right - CELL_MENU_WIDTH
    let y = btnRect.bottom + 4
    if (x < 0) x = btnRect.left
    if (y + CELL_MENU_EST_HEIGHT > window.innerHeight) y = btnRect.top - CELL_MENU_EST_HEIGHT
    return { x, y }
  }, [])

  const computeSubMenuPos = useCallback(() => {
    const el = cellMenuPortalRef.current
    if (!el) return null
    const primaryMenu = el.getBoundingClientRect()
    const menuPosX = primaryMenu.left
    const overflowRight =
      menuPosX + CELL_MENU_WIDTH + CELL_SUBMENU_WIDTH > window.innerWidth
    const x = overflowRight
      ? primaryMenu.left - 144
      : primaryMenu.left + CELL_MENU_WIDTH + 4
    return {
      x,
      y: primaryMenu.top + REF_MENU_ITEM_OFFSET_Y,
    }
  }, [])

  const closeCellMenus = useCallback(() => {
    clearTimeout(submenuHoverTimerRef.current)
    setCellMenu(null)
    setSubMenu(null)
  }, [])

  useEffect(() => {
    if (!cellMenu) return undefined
    const close = (e) => {
      if (cellMenuPortalRef.current?.contains(e.target)) return
      if (subMenuPortalRef.current?.contains(e.target)) return
      markSuppressPaneMenu()
      closeCellMenus()
    }
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [cellMenu, closeCellMenus])

  useEffect(() => () => clearTimeout(submenuHoverTimerRef.current), [])

  const nodeLabel = (data.label && String(data.label).trim()) || "Image"

  const handleReupload = useCallback(() => {
    const input = document.createElement("input")
    input.type = "file"
    input.accept = "image/*"
    input.onchange = async (e) => {
      const file = e.target.files?.[0]
      if (!file) return
      try {
        const meta = await uploadImageFileWithMeta(file)
        if (data.onUpdate) data.onUpdate(id, buildUploadedImageNodePatch(meta))
      } catch (err) {
        console.error("重新上传失败", err)
        showToast(err.message || t("common.uploadFail"))
      }
    }
    input.click()
  }, [id, data, showToast, t])

  const submitImageTaskRef = useRef(submitImageTask)
  const buildSubmitPayloadRef = useRef(buildSubmitPayload)
  useEffect(() => { submitImageTaskRef.current = submitImageTask }, [submitImageTask])
  useEffect(() => { buildSubmitPayloadRef.current = buildSubmitPayload }, [buildSubmitPayload])
  useEffect(() => { generateRef.current = handleGenerate }, [handleGenerate])

  useEffect(() => {
    if (!data.pendingTrigger) return
    const batchCount = Math.max(1, Math.min(Number(data.count) || 1, 4))
    setExpectedCount(batchCount)
    setResults(Array(batchCount).fill(null))
    setSlotPhases(Array(batchCount).fill(SLOT_PHASE.WAITING))
    setSlotProgress(Array(batchCount).fill(0))
    data.onUpdate?.(id, { pendingTrigger: null, expectedCount: batchCount })
    setTimeout(() => {
      const payload = buildSubmitPayloadRef.current?.()
      if (!payload?.prompt) {
        console.error("[image-gen] pendingTrigger 跳过：提示词为空", { payload, dataPrompt: data.prompt })
        setStatus("failed")
        setErrorMessage(t("canvas.gen.noPrompt"))
        data.onUpdate?.(id, { status: "failed", error: t("canvas.gen.noPrompt") })
        const ref = data.scriptTableRef
        if (ref?.nodeId && ref?.rowId) {
          const errMsg = t("canvas.gen.noPrompt")
          setNodes((ns) =>
            ns.map((n) => {
              if (ref.beatCardNodeId && n.id === ref.beatCardNodeId && n.type === BEAT_CARD_NODE_TYPE) {
                return {
                  ...n,
                  data: {
                    ...n.data,
                    keyframes: (n.data.keyframes || []).map((kf) =>
                      ref.keyframeId && kf.id === ref.keyframeId
                        ? { ...kf, status: "failed", error: errMsg }
                        : kf
                    ),
                  },
                }
              }
              if (n.id !== ref.nodeId || n.type !== "script-table") return n
              return {
                ...n,
                data: {
                  ...n.data,
                  rows: (n.data.rows || []).map((r) => {
                    if (r.id !== ref.rowId) return r
                    if (ref.keyframeId && !ref.beatCardNodeId) {
                      return {
                        ...r,
                        keyframes: (r.keyframes || []).map((kf) =>
                          kf.id === ref.keyframeId
                            ? { ...kf, status: "failed", error: errMsg }
                            : kf
                        ),
                      }
                    }
                    return {
                      ...r,
                      directStatus: "failed",
                      error: errMsg,
                    }
                  }),
                },
              }
            })
          )
        }
        return
      }
      logImageGen("pendingTrigger → submitImageTask", payload)
      submitImageTaskRef.current?.(payload)
    }, 30)
  }, [data.pendingTrigger, data.count, data.prompt, id, data, setNodes, t])

  const isIdle = status === "input"
  const isPending = status === "pending" || status === "generating"
  const isDone = status === "completed" && results.some(Boolean)
  const ratingTaskId = data.taskId || data.taskIds?.[0] || taskId || null
  const isFailed =
    (status === "failed" || status === "error") && !isPending && !sending
  const retryPolicy = useMemo(
    () => getRetryPolicy(errorMessage || data.error || ""),
    [errorMessage, data.error]
  )
  const gridSlotCount = isPending ? expectedCount : Math.max(results.length, 1)
  const showResultsGrid = !data.uploadedImage && (isPending || isDone) && gridSlotCount > 0
  const showUploadRow =
    isRefSource
    || (isIdle && !data.uploadedImage && !showResultsGrid && selected)

  const setAssetLibraryOpen = useCanvasStore((s) => s.setAssetLibraryOpen)

  const openAssetLibrary = useCallback(() => {
    setAssetLibraryOpen(true)
    useCanvasStore.getState().setGenHistoryOpen(false)
  }, [setAssetLibraryOpen])

  const handleTopUpload = useCallback(async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const meta = await uploadImageFileWithMeta(file)
      if (isIdle && !isRefSource) {
        if (data.onUpdate) {
          data.onUpdate(id, { ...buildUploadedImageNodePatch(meta), referenceImage: null })
        }
      } else {
        setReferenceImage(meta.url)
        if (data.onUpdate) data.onUpdate(id, { referenceImage: meta.url })
        if (isRefSelectActive) refSelect?.exit()
      }
    } catch (err) {
      console.error("上传失败", err)
      showToast(err.message || t("common.uploadFail"))
    }
    e.target.value = ""
  }, [id, data, isIdle, isRefSource, isRefSelectActive, refSelect, showToast, t])

  const handleUploadedImageLoad = useCallback((e) => {
    if (!data.onUpdate || !data.uploadedImage) return
    if (data.results?.some(Boolean) || data.imageUrl) return
    const img = e.currentTarget
    const w = img.naturalWidth
    const h = img.naturalHeight
    if (!w || !h) return
    const ratio = ratioStringFromDimensions(w, h)
    if (ratio === data.uploadAspectRatio && ratio === data.cardDisplayRatio) return
    const size = sizeForAspectRatio(ratio)
    data.onUpdate(id, {
      uploadAspectRatio: ratio,
      cardDisplayRatio: ratio,
      cardWidth: size.width,
      cardHeight: size.height,
    })
  }, [id, data])

  const displayRatio = cardDisplayRatio(data, "image")

  const gridLayout = useMemo(
    () => computeGridLayout(gridSlotCount, displayRatio),
    [gridSlotCount, displayRatio]
  )
  const isMultiGrid = showResultsGrid && gridSlotCount > 1
  const previewAspect = cssAspectRatio(displayRatio)
  const isCanvasPickerActive = useCanvasRefPick || isRefImagePicker
  const isRefTarget = isCanvasPickerActive && !isRefSource && hasDisplayImage && !isMultiGrid

  const selectedRef = refSelect?.mode?.selectedRef
  const hoverRef = refSelect?.mode?.hoverRef
  const isPickerSelectable =
    isCanvasPickerActive && !isRefSource && hasDisplayImage
  const shouldDimForRefPick =
    isRefSelectActive && !isRefSource && !isPickerSelectable

  const gridImages = useMemo(() => {
    return Array.from({ length: gridSlotCount }).map((_, index) => {
      const url = results[index] || null
      return {
        nodeId: id,
        imageIndex: index,
        imageId: `${id}_${index}`,
        imageUrl: url,
        label: nodeLabel,
      }
    })
  }, [gridSlotCount, results, id, nodeLabel])

  const pickRefPayload = useCallback(
    (imageIndex, imageUrl) => ({
      nodeId: id,
      imageIndex,
      imageUrl,
      imageId: `${id}_${imageIndex}`,
      label: isMultiGrid ? `${nodeLabel} #${imageIndex + 1}` : nodeLabel,
    }),
    [id, nodeLabel, isMultiGrid]
  )

  const handleRefTargetClick = useCallback((e) => {
    if (!isRefTarget) return
    e.stopPropagation()
    e.preventDefault()
    const imgUrl =
      data.uploadedImage
      || (gridSlotCount === 1 && results[0] ? results[0] : null)
      || data.imageUrl
      || referenceImage
      || null
    if (!imgUrl) return
    const payload = pickRefPayload(0, imgUrl)
    refSelect?.setSelectedRef?.(payload)
    refSelect?.selectReference(payload)
  }, [
    isRefTarget,
    data.uploadedImage,
    data.imageUrl,
    results,
    referenceImage,
    refSelect,
    gridSlotCount,
    pickRefPayload,
  ])

  const handleCellRefPick = useCallback(
    (imageIndex, imageUrl, e) => {
      e.stopPropagation()
      e.preventDefault()
      if (!isCanvasPickerActive || isRefSource || !imageUrl) return
      const payload = pickRefPayload(imageIndex, imageUrl)
      refSelect?.setSelectedRef?.(payload)
      refSelect?.selectReference(payload)
    },
    [isCanvasPickerActive, isRefSource, refSelect, pickRefPayload]
  )

  const handleCellRefHover = useCallback(
    (imageIndex, imageUrl) => {
      if (!isCanvasPickerActive || isRefSource || !imageUrl) return
      refSelect?.setHoverRef?.(pickRefPayload(imageIndex, imageUrl))
    },
    [isCanvasPickerActive, isRefSource, refSelect, pickRefPayload]
  )

  const applyReferenceToVideo = useCallback(
    (targetVideoId, imageIndex, imageUrl, slot) => {
      const refItem = buildRefItem({
        nodeId: id,
        imageIndex,
        imageUrl,
        label: isMultiGrid ? `${nodeLabel} #${imageIndex + 1}` : nodeLabel,
      })
      data.onApplyVideoReference?.(targetVideoId, refItem, slot)
      closeCellMenus()
      const slotLabel =
        slot === "first"
          ? t("canvas.image.slotFirst")
          : slot === "last"
            ? t("canvas.image.slotLast")
            : t("canvas.image.slotFreeref")
      showToast(t("canvas.image.setAs", { label: slotLabel }))
    },
    [id, nodeLabel, isMultiGrid, data, showToast, closeCellMenus, t]
  )

  const openRefSubmenu = useCallback(
    (cellIndex, imageIndex, imageUrl) => {
      if (!imageUrl) return
      if (!connectedVideoNodes.length) {
        showToast(t("canvas.image.setRefNeedVideo"))
        return
      }
      const pos = computeSubMenuPos()
      if (!pos) return
      if (connectedVideoNodes.length === 1) {
        setSubMenu({
          pos,
          step: "mode",
          cellIndex,
          imageIndex,
          imageUrl,
          targetVideoId: connectedVideoNodes[0].id,
        })
      } else {
        setSubMenu({
          pos,
          step: "video",
          cellIndex,
          imageIndex,
          imageUrl,
          targetVideoId: null,
        })
      }
    },
    [connectedVideoNodes, computeSubMenuPos, showToast, t]
  )

  const handleRefMenuItemEnter = useCallback(
    (cellIndex, imageIndex, imageUrl) => {
      clearTimeout(submenuHoverTimerRef.current)
      submenuHoverTimerRef.current = setTimeout(() => {
        submenuHoverTimerRef.current = null
        openRefSubmenu(cellIndex, imageIndex, imageUrl)
      }, 300)
    },
    [openRefSubmenu]
  )

  const handleRefMenuItemLeave = useCallback(() => {
    clearTimeout(submenuHoverTimerRef.current)
    submenuHoverTimerRef.current = setTimeout(() => {
      submenuHoverTimerRef.current = null
      setSubMenu(null)
    }, MENU_SUBMENU_CLOSE_MS)
  }, [])

  const lastCardWidthRef = useRef(null)
  useEffect(() => {
    if (!data.onUpdate) return
    const nextW = showResultsGrid
      ? gridLayout.gridWidth
      : sizeForAspectRatio(displayRatio).width
    const nextH = showResultsGrid
      ? gridLayout.gridHeight
      : sizeForAspectRatio(displayRatio).height
    if (lastCardWidthRef.current === `${nextW}x${nextH}`) return
    lastCardWidthRef.current = `${nextW}x${nextH}`
    data.onUpdate(id, { cardWidth: nextW, cardHeight: nextH })
  }, [showResultsGrid, gridLayout.gridWidth, gridLayout.gridHeight, displayRatio, id, data])

  useEffect(() => {
    if (!isPending) return undefined
    let hintIndex = 0
    setProgressHint(progressHints[0])
    const hintTimer = setInterval(() => {
      hintIndex = (hintIndex + 1) % progressHints.length
      setProgressHint(progressHints[hintIndex])
    }, PROGRESS_HINT_INTERVAL_MS)
    return () => clearInterval(hintTimer)
  }, [isPending, progressHints])

  const rootRef = useRef(null)
  useCanvasNodeWheel(rootRef)
  const [leftVisible, setLeftVisible] = useState(false)
  const [rightVisible, setRightVisible] = useState(false)
  const plusPinned = selected

  const rootWidth = showResultsGrid ? gridLayout.gridWidth : sizeForAspectRatio(displayRatio).width
  const previewSizeStyle = showResultsGrid
    ? {
        width: gridLayout.gridWidth,
        height: gridLayout.gridHeight,
        aspectRatio: "unset",
      }
    : {
        width: "100%",
        aspectRatio: previewAspect,
      }

  const handleCellDownload = useCallback((url) => {
    if (!url) return
    const link = document.createElement("a")
    link.href = url
    link.download = `image-${Date.now()}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [])

  const addAssetFromUrl = useAssetStore((s) => s.addAssetFromUrl)

  const handleSaveToAsset = useCallback(
    async (url) => {
      if (!url) return
      const { canvasId, projectName } = useCanvasStore.getState()
      try {
        await addAssetFromUrl({
          name: t("canvas.image.assetName", {
            time: new Date().toLocaleTimeString("zh", { hour: "2-digit", minute: "2-digit" }),
          }),
          kind: "image",
          imageUrl: stripMediaTicket(url),
          sourceCanvasId: canvasId,
          sourceCanvasName: projectName || t("canvas.image.currentCanvas"),
          sourceNodeId: id,
        })
        showToast(t("canvas.image.favorited"))
      } catch (err) {
        console.error(err)
        showToast(t("canvas.image.favoriteFail"))
      }
    },
    [addAssetFromUrl, id, showToast, t]
  )

  const handleCopyImageLink = useCallback(async (url) => {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      showToast(t("canvas.image.linkCopied"))
    } catch {
      showToast(t("canvas.image.copyFail"))
    }
  }, [showToast, t])

  const nodeZIndex = data.zIndex ?? 0

  return (
    <div
      className={`gn2-wrapper${isRefTarget ? " gn2-wrapper--ref-target" : ""}${isRefSource ? " gn2-wrapper--ref-source" : ""}`}
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

      {/* 标签行 */}
      <div className="gn2-label-row">
        <NodeLabelIcon />
        <EditableNodeLabel nodeId={id} data={data} defaultLabel="Image" className="gn2-label-text" />
        <NodeLastEditedMeta meta={data?.meta} />
      </div>

      {/* 卡片本体 */}
      <div
        ref={rootRef}
        className={`gn2-root${selected ? " gn2-root--selected" : ""}${isRefTarget ? " gn2-root--ref-selectable" : ""}${shouldDimForRefPick ? " gn2-root--ref-dimmed" : ""}${showResultsGrid ? " gn2-root--grid" : ""}`}
        onClick={isRefTarget ? handleRefTargetClick : undefined}
        data-ref-hint={isRefTarget ? t("canvas.image.clickPickRef") : undefined}
        style={{
          width: rootWidth,
          ...(isRefTarget ? { cursor: "pointer" } : null),
        }}
      >
        {/* Target handle — tgt, top:50% relative to gn2-root, same as src zones */}
        <Handle type="target" position={Position.Left} id="tgt" style={{ position: 'absolute', top: '50%', left: -1, width: 1, height: 1, minWidth: 1, minHeight: 1, background: 'transparent', border: 'none', opacity: 0, transform: 'translateY(-50%)', zIndex: 25 }} />
        {/* Source handles: large hit area centered on card edge */}
        <Handle type="source" position={Position.Left}  id="src-left"  className="gn2-edge-handle gn2-edge-handle--left"
          onMouseEnter={() => setLeftVisible(true)} onMouseLeave={() => { if (!plusPinned) setLeftVisible(false) }} />
        <Handle type="source" position={Position.Right} id="src-right" className="gn2-edge-handle gn2-edge-handle--right"
          onMouseEnter={() => setRightVisible(true)} onMouseLeave={() => { if (!plusPinned) setRightVisible(false) }} />

        {/* Left zone: hover container + sliding visual button */}
        <div
          className={`gn2-plus-left-zone${leftVisible || plusPinned ? ' gn2-plus-zone--visible' : ''}`}
          onMouseEnter={() => setLeftVisible(true)}
          onMouseLeave={() => { if (!plusPinned) setLeftVisible(false) }}
        >
          <div
            className="gn2-plus-btn-visual nodrag nopan"
            onClick={(e) => { e.stopPropagation(); canvasActions?.openPickerAt(e.clientX - 20, e.clientY, { toLeft: true, targetNodeId: id }) }}
          >
            +
          </div>
        </div>

        {/* Right zone: hover container + sliding visual button */}
        <div
          className={`gn2-plus-right-zone${rightVisible || plusPinned ? ' gn2-plus-zone--visible' : ''}`}
          onMouseEnter={() => setRightVisible(true)}
          onMouseLeave={() => { if (!plusPinned) setRightVisible(false) }}
        >
          <div
            className="gn2-plus-btn-visual nodrag nopan"
            onClick={(e) => { e.stopPropagation(); canvasActions?.openPickerAt(e.clientX + 20, e.clientY, { fromEdge: true, sourceNodeId: id, sourceNodeType: 'image-gen' }) }}
          >
            +
          </div>
        </div>

        {/* 预览区：容器可传递拖动；媒体元素 pointer-events:none 穿透到节点 */}
        <div className="gn2-preview image-preview-area" style={previewSizeStyle}>
          {/* 上传的图片直接显示 */}
          {data.uploadedImage && !isRefSource && (
            <img
              className="gn2-result-img gn2-result-img--uploaded"
              src={mediaUrlForDisplay(data.uploadedImage)}
              alt="Uploaded"
              draggable={false}
              onDragStart={(e) => e.preventDefault()}
              onLoad={handleUploadedImageLoad}
              style={{ pointerEvents: "none" }}
            />
          )}
          {!data.uploadedImage && isIdle && !isRefSource && (
            <div className="gn2-placeholder"><ImagePlaceholderIcon /></div>
          )}
          {isRefSource && (
            <div className="gn2-ref-source-overlay">
              <span className="gn2-ref-esc-hint"><kbd>ESC</kbd> {t("canvas.image.escExit")}</span>
            </div>
          )}
          {showResultsGrid && (
            <div
              className="results-grid"
              data-count={gridSlotCount}
              style={{
                width: gridLayout.gridWidth,
                height: gridLayout.gridHeight,
                gridTemplateColumns: `repeat(${gridLayout.cols}, ${gridLayout.cellW || CELL}px)`,
                gridTemplateRows: `repeat(${gridLayout.rows}, ${gridLayout.cellH || CELL}px)`,
              }}
            >
              {gridImages.map((img, i) => {
                const url = mediaUrlForDisplay(img.imageUrl)
                const cellPhase = slotPhases[i] || (url ? SLOT_PHASE.DONE : SLOT_PHASE.WAITING)
                const cellProgress = slotProgress[i] ?? 0
                const isCellWaiting = isPending && !url && cellPhase === SLOT_PHASE.WAITING
                const isCellPicker = isCanvasPickerActive && !isRefSource && !!url && isMultiGrid
                const isCellSelected =
                  selectedRef?.nodeId === id && selectedRef?.imageIndex === i
                const isCellHover =
                  !isCellSelected && hoverRef?.nodeId === id && hoverRef?.imageIndex === i
                return (
                  <div
                    key={`result-${img.imageId}`}
                    className={`results-grid-cell${isCellPicker ? " nodrag" : ""}${gridSlotCount === 3 && i === 0 ? " span-full" : ""}${isCellPicker ? " results-grid-cell--picker-active" : ""}${isCellSelected ? " results-grid-cell--ref-highlight" : ""}${isCellHover ? " results-grid-cell--ref-hover" : ""}`}
                  >
                    {url ? (
                      <>
                        <img
                          src={url}
                          alt=""
                          draggable={false}
                          onDragStart={(e) => e.preventDefault()}
                          style={{
                            width: "100%",
                            height: "100%",
                            objectFit: "cover",
                            display: "block",
                            pointerEvents: "none",
                          }}
                        />
                        {isCellPicker && (
                          <div
                            className="picker-overlay nodrag nopan"
                            onPointerDown={(e) => handleCellRefPick(img.imageIndex, img.imageUrl, e)}
                            onMouseEnter={() => handleCellRefHover(img.imageIndex, img.imageUrl)}
                            onMouseLeave={() => refSelect?.setHoverRef?.(null)}
                          >
                            <span>{t("canvas.image.pickThis")}</span>
                          </div>
                        )}
                        <div
                          className="cell-dots-wrap nodrag nopan"
                          onPointerDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            className="cell-dots-btn nodrag nopan"
                            onClick={(e) => {
                              e.stopPropagation()
                              const rect = e.currentTarget.getBoundingClientRect()
                              const menuPos = computeMenuPos(rect)
                              if (cellMenu?.cellIndex === i) {
                                closeCellMenus()
                              } else {
                                setSubMenu(null)
                                setCellMenu({
                                  cellIndex: i,
                                  imageIndex: img.imageIndex,
                                  imageUrl: url,
                                  menuPos,
                                })
                              }
                            }}
                          >
                            ⋯
                          </button>
                        </div>
                      </>
                    ) : isCellWaiting ? (
                      <div className="results-cell-pending results-cell-waiting">
                        <span className="gn2-gen-label gn2-gen-label--waiting">{t("canvas.image.waiting")}</span>
                      </div>
                    ) : (
                      <div className="results-cell-pending">
                        {isPending && (
                          <>
                            <GenerationBrandLoader />
                            <span className="gn2-pct">
                              {isMultiGrid
                                ? (cellProgress > 0 ? `${cellProgress}%` : "0%")
                                : (pollProgress > 0 ? `${pollProgress}%` : "0%")}
                            </span>
                            {i === 0 && (
                              <GenerationStopButton onStop={handleStopGeneration} />
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
          {!data.uploadedImage && isFailed && (
            <div className="gn2-error-area">
              <span className="gn2-error-icon">⚠</span>
              <span className="gn2-error-msg gn2-error-msg--failed">
                {t("canvas.gen.failedWithReason", {
                  msg: errorMessage || data.error || t("canvas.common.unknownError"),
                })}
              </span>
              <button
                type="button"
                className="gn2-retry-btn nodrag"
                onClick={handleRetry}
                disabled={sending || !retryPolicy.retryable}
                title={
                  !retryPolicy.retryable
                    ? t("canvas.gen.retryBlocked", { reason: retryPolicy.reason })
                    : undefined
                }
              >
                {t("canvas.gen.regenerate")}
              </button>
            </div>
          )}
        </div>

        {isDone && ratingTaskId ? (
          <TaskRatingBar
            taskId={ratingTaskId}
            taskType="image"
            userRating={data.userRating ?? null}
            ratingTags={data.ratingTags ?? []}
            ratingComment={data.ratingComment ?? ""}
            defaultExpanded={data.userRating == null}
            onRated={(patch) => patchNodeData(patch, "taskRating")}
          />
        ) : null}

        <MediaFullscreenViewer src={lightboxSrc} kind="image" onClose={() => setLightboxSrc(null)} />

      </div>

      {toast && (
        <div className="gn2-toast nodrag" onPointerDown={(e) => e.stopPropagation()}>
          {toast}
        </div>
      )}

      {cellMenu &&
        createPortal(
          <div
            ref={cellMenuPortalRef}
            className={`cell-menu-portal gn2-dots-menu nodrag nopan ${getThemePageClass()}`}
            style={{
              position: "fixed",
              top: cellMenu.menuPos.y,
              left: cellMenu.menuPos.x,
              zIndex: Z_NODE_DOTS_MENU,
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                e.stopPropagation()
                setLightboxSrc(cellMenu.imageUrl)
                closeCellMenus()
              }}
            >
              <span>🔍</span>{t("canvas.image.zoom")}
            </button>
            <button
              type="button"
              className={`gn2-dots-item menu-item has-submenu nodrag nopan${subMenu ? " gn2-dots-item--submenu-open" : ""}`}
              onMouseEnter={() =>
                handleRefMenuItemEnter(
                  cellMenu.cellIndex,
                  cellMenu.imageIndex,
                  cellMenu.imageUrl
                )
              }
              onMouseLeave={handleRefMenuItemLeave}
            >
              <span>{t("canvas.image.setAsRef")}</span>
            </button>
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                e.stopPropagation()
                handleCopyImageLink(cellMenu.imageUrl)
                closeCellMenus()
              }}
            >
              <span>🔗</span>{t("canvas.image.copyLink")}
            </button>
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                e.stopPropagation()
                handleSaveToAsset(cellMenu.imageUrl)
                closeCellMenus()
              }}
            >
              <span>★</span>{t("canvas.image.favorite")}
            </button>
            <button
              type="button"
              className="gn2-dots-item nodrag nopan"
              onClick={(e) => {
                e.stopPropagation()
                handleCellDownload(cellMenu.imageUrl)
                closeCellMenus()
              }}
            >
              <span>⬇</span>{t("canvas.image.download")}
            </button>
          </div>,
          getThemePortalRoot()
        )}

      {subMenu &&
        createPortal(
          <div
            ref={subMenuPortalRef}
            className={`cell-menu-portal gn2-dots-menu nodrag nopan ${getThemePageClass()}`}
            style={{
              position: "fixed",
              top: subMenu.pos.y,
              left: subMenu.pos.x,
              width: CELL_SUBMENU_WIDTH,
              zIndex: Z_NODE_DOTS_MENU + 1,
            }}
            onMouseEnter={() => clearTimeout(submenuHoverTimerRef.current)}
            onMouseLeave={() => {
              clearTimeout(submenuHoverTimerRef.current)
              submenuHoverTimerRef.current = setTimeout(() => {
                submenuHoverTimerRef.current = null
                setSubMenu(null)
              }, MENU_SUBMENU_CLOSE_MS)
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            {subMenu.step === "video" && (
              <>
                <div className="cell-menu-portal-title">{t("canvas.image.pickVideoCard")}</div>
                {connectedVideoNodes.map((v) => (
                  <button
                    key={v.id}
                    type="button"
                    className="gn2-dots-item nodrag nopan"
                    onClick={(e) => {
                      e.stopPropagation()
                      setSubMenu((prev) => ({
                        ...prev,
                        step: "mode",
                        targetVideoId: v.id,
                      }))
                    }}
                  >
                    {v.label}
                  </button>
                ))}
              </>
            )}
            {subMenu.step === "mode" && subMenu.targetVideoId && (
              <>
                <button
                  type="button"
                  className="gn2-dots-item nodrag nopan"
                  onClick={(e) => {
                    e.stopPropagation()
                    applyReferenceToVideo(
                      subMenu.targetVideoId,
                      subMenu.imageIndex,
                      subMenu.imageUrl,
                      "first"
                    )
                  }}
                >
                  {t("canvas.image.setFirst")}
                </button>
                <button
                  type="button"
                  className="gn2-dots-item nodrag nopan"
                  onClick={(e) => {
                    e.stopPropagation()
                    applyReferenceToVideo(
                      subMenu.targetVideoId,
                      subMenu.imageIndex,
                      subMenu.imageUrl,
                      "last"
                    )
                  }}
                >
                  {t("canvas.image.setLast")}
                </button>
                <button
                  type="button"
                  className="gn2-dots-item nodrag nopan"
                  onClick={(e) => {
                    e.stopPropagation()
                    applyReferenceToVideo(
                      subMenu.targetVideoId,
                      subMenu.imageIndex,
                      subMenu.imageUrl,
                      "freeref"
                    )
                  }}
                >
                  {t("canvas.image.slotFreeref")}
                </button>
              </>
            )}
          </div>,
          getThemePortalRoot()
        )}

    </div>
  )
}

