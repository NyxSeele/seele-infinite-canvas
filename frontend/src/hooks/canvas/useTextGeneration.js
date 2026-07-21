import { useCallback, useEffect, useRef } from "react"
import { addEdge } from "reactflow"
import api from "../../services/api"
import { isNetworkError } from "../../components/canvas/taskNetworkError"
import { teamIdPayload } from "../../utils/teamContext"
import { cancelCanvasTask } from "../../services/cancelTask"
import { TASK_POLL_TIMEOUT_MS } from "../../components/canvas/taskPollTimeout"
import { createRateLimitBackoffState } from "../../utils/canvas/rateLimitBackoff"
import { normalizeTextResponseNode } from "../../utils/canvas/nodeNormalize"
import { TEXT_NOTE_WIDTH, TEXT_MODES } from "../../utils/canvas/nodeHelpers"
import { getT } from "../../utils/locale"

const TASK_POLL_INTERVAL_MS = 5000

function extractTextTaskResult(task) {
  const raw = task?.result
  if (typeof raw === "string") return raw
  if (raw && typeof raw === "object") {
    return raw.text || raw.content || ""
  }
  return ""
}

export function useTextGeneration({ setNodes, setEdges, getNode, buildData, setSelectedNodeId }) {
  const pollTimersRef = useRef(new Map())
  const textRetryRef = useRef(() => {})

  useEffect(() => () => {
    pollTimersRef.current.forEach(({ interval, timeout }) => {
      clearInterval(interval)
      clearTimeout(timeout)
    })
    pollTimersRef.current.clear()
  }, [])

  const updateResponseNodeData = useCallback((responseNodeId, patch) => {
    setNodes((ns) =>
      ns.map((n) =>
        n.id === responseNodeId ? { ...n, data: { ...n.data, ...patch } } : n
      )
    )
  }, [setNodes])

  const stopPolling = useCallback((responseNodeId) => {
    const timers = pollTimersRef.current.get(responseNodeId)
    if (!timers) return
    clearInterval(timers.interval)
    clearTimeout(timers.timeout)
    pollTimersRef.current.delete(responseNodeId)
  }, [])

  const applyTextTaskPollResult = useCallback((task, taskId, responseNodeId) => {
    if (task.status === "completed") {
      const text = extractTextTaskResult(task)
      const src = getNode(getNode(responseNodeId)?.data?.sourceNodeId)
      const screenplayMode = src?.data?.textMode === TEXT_MODES.SCREENPLAY
      updateResponseNodeData(responseNodeId, {
        status: "completed",
        content: text,
        taskId,
        screenplayMode,
        // 大纲由 Agent pipeline_step generate_outline 或用户点「整理到大纲」触发，勿自动抢跑
        outlineAutoPending: false,
      })
      return true
    }
    if (task.status === "failed") {
      updateResponseNodeData(responseNodeId, {
        status: "failed",
        error: task.error || getT()("canvas.common.unknownError"),
      })
      return true
    }
    if (task.status === "processing" || task.status === "queued" || task.status === "running") {
      updateResponseNodeData(responseNodeId, { status: "generating", taskId })
    }
    return false
  }, [getNode, updateResponseNodeData])

  const startPolling = useCallback((taskId, responseNodeId) => {
    stopPolling(responseNodeId)
    const rateLimit = createRateLimitBackoffState()

    const interval = setInterval(async () => {
      if (rateLimit.paused) return
      try {
        const res = await api.get(`/api/tasks/${taskId}`)
        const task = res.data
        rateLimit.reset()
        if (applyTextTaskPollResult(task, taskId, responseNodeId)) {
          stopPolling(responseNodeId)
        }
      } catch (err) {
        if (isNetworkError(err)) return
        if (rateLimit.apply(err)) return
        console.error("poll task error:", err)
        stopPolling(responseNodeId)
        updateResponseNodeData(responseNodeId, {
          status: "failed",
          error: getT()("canvas.common.networkError"),
        })
      }
    }, TASK_POLL_INTERVAL_MS)

    const timeout = setTimeout(async () => {
      try {
        const res = await api.get(`/api/tasks/${taskId}`)
        const task = res.data
        if (applyTextTaskPollResult(task, taskId, responseNodeId)) {
          stopPolling(responseNodeId)
          return
        }
      } catch {
        /* 超时前最后一次查询失败则按超时处理 */
      }
      stopPolling(responseNodeId)
      setNodes((ns) => {
        const node = ns.find((n) => n.id === responseNodeId)
        if (node?.data?.status !== "generating") return ns
        return ns.map((n) =>
          n.id === responseNodeId
            ? { ...n, data: { ...n.data, status: "failed", error: getT()("canvas.gen.timeout") } }
            : n
        )
      })
    }, TASK_POLL_TIMEOUT_MS)

    pollTimersRef.current.set(responseNodeId, { interval, timeout })
  }, [stopPolling, updateResponseNodeData, setNodes, applyTextTaskPollResult])

  const patchNodeData = useCallback(
    (nodeId, patch) => {
      setNodes((ns) =>
        ns.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n
        )
      )
    },
    [setNodes]
  )

  const runTextGeneration = useCallback(async (nodeId, params, existingResponseId = null) => {
    if (!params.modelId || !params.prompt?.trim()) return

    const sourceNode = getNode(nodeId)
    if (!sourceNode) return

    let responseNodeId = existingResponseId

    if (!responseNodeId) {
      responseNodeId = `text-response-${Date.now()}`
      const sourceW = sourceNode.width ?? TEXT_NOTE_WIDTH
      const responseNode = normalizeTextResponseNode({
        id: responseNodeId,
        type: "text-response",
        draggable: true,
        position: {
          x: sourceNode.position.x + sourceW + 80,
          y: sourceNode.position.y,
        },
        data: {
          ...buildData({
            status: "generating",
            content: "",
            error: "",
            sourceNodeId: nodeId,
            screenplayMode: sourceNode.data?.textMode === TEXT_MODES.SCREENPLAY,
            model: params.modelId,
            prompt: params.prompt,
            count: params.count || 1,
          }),
          onRetry: (id) => textRetryRef.current(id),
        },
      })
      setNodes((ns) => [...ns, responseNode])
      setEdges((es) =>
        addEdge(
          {
            id: `edge-${nodeId}-${responseNodeId}`,
            source: nodeId,
            sourceHandle: "src-right",
            target: responseNodeId,
            targetHandle: "tgt",
            type: "ghost",
            animated: false,
          },
          es
        )
      )
      setSelectedNodeId(null)
    } else {
      updateResponseNodeData(responseNodeId, {
        status: "generating",
        content: "",
        error: "",
        model: params.modelId,
        prompt: params.prompt,
        count: params.count || 1,
      })
    }

    setNodes((ns) =>
      ns.map((n) => {
        if (n.id !== nodeId) return n
        return {
          ...n,
          data: {
            ...n.data,
            prompt: params.prompt,
            modelId: params.modelId,
          },
        }
      })
    )

    try {
      const screenplayMode = sourceNode.data?.textMode === TEXT_MODES.SCREENPLAY
      const res = await api.post("/api/tasks/text", {
        model: params.modelId,
        prompt: params.prompt,
        count: params.count || 1,
        node_id: nodeId,
        screenplay_mode: screenplayMode,
        ...teamIdPayload(),
      })
      if (res.data?.task_id) {
        updateResponseNodeData(responseNodeId, { taskId: res.data.task_id })
        startPolling(res.data.task_id, responseNodeId)
      }
    } catch (err) {
      const msg = err.response?.data?.detail || getT()("canvas.error.textGenFail")
      console.error("text task error:", err)
      updateResponseNodeData(responseNodeId, { status: "failed", error: msg })
    }

    return responseNodeId
  }, [getNode, buildData, setNodes, setEdges, setSelectedNodeId, updateResponseNodeData, startPolling])

  const handleTextResponseRetry = useCallback((responseNodeId) => {
    const responseNode = getNode(responseNodeId)
    if (!responseNode?.data?.sourceNodeId) return
    const { sourceNodeId, model, prompt, count } = responseNode.data
    runTextGeneration(sourceNodeId, {
      modelId: model,
      prompt: prompt || "",
      count: count || 1,
    }, responseNodeId)
  }, [getNode, runTextGeneration])

  textRetryRef.current = handleTextResponseRetry

  return {
    updateResponseNodeData,
    runTextGeneration,
    textRetryRef,
    patchNodeData,
    stopPolling,
  }
}
