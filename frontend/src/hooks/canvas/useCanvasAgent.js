import { useState, useRef, useCallback, useEffect } from "react"
import { useReactFlow } from "reactflow"
import { addEdge } from "reactflow"
import {
  runAgentStream,
  AgentQuotaError,
  AGENT_REQUEST_TIMEOUT_MS,
  AGENT_SSE_IDLE_TIMEOUT_MS,
} from "../../services/agentApi"
import {
  saveAgentChatHistory,
  syncAgentSession,
  loadAgentSession,
  clearAgentSession,
} from "../../utils/canvas/agentChatHistory"
import { activeChatArchiveId } from "../../utils/canvas/agentConversationStorage"
import { cancelCanvasTask } from "../../services/cancelTask"
import { serializeCanvasForAgent } from "../../utils/canvas/serializeCanvasForAgent"
import {
  buildAgentCreateNodeData,
  AGENT_OUTLINE_WIDTH,
  AGENT_SCRIPT_TABLE_WIDTH,
} from "../../utils/canvas/agentCreateNodeData"
import {
  computeAgentNodePosition,
  createAgentPipelineContext,
  executeAgentPipelineStep,
} from "../../utils/canvas/agentPipeline"
import { getCanvasPipelineBusy } from "../../utils/canvas/canvasPipelineState"
import {
  resolveAgentUserCommand,
  getPipelineStepLabel,
} from "../../utils/canvas/agentCommandRouter"
import { normalizeTextResponseNode } from "../../utils/canvas/nodeNormalize"
import { useModelStore } from "../../stores"

const AGENT_NODE_TYPE_MAP = {
  text: "text-response",
  outline: "outline",
  script_table: "script-table",
  image: "image-gen",
  video: "video-gen",
}

const ENTER_ANIM_MS = 150
const SKIPPED_SUMMARY = "部分操作因节点不存在已跳过"
const MAX_STORED_MESSAGES = 80

function pendingStorageKey(projectId) {
  return projectId ? `agent-pending-${projectId}` : null
}

/** 从「我选择「方案名」（侧重：…）」类用户消息提取 create_text_note 的 prompt */
function buildCreateTextNotePromptFromUserMessage(userContent) {
  const lastUser = (userContent || "").trim()
  if (!lastUser) return null
  if (!lastUser.startsWith("我选择")) return null

  const quoted = lastUser.match(/我选择[「"]([^」"]+)[」"]/)
  if (quoted) {
    const focus = lastUser.match(/侧重[：:]\s*([^）)]+)/)?.[1]
      || lastUser.match(/[（(]([^）)]+)[）)]/)?.[1]
    return {
      prompt: [quoted[1], focus].filter(Boolean).join("，"),
      label: quoted[1],
    }
  }

  const plain = lastUser.replace(/^我选择[：:\s]*/, "").trim()
  if (plain) return { prompt: plain, label: plain.slice(0, 20) }
  return null
}

const NEW_CHAIN_TRIGGER_KEYWORDS = [
  "重新做",
  "换一个",
  "换个",
  "另起",
  "新主题",
  "从头",
  "重新来",
  "新开",
]

function isNewChainTrigger(userInput) {
  const text = (userInput || "").trim()
  if (!text) return false
  if (text.startsWith("我选择")) return true
  return NEW_CHAIN_TRIGGER_KEYWORDS.some((k) => text.includes(k))
}

function collectImageTaskIds(node) {
  if (!node?.data) return []
  const ids = []
  if (node.data.taskId) ids.push(node.data.taskId)
  if (Array.isArray(node.data.taskIds)) ids.push(...node.data.taskIds)
  return [...new Set(ids.filter(Boolean))]
}

function cancelAgentImageTasks(currentNodes, snapshotNodes) {
  const snapshotMap = new Map(snapshotNodes.map((n) => [n.id, n]))
  for (const node of currentNodes) {
    if (node.type !== "image-gen") continue
    const snap = snapshotMap.get(node.id)
    const currentIds = collectImageTaskIds(node)
    const snapIds = new Set(collectImageTaskIds(snap))
    const toCancel = snap ? currentIds.filter((id) => !snapIds.has(id)) : currentIds
    for (const tid of toCancel) {
      cancelCanvasTask(tid).catch((err) => {
        console.warn("[agent] cancel image task failed:", tid, err)
      })
    }
  }
}

function stripNodeRuntime(data) {
  if (!data || typeof data !== "object") return data
  const {
    onUpdate,
    onDelete,
    onDisconnectIncoming,
    onApplyVideoReference,
    onStopGeneration,
    composeNodeData,
    composeOutlineNodeData,
    connectOutlineFromResponse,
    onGenerateScreenplay,
    onGenerateShotScript,
    onGenerateScriptTable,
    onImportScriptTable,
    onMigrateShotScript,
    onRetry,
    ...rest
  } = data
  return rest
}

function cloneCanvas(nodes, edges) {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: { ...n.position },
      zIndex: n.zIndex,
      style: n.style ? { ...n.style } : undefined,
      draggable: n.draggable,
      data: stripNodeRuntime(n.data),
    })),
    edges: edges.map((e) => ({ ...e })),
  }
}

function rebuildNodesFromSnapshot(snapshotNodes, buildData, buildOutlineData) {
  return snapshotNodes.map((n) => {
    const z = n.zIndex ?? n.data?.zIndex ?? 1
    const persisted = stripNodeRuntime(n.data)
    const handlers =
      n.type === "outline"
        ? buildOutlineData?.({ ...persisted, zIndex: z })
        : buildData?.({ ...persisted, zIndex: z })
    const raw = {
      ...n,
      data: { ...handlers, ...persisted, readOnly: persisted.readOnly },
    }
    return n.type === "text-response" ? normalizeTextResponseNode(raw) : raw
  })
}

