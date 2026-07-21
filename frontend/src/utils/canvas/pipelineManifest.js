/**
 * Pipeline step names — mirror of backend/pipelines/velora_canvas.yaml.
 * Truth source: load_pipeline("velora_canvas") on the backend.
 */

export const PIPELINE_STEP_NAMES = [
  "create_text_note",
  "start_text_generation",
  "generate_outline",
  "generate_script_table",
  "split_shot_beats",
  "generate_storyboard",
  "generate_video",
  "manage_cast",
  "manage_scene",
]

/** @deprecated use EXECUTOR_IDS / toolRegistry — kept for callers */
export const PIPELINE_EXECUTOR_STEP_NAMES = [...PIPELINE_STEP_NAMES]
