/**
 * Frontend tool registry — maps pipeline step → canvas executor method.
 * Truth source for step list: backend/pipelines/velora_canvas.yaml
 * (mirrored in PIPELINE_STEP_NAMES).
 */
import { PIPELINE_STEP_NAMES } from "./pipelineManifest"

/** Stable executor ids aligned with YAML `executor` field. */
export const EXECUTOR_IDS = {
  create_text_note: "canvas.create_text_note",
  start_text_generation: "canvas.start_text_generation",
  generate_outline: "canvas.generate_outline",
  generate_script_table: "canvas.generate_script_table",
  split_shot_beats: "canvas.split_shot_beats",
  generate_storyboard: "canvas.generate_storyboard",
  generate_video: "canvas.generate_video",
  manage_cast: "canvas.manage_cast",
  manage_scene: "canvas.manage_scene",
}

/**
 * Build step → async fn map from a pipeline context object
 * (createTextNote, generateOutline, …).
 */
export function buildExecutorMap(ctx) {
  return {
    create_text_note: (data) => ctx.createTextNote(data),
    start_text_generation: (data) => ctx.startTextGeneration(data),
    generate_outline: (data) => ctx.generateOutline(data),
    generate_script_table: (data) => ctx.generateScriptTable(data),
    split_shot_beats: (data) => ctx.splitShotBeats(data),
    generate_storyboard: (data) => ctx.generateStoryboard(data),
    generate_video: (data) => ctx.generateVideo(data),
    manage_cast: (data) => ctx.manageCast(data),
    manage_scene: (data) => ctx.manageScene(data),
  }
}

export function getExecutor(executorMap, step) {
  return executorMap?.[step] || null
}

export function assertRegistryComplete(executorMap = null) {
  const map = executorMap || EXECUTOR_IDS
  for (const step of PIPELINE_STEP_NAMES) {
    if (!map[step]) {
      throw new Error(`[toolRegistry] missing executor for step: ${step}`)
    }
  }
  return true
}

if (import.meta.env?.DEV) {
  try {
    assertRegistryComplete(EXECUTOR_IDS)
  } catch (err) {
    console.assert(false, err.message)
  }
}
