import { useCanvasStore } from "../stores/canvasStore"
import { useTeamStore } from "../stores/teamStore"

/** 当前工作区/画布上下文下的 team_id（个人为 null） */
export function getActiveTeamId() {
  return useTeamStore.getState().activeTeamId || null
}

/** 画布项目所属团队（优先 projectTeamId，与资产库一致） */
export function getCanvasTeamId() {
  const projectTeamId = useCanvasStore.getState().projectTeamId
  return projectTeamId ?? getActiveTeamId() ?? null
}

/** 生成任务请求体附加字段 */
export function teamIdPayload() {
  const teamId = getCanvasTeamId()
  return teamId ? { team_id: teamId } : {}
}