function serializeMessagesForSave(messages) {
  const slice =
    messages.length > MAX_STORED_MESSAGES
      ? messages.slice(-MAX_STORED_MESSAGES)
      : messages
  return slice.map((m) => ({
    role: m.role,
    content: m.content,
    ...(m.kind ? { kind: m.kind } : {}),
    ...(m.roundId ? { roundId: m.roundId } : {}),
    ...(m.canUndo ? { canUndo: m.canUndo } : {}),
    ...(m.thinking ? { thinking: m.thinking } : {}),
    ...(m.creativeOptions ? { creativeOptions: m.creativeOptions } : {}),
    ...(m.creativeGroupTitle ? { creativeGroupTitle: m.creativeGroupTitle } : {}),
    ...(m.creativeGroupSubtitle ? { creativeGroupSubtitle: m.creativeGroupSubtitle } : {}),
    ...(m.suggestions ? { suggestions: m.suggestions } : {}),
    ...(m.castPending ? { castPending: m.castPending } : {}),
    ...(m.castPendingScriptTableId
      ? { castPendingScriptTableId: m.castPendingScriptTableId }
      : {}),
  }))
}

export function useCanvasAgent({
  projectId,
  readOnlyRef,
  buildData,
  buildOutlineData,
  bumpZIndex,
  workflowRef,
}) {
  const reactFlow = useReactFlow()
  const getCanvasNodes = useCallback(
    () => workflowRef?.current?.getNodes?.() ?? reactFlow.getNodes(),
    [workflowRef, reactFlow]
  )
  const getCanvasEdges = useCallback(
    () => workflowRef?.current?.getEdges?.() ?? reactFlow.getEdges(),
    [workflowRef, reactFlow]
  )
  const setCanvasNodes = useCallback(
    (updater) => {
      const setter = workflowRef?.current?.setNodes ?? reactFlow.setNodes
      return setter(updater)
    },
    [workflowRef, reactFlow]
  )
  const setCanvasEdges = useCallback(
    (updater) => {
      const setter = workflowRef?.current?.setEdges ?? reactFlow.setEdges
      return setter(updater)
    },
    [workflowRef, reactFlow]
  )
  const [messages, setMessages] = useState([])
  const [pendingActions, setPendingActions] = useState([])
  const [thinking, setThinking] = useState("")
  const [streamingReply, setStreamingReply] = useState("")
  const [error, setError] = useState("")
  const [retryErrorUserIndex, setRetryErrorUserIndex] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [executionMode, setExecutionMode] = useState("manual")
  const [pipelineStatus, setPipelineStatus] = useState("")
  const [awaitingReply, setAwaitingReply] = useState(null)
  const [reviewRoundId, setReviewRoundId] = useState(null)
  const [conversationLoading, setConversationLoading] = useState(false)
  const abortRef = useRef(null)
  const currentRoundRef = useRef(null)
  const roundSnapshotsRef = useRef({})
  const roundSnapshotTakenRef = useRef(false)
  const skippedActionsRef = useRef([])
  const skipNotesRef = useRef([])
  const skipSaveRef = useRef(true)
  const timedOutRef = useRef(false)
  const stoppedByUserRef = useRef(false)
  const executedCountRef = useRef(0)
  const messagesRef = useRef([])
  const reviewRoundIdRef = useRef(null)
  const isRunningRef = useRef(false)
  const sendMessageRef = useRef(null)

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    reviewRoundIdRef.current = reviewRoundId
  }, [reviewRoundId])

  useEffect(() => {
    isRunningRef.current = isRunning
  }, [isRunning])

  const persistMessages = useCallback(
    async (msgs) => {
      if (!projectId || skipSaveRef.current || readOnlyRef?.current) return
      if (!Array.isArray(msgs) || msgs.length === 0) return
      await syncAgentSession(projectId, serializeMessagesForSave(msgs))
    },
    [projectId, readOnlyRef]
  )

  useEffect(() => {
    if (!projectId) {
      setMessages([])
      return
    }
    if (readOnlyRef?.current) {
      setMessages([])
      setConversationLoading(false)
      skipSaveRef.current = false
      return
    }
    let cancelled = false
    skipSaveRef.current = true
    setConversationLoading(true)
    loadAgentSession(projectId)
      .then((loaded) => {
        if (cancelled) return
        if (Array.isArray(loaded) && loaded.length > 0) {
          setMessages(loaded)
        } else {
          setMessages([])
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.warn("[agent] load session failed:", err)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setConversationLoading(false)
          skipSaveRef.current = false
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId || conversationLoading) return
    const key = pendingStorageKey(projectId)
    if (!key) return
    try {
      const raw = sessionStorage.getItem(key)
      if (!raw) return
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed?.actions) && parsed.actions.length > 0) {
        setPendingActions(parsed.actions)
        if (parsed.roundId) currentRoundRef.current = parsed.roundId
      }
    } catch {
      /* ignore */
    }
  }, [projectId, conversationLoading])

  useEffect(() => {
    const key = pendingStorageKey(projectId)
    if (!key || skipSaveRef.current) return
    if (pendingActions.length === 0) {
      sessionStorage.removeItem(key)
      return
    }
    sessionStorage.setItem(
      key,
      JSON.stringify({
        actions: pendingActions,
        roundId: currentRoundRef.current,
      })
    )
  }, [pendingActions, projectId])

  const markNodeEnterAnimation = useCallback(
    (nodeId) => {
      setCanvasNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, className: "agent-node-enter" } : n))
      )
      window.setTimeout(() => {
        setCanvasNodes((nds) =>
          nds.map((n) =>
            n.id === nodeId ? { ...n, className: undefined } : n
          )
        )
      }, ENTER_ANIM_MS)
    },
    [setCanvasNodes]
  )

  const maybeTakeRoundSnapshot = useCallback(() => {
    const roundId = currentRoundRef.current
    if (!roundId || roundSnapshotsRef.current[roundId]) return
    roundSnapshotsRef.current[roundId] = cloneCanvas(getCanvasNodes(), getCanvasEdges())
    roundSnapshotTakenRef.current = true
  }, [getCanvasNodes, getCanvasEdges])

  const buildCreateNodeExtra = useCallback((action, z) => {
    const { imageModels, videoModels } = useModelStore.getState()
    return buildAgentCreateNodeData(
      { ...action, _imageModels: imageModels, _videoModels: videoModels },
      z
    )
  }, [])

  const runPipelineStep = useCallback(
    async (action, thinking) => {
      const w = workflowRef?.current
      if (!w?.runTextGeneration) {
        return { ok: false, error: "画布工作流未就绪" }
      }
      const ctx = createAgentPipelineContext({
        getNodes: getCanvasNodes,
        getEdges: getCanvasEdges,
        setNodes: setCanvasNodes,
        setEdges: setCanvasEdges,
        buildData,
        buildOutlineData,
        bumpZIndex,
        runTextGeneration: w.runTextGeneration,
        onGenerateScriptTable: w.onGenerateScriptTable,
        getDefaultTextModelId: w.getDefaultTextModelId,
        getDefaultImageModelId: w.getDefaultImageModelId,
        getDefaultVideoModelId: w.getDefaultVideoModelId,
        patchScriptTableRow: w.patchScriptTableRow,
        runScriptTableRowGenerate: w.runScriptTableRowGenerate,
        runScriptTableRowVideoGenerate: w.runScriptTableRowVideoGenerate,
        createBeatCardForRow: w.createBeatCardForRow,
        patchBeatCard: w.patchBeatCard,
        readOnlyRef,
        signal: abortRef.current?.signal,
      })
      const payload = {
        ...action,
        data: { ...(action.data || {}) },
      }
      return executeAgentPipelineStep(payload, ctx)
    },
    [
      workflowRef,
      getCanvasNodes,
      getCanvasEdges,
      setCanvasNodes,
      setCanvasEdges,
      buildData,
      buildOutlineData,
      bumpZIndex,
      readOnlyRef,
    ]
  )

  const finalizeAgentLayout = useCallback((targetNodeIds = []) => {
    const w = workflowRef?.current
    if (!w?.fitView) return
    const fit = () => {
      const nodes = getCanvasNodes()
      const ids = Array.isArray(targetNodeIds) ? targetNodeIds.filter(Boolean) : []
      const targets = ids.length > 0
        ? nodes.filter((n) => ids.includes(n.id))
        : nodes
      if (targets.length > 0) {
        w.fitView({
          nodes: targets.map((n) => ({ id: n.id })),
          padding: 0.3,
          duration: 400,
        })
      }
    }
    requestAnimationFrame(() => requestAnimationFrame(fit))
  }, [workflowRef, getCanvasNodes])

  const executeActions = useCallback(
    (actions, { animate = false, takeSnapshot = false } = {}) => {
      if (readOnlyRef?.current) return { skipped: [], skipNotes: [], createdNodeIds: [] }

      if (takeSnapshot) {
        maybeTakeRoundSnapshot()
      }

      const nodes = getCanvasNodes()
      const nodeIds = new Set(nodes.map((n) => n.id))
      const idMap = {}
      const newNodes = []
      const newEdges = []
      const skipped = []
      const skipNotes = []
      let z = bumpZIndex?.() ?? 1

      for (const action of actions) {
        if (action.type === "ask_user" || action.type === "done") continue

        if (action.type === "create_node") {
          const flowType = AGENT_NODE_TYPE_MAP[action.node_type] || "text-response"
          const extra = buildCreateNodeExtra(action, z)
          if (!extra || extra.__agentError) {
            skipped.push(action)
            if (extra?.__agentError) skipNotes.push(extra.__agentError)
            continue
          }
          z += 1

          const realId = `agent_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
          if (action.temp_id) idMap[action.temp_id] = realId
          nodeIds.add(realId)

          const nodeData =
            flowType === "outline"
              ? buildOutlineData?.({ ...extra, zIndex: z - 1 }) ?? extra
              : buildData?.({ ...extra, zIndex: z - 1 }) ?? extra

          const width =
            flowType === "script-table"
              ? AGENT_SCRIPT_TABLE_WIDTH
              : flowType === "outline"
                ? AGENT_OUTLINE_WIDTH
                : undefined

          const rawNode = {
            id: realId,
            type: flowType,
            position:
              action.position
              || computeAgentNodePosition(
                [...nodes, ...newNodes],
                [...(getCanvasEdges() || []), ...newEdges],
                flowType
              ),
            zIndex: z - 1,
            ...(width ? { width } : {}),
            style: { zIndex: z - 1, ...(width ? { width } : {}) },
            className: animate ? "agent-node-enter" : undefined,
            data: {
              ...nodeData,
              readOnly: readOnlyRef?.current === true,
            },
          }
          newNodes.push(
            flowType === "text-response" ? normalizeTextResponseNode(rawNode) : rawNode
          )
          if (animate) {
            window.setTimeout(() => markNodeEnterAnimation(realId), 0)
          }
        } else if (action.type === "update_node") {
          if (!nodeIds.has(action.id) && !idMap[action.id]) {
            skipped.push(action)
            continue
          }
          const targetId = idMap[action.id] || action.id
          const newIdx = newNodes.findIndex((n) => n.id === targetId)
          if (newIdx >= 0) {
            newNodes[newIdx] = {
              ...newNodes[newIdx],
              data: { ...newNodes[newIdx].data, ...action.patch },
            }
          } else {
            setCanvasNodes((nds) =>
              nds.map((n) =>
                n.id === targetId
                  ? { ...n, data: { ...n.data, ...action.patch } }
                  : n
              )
            )
          }
        } else if (action.type === "delete_node") {
          const targetId = idMap[action.id] || action.id
          const newIdx = newNodes.findIndex((n) => n.id === targetId)
          if (newIdx >= 0) {
            newNodes.splice(newIdx, 1)
            for (const [k, v] of Object.entries(idMap)) {
              if (v === targetId || k === action.id) delete idMap[k]
            }
            nodeIds.delete(targetId)
          } else if (nodeIds.has(targetId)) {
            setCanvasNodes((nds) => nds.filter((n) => n.id !== targetId))
            setCanvasEdges((eds) =>
              eds.filter((e) => e.source !== targetId && e.target !== targetId)
            )
            nodeIds.delete(targetId)
          } else {
            skipped.push(action)
          }
        } else if (action.type === "create_edge") {
          const source = idMap[action.source] || action.source
          const target = idMap[action.target] || action.target
          if (!nodeIds.has(source) && !idMap[action.source]) {
            skipped.push(action)
            continue
          }
          if (!nodeIds.has(target) && !idMap[action.target]) {
            skipped.push(action)
            continue
          }
          newEdges.push({
            id: `agent_edge_${Date.now()}_${Math.random().toString(36).slice(2, 5)}`,
            source,
            target,
            type: "ghost",
          })
        } else if (action.type === "move_node") {
          const targetId = idMap[action.id] || action.id
          const newIdx = newNodes.findIndex((n) => n.id === targetId)
          if (newIdx >= 0) {
            newNodes[newIdx] = {
              ...newNodes[newIdx],
              position: action.position,
            }
          } else if (nodeIds.has(targetId)) {
            setCanvasNodes((nds) =>
              nds.map((n) =>
                n.id === targetId ? { ...n, position: action.position } : n
              )
            )
          } else {
            skipped.push(action)
          }
        }
      }

      if (newNodes.length > 0) {
        setCanvasNodes((nds) => [...nds, ...newNodes])
      }
      if (newEdges.length > 0) {
        setCanvasEdges((eds) => {
          let next = eds
          for (const edge of newEdges) {
            next = addEdge(edge, next)
          }
          return next
        })
      }

      return { skipped, skipNotes, createdNodeIds: newNodes.map((n) => n.id) }
    },
    [
      getCanvasNodes,
      getCanvasEdges,
      setCanvasNodes,
      setCanvasEdges,
      buildData,
      buildOutlineData,
      bumpZIndex,
      readOnlyRef,
      markNodeEnterAnimation,
      maybeTakeRoundSnapshot,
      buildCreateNodeExtra,
    ]
  )

  const appendSkippedSummary = useCallback((summary, skippedCount) => {
    if (!skippedCount) return summary
    const note = `（${SKIPPED_SUMMARY}）`
    return summary.includes(SKIPPED_SUMMARY) ? summary : `${summary}\n${note}`
  }, [])

  const sendMessage = useCallback(
    async (userInput) => {
      if (isRunningRef.current || readOnlyRef?.current || !projectId) return

      if (reviewRoundIdRef.current) {
        setError("请先「采纳并继续」或「撤销」上一步，再执行下一步")
        return
      }

      const busy = getCanvasPipelineBusy(getCanvasNodes())
      if (busy.busy) {
        setError(busy.reason)
        return
      }

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      timedOutRef.current = false
      stoppedByUserRef.current = false

      const timeoutId = window.setTimeout(() => {
        timedOutRef.current = true
        controller.abort()
      }, AGENT_REQUEST_TIMEOUT_MS)

      const roundId = `round_${Date.now()}`
      currentRoundRef.current = roundId
      roundSnapshotTakenRef.current = false
      skippedActionsRef.current = []
      skipNotesRef.current = []
      executedCountRef.current = 0
      setReviewRoundId(null)
      let allCreatedNodeIds = []

      const newMessage = { role: "user", content: userInput }
      const updatedMessages = [...messagesRef.current, newMessage]
      setMessages(updatedMessages)
      void persistMessages(updatedMessages)
      setIsRunning(true)
      setThinking("")
      setStreamingReply("")
      setPipelineStatus("")
      setError("")
      setRetryErrorUserIndex(null)
      setPendingActions([])
      if (awaitingReply) setAwaitingReply(null)

      const nodes = getCanvasNodes()
      const edges = getCanvasEdges()
      const selectedIds = nodes.filter((n) => n.selected).map((n) => n.id)
      const canvasSnapshot = serializeCanvasForAgent(nodes, edges, selectedIds)

      const directCmd = resolveAgentUserCommand(userInput, nodes, edges)
      if (directCmd?.error) {
        window.clearTimeout(timeoutId)
        setIsRunning(false)
        setError(directCmd.error)
        return
      }
      if (directCmd?.action) {
        try {
          maybeTakeRoundSnapshot()
          setThinking("")
          setPipelineStatus(directCmd.statusLabel || getPipelineStepLabel(directCmd.action.step))
          const result = await runPipelineStep(directCmd.action, "")
          if (stoppedByUserRef.current) {
            setError("已停止生成")
            stoppedByUserRef.current = false
            return
          }
          setPipelineStatus("")
          if (result.nodeIds?.length) {
            allCreatedNodeIds.push(...result.nodeIds)
          }
          finalizeAgentLayout(result.nodeIds || [])

          let summary = directCmd.successSummary || "本步已执行"
          if (!result.ok && result.error) {
            summary = result.error
          } else {
            executedCountRef.current = 1
          }

          const isAuto = executionMode === "auto"
          const needsReview = result.ok && roundSnapshotTakenRef.current
          const canUndo = needsReview && !isAuto

          const assistantMsg = {
            role: "assistant",
            content: summary,
            roundId,
            canUndo,
            thinking: directCmd.statusLabel
              ? `✓ 已识别指令\n→ ${directCmd.statusLabel.replace(/…$/, "")}`
              : undefined,
          }
          const withReply = [...updatedMessages, assistantMsg]
          setMessages(withReply)
          await persistMessages(withReply)
          if (needsReview) setReviewRoundId(roundId)

          if (isAuto && result.ok && needsReview) {
            // 自动模式：等待输入框上方确认条，不自动发「继续」
          } else if (isAuto && result.ok && !needsReview) {
            const busyAfter = getCanvasPipelineBusy(getCanvasNodes())
            if (!busyAfter.busy) {
              delete roundSnapshotsRef.current[roundId]
              window.setTimeout(() => {
                if (!isRunningRef.current && !reviewRoundIdRef.current) {
                  sendMessageRef.current?.("继续")
                }
              }, 600)
            }
          }
        } catch (err) {
          setError(err?.message || "执行失败")
        } finally {
          window.clearTimeout(timeoutId)
          setIsRunning(false)
          setPipelineStatus("")
          finalizeAgentLayout(allCreatedNodeIds)
        }
        return
      }

      let idleTimedOut = false
      let idleCheckId = null
      let inPipelineStep = false

      try {
        const messagesForLLM = isNewChainTrigger(userInput)
          ? [{ role: "user", content: userInput }]
          : updatedMessages

        const response = await runAgentStream(
          {
            project_id: projectId,
            canvas_snapshot: canvasSnapshot,
            messages: messagesForLLM,
            execution_mode: executionMode,
          },
          { signal: controller.signal }
        )

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        const collectedActions = []
        let collectedThinking = ""
        let buffer = ""
        let pausedAtAsk = false
        let askQuestion = null
        let finalMessages = updatedMessages

        let streamBuffer = ""
        let collectedReply = ""
        let lastCreatedTextNoteId = null
        let lastCastPending = null
        let lastCastPendingScriptTableId = null
        let lastScenePending = null
        let lastScenePendingScriptTableId = null
        let criticalStepFailed = false
        let streamErrored = false
        let lastEventAt = Date.now()
        idleCheckId = window.setInterval(() => {
          if (inPipelineStep) return
          if (Date.now() - lastEventAt > AGENT_SSE_IDLE_TIMEOUT_MS) {
            idleTimedOut = true
            controller.abort()
          }
        }, 5000)

        while (true) {
          if (stoppedByUserRef.current) break
          const { value, done } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split("\n\n")
          buffer = parts.pop() || ""

          for (const part of parts) {
            const line = part.split("\n").find((l) => l.startsWith("data: "))
            if (!line) continue

            let data
            try {
              data = JSON.parse(line.slice(6))
            } catch {
              continue
            }

            lastEventAt = Date.now()

            if (data.event === "thinking_delta") {
              streamBuffer += data.content || ""
            } else if (data.event === "status_delta") {
              const piece = data.content || ""
              if (data.append) {
                collectedThinking += piece
              } else {
                collectedThinking = piece
              }
              setThinking(collectedThinking)
            } else if (data.event === "reply_delta") {
              collectedReply += data.content || ""
              setStreamingReply(collectedReply)
            } else if (data.event === "thinking") {
              collectedThinking = data.content
              setThinking(data.content)
            } else if (data.event === "action") {
              const action = data.action
              collectedActions.push(action)

              if (action.type === "ask_user") {
                pausedAtAsk = true
                askQuestion = action.question
                setAwaitingReply(action.question)
                isRunningRef.current = false
                setIsRunning(false)
                const groupTitle = action.group_title || ""
                const groupSubtitle = action.group_subtitle || ""
                const hasCreativeCards = Array.isArray(action.options) && action.options.length > 0
                const castPendingFromAsk = Array.isArray(action.cast_pending)
                  ? action.cast_pending.map((name, idx) => ({
                      id: `pending-${idx}`,
                      name: typeof name === "string" ? name : name?.name || "",
                      type: "character",
                    })).filter((c) => c.name)
                  : null
                const scenePendingFromAsk = Array.isArray(action.scene_pending)
                  ? action.scene_pending.map((name, idx) => ({
                      id: `scene-pending-${idx}`,
                      name: typeof name === "string" ? name : name?.name || "",
                      type: "scene",
                    })).filter((s) => s.name)
                  : null
                const intro =
                  hasCreativeCards && (groupTitle || groupSubtitle)
                    ? ""
                    : (action.question || "").trim()
                finalMessages = [
                  ...finalMessages,
                  {
                    role: "assistant",
                    content: intro,
                    kind: "ask",
                    creativeOptions: Array.isArray(action.options) ? action.options : null,
                    creativeGroupTitle: groupTitle || undefined,
                    creativeGroupSubtitle: groupSubtitle || undefined,
                    castPending: castPendingFromAsk?.length
                      ? castPendingFromAsk
                      : lastCastPending || undefined,
                    castPendingScriptTableId:
                      action.script_table_id
                      || lastCastPendingScriptTableId
                      || undefined,
                    scenePending: scenePendingFromAsk?.length
                      ? scenePendingFromAsk
                      : lastScenePending || undefined,
                    scenePendingScriptTableId:
                      action.script_table_id
                      || lastScenePendingScriptTableId
                      || undefined,
                    roundId,
                    ...(collectedThinking
                      ? { thinking: collectedThinking }
                      : {}),
                  },
                ]
                setMessages(finalMessages)
                persistMessages(finalMessages)
                setThinking("")
                setStreamingReply("")
                continue
              }

              if (pausedAtAsk) continue

              if (action.type === "done") continue

              if (action.type === "pipeline_step") {
                if (stoppedByUserRef.current) break
                if (!roundSnapshotTakenRef.current) {
                  maybeTakeRoundSnapshot()
                }
                const stepLabels = {
                  create_text_note: "正在创建文本输入卡…",
                  start_text_generation: "正在生成剧本文本…",
                  generate_outline: "正在生成剧本大纲…",
                  generate_script_table: "正在生成分镜表…",
                  split_shot_beats: "正在拆分镜头节拍…",
                  generate_storyboard: "正在生成分镜图…",
                  generate_video: "正在生成镜头视频…",
                  manage_cast: "正在更新角色设定库…",
                  manage_scene: "正在更新场景实体库…",
                }
                let pipelineAction = action
                if (
                  action.step === "create_text_note"
                  && !(action.data?.prompt || action.data?.content || "").trim()
                ) {
                  const lastUserMsg = finalMessages
                    .filter((m) => m.role === "user")
                    .slice(-1)[0]?.content
                  const inferred = buildCreateTextNotePromptFromUserMessage(lastUserMsg)
                  if (inferred?.prompt) {
                    pipelineAction = {
                      ...action,
                      data: {
                        ...(action.data || {}),
                        prompt: inferred.prompt,
                        label: action.data?.label || inferred.label,
                        intent: action.data?.intent || "screenplay",
                      },
                    }
                  }
                }
                if (
                  action.step === "start_text_generation"
                  && lastCreatedTextNoteId
                ) {
                  pipelineAction = {
                    ...action,
                    data: {
                      ...(action.data || {}),
                      source_id: lastCreatedTextNoteId,
                      text_note_id: lastCreatedTextNoteId,
                    },
                  }
                  lastCreatedTextNoteId = null
                }
                setThinking("")
                setPipelineStatus(stepLabels[pipelineAction.step] || "正在执行本步…")
                inPipelineStep = true
                lastEventAt = Date.now()
                const result = await runPipelineStep(
                  pipelineAction,
                  collectedThinking || streamBuffer
                )
                inPipelineStep = false
                lastEventAt = Date.now()
                if (stoppedByUserRef.current) break
                setPipelineStatus("")
                if (result.ok) {
                  executedCountRef.current += 1
                  if (result.nodeIds?.length) {
                    allCreatedNodeIds.push(...result.nodeIds)
                  }
                  if (
                    pipelineAction.step === "create_text_note"
                    && result.nodeIds?.[0]
                  ) {
                    lastCreatedTextNoteId = result.nodeIds[0]
                  }
                  if (
                    pipelineAction.step === "manage_cast"
                    && result.castPending?.length
                  ) {
                    lastCastPending = result.castPending
                    lastCastPendingScriptTableId = result.scriptTableId || null
                  }
                  if (
                    pipelineAction.step === "manage_scene"
                    && result.scenePending?.length
                  ) {
                    lastScenePending = result.scenePending
                    lastScenePendingScriptTableId = result.scriptTableId || null
                  }
                  finalizeAgentLayout(result.nodeIds || [])
                } else if (result.error) {
                  skipNotesRef.current.push(result.error)
                  if (pipelineAction.step === "create_text_note") {
                    criticalStepFailed = true
                  }
                  if (result.error === "已停止") break
                }
              } else {
                const { skipped, skipNotes, createdNodeIds } = executeActions([action], {
                  animate: true,
                  takeSnapshot: !roundSnapshotTakenRef.current,
                })
                if (skipped.length === 0) executedCountRef.current += 1
                skippedActionsRef.current.push(...skipped)
                if (skipNotes?.length) skipNotesRef.current.push(...skipNotes)
                if (createdNodeIds?.length) {
                  allCreatedNodeIds.push(...createdNodeIds)
                }
                finalizeAgentLayout(createdNodeIds || [])
              }
            } else if (data.event === "done") {
              if (askQuestion) {
                setThinking("")
                setStreamingReply("")
                break
              }

              const doneAction = collectedActions.find((a) => a.type === "done")
              const executed = executedCountRef.current
              const suggestions = Array.isArray(data.suggestions) ? data.suggestions : []

              let summary = collectedReply || doneAction?.summary || collectedThinking || ""
              const errorNotes = [...new Set(skipNotesRef.current)].filter(Boolean)
              const hadPipelineStep = collectedActions.some((a) => a.type === "pipeline_step")

              if (
                (criticalStepFailed || (executed === 0 && hadPipelineStep))
                && skipNotesRef.current.length > 0
              ) {
                summary = skipNotesRef.current.join("；")
              } else if (errorNotes.length > 0) {
                const errText = errorNotes.join("；")
                summary = executed > 0
                  ? `${summary || "本步部分完成"}\n\n问题：${errText}`
                  : errText
              } else if (!summary && executed > 0) {
                summary = "本步已应用到画布"
              }

              if (executed === 0 && errorNotes.length === 0 && skipNotesRef.current.length > 0) {
                summary = skipNotesRef.current.join("；")
              }

              const hasImage = collectedActions.some(
                (a) => a.type === "create_node" && a.node_type === "image"
              )
              const hasVideo = collectedActions.some(
                (a) => a.type === "create_node" && a.node_type === "video"
              )
              if (hasImage && executed > 0 && !summary.includes("异步")) {
                summary += "\n（图像节点已创建，正在异步生成，请稍候）"
              }
              if (hasVideo && executed > 0 && !summary.includes("异步")) {
                summary += "\n（视频节点已创建，正在异步生成，请稍候）"
              }

              summary = appendSkippedSummary(
                summary,
                skippedActionsRef.current.length
              )

              if (skipNotesRef.current.length > 0) {
                const notes = [...new Set(skipNotesRef.current)].join("；")
                if (!summary.includes(notes)) {
                  summary = summary ? `${summary}\n（${notes}）` : notes
                }
              }

              const isAuto = executionMode === "auto"
              const needsReview =
                roundSnapshotTakenRef.current && executed > 0 && errorNotes.length === 0
              const canUndo = needsReview && !isAuto
              if (needsReview) setReviewRoundId(roundId)

              finalMessages = [
                ...finalMessages,
                {
                  role: "assistant",
                  content: summary,
                  roundId,
                  canUndo,
                  suggestions: suggestions.length > 0 ? suggestions : undefined,
                  ...(lastCastPending?.length
                    ? {
                        castPending: lastCastPending,
                        castPendingScriptTableId: lastCastPendingScriptTableId,
                      }
                    : {}),
                  ...(lastScenePending?.length
                    ? {
                        scenePending: lastScenePending,
                        scenePendingScriptTableId: lastScenePendingScriptTableId,
                      }
                    : {}),
                  ...(collectedThinking
                    ? { thinking: collectedThinking }
                    : {}),
                },
              ]
              setMessages(finalMessages)
              persistMessages(finalMessages)
              setThinking("")
              setStreamingReply("")

              if (isAuto && errorNotes.length > 0) {
                setError(`自动生成已暂停：${errorNotes.join("；")}`)
              } else if (isAuto && executed > 0 && !askQuestion && !needsReview) {
                const busyAfter = getCanvasPipelineBusy(getCanvasNodes())
                if (!busyAfter.busy) {
                  delete roundSnapshotsRef.current[roundId]
                  window.setTimeout(() => {
                    if (!isRunningRef.current && !reviewRoundIdRef.current) {
                      const busyLater = getCanvasPipelineBusy(getCanvasNodes())
                      if (!busyLater.busy) {
                        sendMessageRef.current?.("继续")
                      }
                    }
                  }, 600)
                }
              }
            } else if (data.event === "error") {
              streamErrored = true
              const msg = data.message || "Agent 执行失败"
              if (msg.includes("JSON") || msg.includes("格式异常")) {
                setError("AI 返回格式异常，请重新描述需求")
              } else {
                setError(msg)
              }
              setRetryErrorUserIndex(Math.max(0, updatedMessages.length - 1))
              if (collectedThinking || collectedReply.trim()) {
                finalMessages = [
                  ...updatedMessages,
                  {
                    role: "assistant",
                    content: collectedReply.trim() || "本轮未完成，请重试。",
                    thinking: collectedThinking || undefined,
                    roundId,
                  },
                ]
                setMessages(finalMessages)
                void persistMessages(finalMessages)
              }
              break
            }
          }
          if (streamErrored) break
        }
      } catch (err) {
        if (err.name === "AbortError") {
          if (stoppedByUserRef.current) {
            setError("已停止生成")
            stoppedByUserRef.current = false
          } else if (idleTimedOut) {
            setError("AI 响应超时，请重试")
          } else if (timedOutRef.current) {
            setError("请求超时，请重试")
          }
          return
        }
        if (err instanceof AgentQuotaError) {
          setError(err.message || "配额不足，请升级")
        } else if (err.name === "TimeoutError" || err.message?.includes("timeout")) {
          setError("请求超时，请重试")
        } else {
          setError(err.message || "Agent 请求失败")
        }
      } finally {
        if (idleCheckId != null) window.clearInterval(idleCheckId)
        window.clearTimeout(timeoutId)
        setIsRunning(false)
        setThinking("")
        setStreamingReply("")
        setPipelineStatus("")
        finalizeAgentLayout(allCreatedNodeIds)
      }
    },
    [
      executionMode,
      projectId,
      getCanvasNodes,
      getCanvasEdges,
      executeActions,
      readOnlyRef,
      awaitingReply,
      persistMessages,
      appendSkippedSummary,
      runPipelineStep,
      finalizeAgentLayout,
      maybeTakeRoundSnapshot,
      runPipelineStep,
      finalizeAgentLayout,
    ]
  )

  useEffect(() => {
    sendMessageRef.current = sendMessage
  }, [sendMessage])

  const confirmPendingActions = useCallback(() => {
    const roundId = currentRoundRef.current
    if (pendingActions.length === 0) return

    const actionCount = pendingActions.length
    const hasImage = pendingActions.some(
      (a) => a.type === "create_node" && a.node_type === "image"
    )
    const { skipped, skipNotes } = executeActions(pendingActions, { takeSnapshot: true })
    if (skipped.length > 0) {
      skippedActionsRef.current.push(...skipped)
    }
    if (skipNotes?.length) {
      skipNotesRef.current.push(...skipNotes)
    }
    setPendingActions([])
    const key = pendingStorageKey(projectId)
    if (key) sessionStorage.removeItem(key)

    if (!roundId) return

    setMessages((prev) => {
      const next = [...prev]
      for (let i = next.length - 1; i >= 0; i -= 1) {
        if (next[i].role === "assistant" && next[i].roundId === roundId) {
          let content = next[i].content.replace(
            /\n?\n?待确认 \d+ 个操作$/,
            ""
          )
          if (actionCount > 0) {
            content = content
              ? `${content}\n\n已完成 ${actionCount} 个操作`
              : `已完成 ${actionCount} 个操作`
          }
          if (hasImage && !content.includes("异步")) {
            content += "\n（图像节点已创建，正在异步生成，请稍候）"
          }
          content = appendSkippedSummary(content, skipped.length)
          if (skipNotes?.length) {
            const notes = [...new Set(skipNotes)].join("；")
            if (!content.includes(notes)) content += `\n（${notes}）`
          }
          const { kind: _kind, ...rest } = next[i]
          next[i] = { ...rest, content, canUndo: true }
          break
        }
      }
      persistMessages(next)
      return next
    })
  }, [pendingActions, executeActions, persistMessages, appendSkippedSummary, projectId])

  const cancelPendingActions = useCallback(() => {
    const roundId = currentRoundRef.current
    setPendingActions([])
    const key = pendingStorageKey(projectId)
    if (key) sessionStorage.removeItem(key)

    if (!roundId) return

    setMessages((prev) => {
      const idx = prev.findIndex(
        (m) =>
          m.role === "assistant" && m.roundId === roundId && m.kind === "pending"
      )
      if (idx < 0) return prev
      const next = prev.filter((_, i) => i !== idx)
      persistMessages(next)
      return next
    })
  }, [persistMessages, projectId])

  const undoRound = useCallback(
    (roundId) => {
      const snapshot = roundSnapshotsRef.current[roundId]
      if (!snapshot || readOnlyRef?.current) return

      cancelAgentImageTasks(getCanvasNodes(), snapshot.nodes)
      setReviewRoundId(null)
      reviewRoundIdRef.current = null
      setCanvasNodes(rebuildNodesFromSnapshot(snapshot.nodes, buildData, buildOutlineData))
      setCanvasEdges(snapshot.edges)
      delete roundSnapshotsRef.current[roundId]

      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.roundId === roundId && m.role === "assistant")
        if (idx < 0) return prev
        const userIdx = idx > 0 && prev[idx - 1].role === "user" ? idx - 1 : -1
        const next = prev.filter((_, i) => i !== idx && i !== userIdx)
        persistMessages(next)
        return next
      })
    },
    [setCanvasNodes, setCanvasEdges, readOnlyRef, buildData, buildOutlineData, persistMessages, getCanvasNodes]
  )

  const acceptRound = useCallback(
    (roundId, { continueNext = false } = {}) => {
      const busy = getCanvasPipelineBusy(getCanvasNodes())
      if (busy.busy) {
        setError(busy.reason)
        return
      }

      delete roundSnapshotsRef.current[roundId]
      setReviewRoundId(null)
      reviewRoundIdRef.current = null
      setError("")
      setMessages((prev) => {
        const next = prev.map((m) =>
          m.roundId === roundId ? { ...m, canUndo: false } : m
        )
        persistMessages(next)
        return next
      })
      if (continueNext) {
        window.setTimeout(() => {
          sendMessageRef.current?.("继续")
        }, 0)
      }
    },
    [getCanvasNodes, setCanvasNodes, persistMessages]
  )

  const stopGeneration = useCallback(() => {
    if (!isRunningRef.current) return
    stoppedByUserRef.current = true
    timedOutRef.current = false
    abortRef.current?.abort()
    isRunningRef.current = false
    setIsRunning(false)
    setPipelineStatus("")
    setStreamingReply("")
  }, [])

  const startNewChat = useCallback(async () => {
    if (isRunningRef.current) return
    const current = messagesRef.current
    if (current.length > 0 && projectId) {
      await saveAgentChatHistory(projectId, serializeMessagesForSave(current), {
        id: `chat_${Date.now()}`,
      })
    }
    setMessages([])
    setReviewRoundId(null)
    reviewRoundIdRef.current = null
    setError("")
    setThinking("")
    if (projectId) {
      skipSaveRef.current = true
      await clearAgentSession(projectId)
      skipSaveRef.current = false
    }
  }, [projectId])

  const loadChatHistory = useCallback(
    async (entry) => {
      if (!entry?.messages || isRunningRef.current) return
      const current = messagesRef.current
      const activeId = projectId ? activeChatArchiveId(projectId) : null
      if (current.length > 0 && projectId && entry.id !== activeId) {
        await saveAgentChatHistory(projectId, serializeMessagesForSave(current), {
          id: `chat_${Date.now()}`,
        })
      }
      setMessages(entry.messages)
      setReviewRoundId(null)
      reviewRoundIdRef.current = null
      setError("")
      if (projectId) {
        skipSaveRef.current = true
        await syncAgentSession(projectId, serializeMessagesForSave(entry.messages))
        skipSaveRef.current = false
      }
    },
    [projectId]
  )

  const startNewChatFromHistory = useCallback(
    async (entry) => {
      if (!entry?.messages || isRunningRef.current) return
      const current = messagesRef.current
      if (current.length > 0 && projectId) {
        await saveAgentChatHistory(projectId, serializeMessagesForSave(current), {
          id: `chat_${Date.now()}`,
        })
      }
      setMessages(entry.messages)
      setReviewRoundId(null)
      reviewRoundIdRef.current = null
      setError("")
      setThinking("")
      if (projectId) {
        skipSaveRef.current = true
        await syncAgentSession(projectId, serializeMessagesForSave(entry.messages))
        skipSaveRef.current = false
      }
    },
    [projectId]
  )

  const startNewChatFromMessage = useCallback(
    async (index) => {
      if (isRunningRef.current) return
      const current = messagesRef.current
      if (index < 0 || index >= current.length) return
      const branch = current.slice(0, index + 1)
      if (current.length > 0 && projectId) {
        await saveAgentChatHistory(projectId, serializeMessagesForSave(current), {
          id: `chat_${Date.now()}`,
        })
      }
      setMessages(branch)
      setReviewRoundId(null)
      reviewRoundIdRef.current = null
      setError("")
      setThinking("")
      if (projectId) {
        skipSaveRef.current = true
        await syncAgentSession(projectId, serializeMessagesForSave(branch))
        skipSaveRef.current = false
      }
    },
    [projectId]
  )

  const deleteMessageAt = useCallback(
    async (index) => {
      if (isRunningRef.current || readOnlyRef?.current) return
      const msgs = messagesRef.current
      if (index < 0 || index >= msgs.length) return

      const next = [...msgs]
      if (next[index]?.role === "user" && next[index + 1]?.role === "assistant") {
        next.splice(index, 2)
      } else {
        next.splice(index, 1)
      }

      setReviewRoundId(null)
      reviewRoundIdRef.current = null
      setMessages(next)
      await persistMessages(next)
    },
    [persistMessages, readOnlyRef]
  )

  const retryFromMessage = useCallback(
    async (index) => {
      if (isRunningRef.current || readOnlyRef?.current) return
      const msgs = messagesRef.current
      const msg = msgs[index]
      if (!msg || msg.role !== "user") return

      const truncated = msgs.slice(0, index)
      setReviewRoundId(null)
      reviewRoundIdRef.current = null
      setError("")
      setRetryErrorUserIndex(null)
      setMessages(truncated)
      await persistMessages(truncated)
      await sendMessage(msg.content)
    },
    [sendMessage, persistMessages, readOnlyRef]
  )

  return {
    messages,
    thinking,
    streamingReply,
    error,
    retryErrorUserIndex,
    isRunning,
    pendingActions,
    executionMode,
    pipelineStatus,
    awaitingReply,
    conversationLoading,
    reviewRoundId,
    setExecutionMode,
    sendMessage,
    confirmPendingActions,
    cancelPendingActions,
    undoRound,
    acceptRound,
    stopGeneration,
    startNewChat,
    loadChatHistory,
    startNewChatFromHistory,
    startNewChatFromMessage,
    deleteMessageAt,
    retryFromMessage,
  }
}
