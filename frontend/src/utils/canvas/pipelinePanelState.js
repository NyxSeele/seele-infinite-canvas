import { buildActiveChain, inferPipelineStage } from "./agentPipeline"
import {
  rowDirectImageReady,
  rowDirectVideoReady,
  rowHasBeatPrompts,
  rowStoryboardReady,
  rowVideoReady,
} from "./scriptTableKeyframes"

/** inferPipelineStage 返回值 → manifest stage name */
export function mapInferStageToManifestStep(stage) {
  const map = {
    create_text_note: "create_text_note",
    start_text_generation: "start_text_generation",
    wait_text_generation: "start_text_generation",
    chat_done: "pipeline_complete",
    generate_outline: "generate_outline",
    wait_outline: "generate_outline",
    generate_script_table: "generate_script_table",
    wait_script_table: "generate_script_table",
    wait_storyboard: "generate_storyboard",
    generate_storyboard: "generate_storyboard",
    wait_video: "generate_video",
    generate_video: "generate_video",
    pipeline_complete: "pipeline_complete",
  }
  return map[stage] || stage
}

function primaryScriptTable(nodes, edges) {
  const chain = buildActiveChain(nodes, edges)
  if (chain?.script) return chain.script
  const tables = (nodes || []).filter((n) => n.type === "script-table")
  return tables.length ? tables[tables.length - 1] : null
}

function libraryHasEntries(lib) {
  if (!Array.isArray(lib) || lib.length === 0) return false
  return lib.some((e) => e && String(e.name || e.displayName || "").trim())
}

/** 单步是否视为已完成（启发式） */
export function isPipelineStepComplete(stepName, nodes, edges = []) {
  const chain = buildActiveChain(nodes, edges)
  const script = primaryScriptTable(nodes, edges)
  const rows = script?.data?.rows || []

  switch (stepName) {
    case "create_text_note":
      return Boolean(chain?.note) || (nodes || []).some((n) => n.type === "text-note")
    case "start_text_generation":
      return chain?.response?.data?.status === "completed"
    case "generate_outline":
      return Boolean(
        chain?.outline?.data?.scenes?.length
        && !chain.outline.data?.loading
      )
    case "generate_script_table":
      return rows.length > 0 && !script?.data?.loading && !script?.data?.generatingFromOutline
    case "split_shot_beats":
      return rows.length > 0 && rows.every((r) => rowHasBeatPrompts(r))
    case "generate_storyboard":
      return (
        rows.length > 0
        && rows.every((r) => rowDirectImageReady(r) || rowStoryboardReady(r))
      )
    case "generate_video":
      return (
        rows.length > 0
        && rows.every(
          (r) => rowDirectVideoReady(r, nodes) || rowVideoReady(r, nodes)
        )
      )
    case "manage_cast":
      return libraryHasEntries(script?.data?.castLibrary)
    case "manage_scene":
      return libraryHasEntries(script?.data?.sceneLibrary)
    default:
      return false
  }
}

export function getPipelinePanelState(nodes, edges = []) {
  const currentInfer = inferPipelineStage(nodes, edges)
  const currentStep = mapInferStageToManifestStep(currentInfer)
  return { currentInfer, currentStep }
}
