import api from "./api"

/** 停止画布/工作台 ComfyUI 任务（后端会解析 comfyui_prompt_id） */
export async function cancelCanvasTask(taskId) {
  if (!taskId) return
  await api.post(`/api/task/${encodeURIComponent(taskId)}/cancel`)
}
