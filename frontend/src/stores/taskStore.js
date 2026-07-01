import { create } from "zustand"
import { wsManager } from "../services/ws"

/**
 * taskStore – single source of truth for generation tasks.
 *
 * Shape utils call:
 *   taskStore.registerTask(shapeId, taskId, type)   when submitting a job
 *   taskStore.getTaskByShapeId(shapeId)              to read live progress
 *   taskStore.removeTask(shapeId)                    when resetting a card
 *
 * The store owns the single WS listener (startListening / stopListening).
 * Canvas.jsx calls startListening on mount and stopListening on unmount.
 */

export const useTaskStore = create((set, get) => ({
  // tasks: { [taskId]: TaskRecord }
  tasks: {},

  // shapeTaskMap: { [shapeId]: taskId } – fast reverse lookup
  shapeTaskMap: {},

  // ── Task lifecycle ───────────────────────────────────────

  registerTask: (shapeId, taskId, type) => {
    set((s) => ({
      tasks: {
        ...s.tasks,
        [taskId]: {
          taskId,
          shapeId,
          type,
          status: "queued",
          progress: 0,
          result: null,
          errorMsg: null,
        },
      },
      shapeTaskMap: { ...s.shapeTaskMap, [shapeId]: taskId },
    }))
  },

  _updateTask: (taskId, patch) => {
    set((s) => {
      const existing = s.tasks[taskId]
      if (!existing) return s
      return { tasks: { ...s.tasks, [taskId]: { ...existing, ...patch } } }
    })
  },

  removeTask: (shapeId) => {
    set((s) => {
      const taskId = s.shapeTaskMap[shapeId]
      if (!taskId) return s
      const { [taskId]: _t, ...tasks } = s.tasks
      const { [shapeId]: _s, ...shapeTaskMap } = s.shapeTaskMap
      return { tasks, shapeTaskMap }
    })
  },

  // ── Selectors ────────────────────────────────────────────

  getTaskByShapeId: (shapeId) => {
    const { tasks, shapeTaskMap } = get()
    const taskId = shapeTaskMap[shapeId]
    return taskId ? (tasks[taskId] ?? null) : null
  },

  // ── WebSocket handler ────────────────────────────────────

  _handleWsMessage: (msg) => {
    const { type, task_id } = msg
    if (!task_id) return
    const task = get().tasks[task_id]
    if (!task) return

    switch (type) {
      case "progress":
        get()._updateTask(task_id, {
          status: "generating",
          progress: Math.round(msg.data?.percent || 0),
        })
        break
      case "done": {
        const imageFilename = msg.data?.images?.[0] ?? null
        const videoFilename = msg.data?.videos?.[0] ?? null
        get()._updateTask(task_id, {
          status: "completed",
          progress: 100,
          result: { imageFilename, videoFilename },
        })
        break
      }
      case "error":
        get()._updateTask(task_id, {
          status: "error",
          errorMsg: msg.message || msg.data?.error || "生成失败",
        })
        break
      default:
        break
    }
  },

  // ── WS subscription lifecycle ────────────────────────────

  _unsubscribe: null,

  startListening: () => {
    if (get()._unsubscribe) return
    const unsub = wsManager.addListener(get()._handleWsMessage)
    set({ _unsubscribe: unsub })
  },

  stopListening: () => {
    const unsub = get()._unsubscribe
    if (unsub) { unsub(); set({ _unsubscribe: null }) }
  },
}))
