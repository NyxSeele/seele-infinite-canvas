import {
  rowHasBeatPrompts,
  rowStoryboardReady,
  rowVideoReady,
} from "./scriptTableKeyframes"
import { buildActiveChain, inferPipelineStage, inferProductionStage } from "./agentPipeline"

function findPrimaryScriptTable(nodes, edges = []) {
  const chain = buildActiveChain(nodes, edges)
  if (chain?.script) return chain.script
  const tables = (nodes || []).filter((n) => n.type === "script-table")
  return tables.length > 0 ? tables[tables.length - 1] : null
}

function findNextRowForBeats(scriptNode) {
  return (scriptNode?.data?.rows || []).find((r) => !rowHasBeatPrompts(r)) || null
}

function findNextRowForStoryboard(scriptNode) {
  return (scriptNode?.data?.rows || []).find(
    (r) => rowHasBeatPrompts(r) && !rowStoryboardReady(r)
  ) || null
}

function findNextRowForVideo(scriptNode, nodes = []) {
  return (scriptNode?.data?.rows || []).find(
    (r) => rowStoryboardReady(r) && !rowVideoReady(r, nodes)
  ) || null
}

const STEP_LABELS = {
  // Labels are local for now; future: GET /api/agent/pipeline/velora_canvas
  split_shot_beats: "正在拆分镜头节拍…",
  generate_storyboard: "正在生成分镜图…",
  generate_video: "正在生成镜头视频…",
  create_text_note: "正在创建文本输入卡…",
  start_text_generation: "正在生成剧本文本…",
  generate_outline: "正在生成剧本大纲…",
  generate_script_table: "正在生成分镜表…",
}

const STAGE_TO_STEP = {
  create_text_note: "create_text_note",
  start_text_generation: "start_text_generation",
  generate_outline: "generate_outline",
  generate_script_table: "generate_script_table",
  split_shot_beats: "split_shot_beats",
  generate_storyboard: "generate_storyboard",
  generate_video: "generate_video",
}

function buildPipelineAction(step, scriptNode, row, nodes, edges = []) {
  const data = {}
  const chain = buildActiveChain(nodes, edges)
  if (step === "create_text_note") {
    return null
  }
  if (step === "start_text_generation") {
    const note = chain?.note || nodes.find((n) => n.type === "text-note")
    if (!note) return { error: "画布上没有文本输入卡" }
    data.source_id = note.id
  } else if (step === "generate_outline") {
    const resp = chain?.response || nodes.filter((n) => n.type === "text-response").pop()
    if (!resp) return { error: "请先生成剧本文本" }
    data.text_response_id = resp.id
  } else if (step === "generate_script_table") {
    const outline = chain?.outline || nodes.filter((n) => n.type === "outline").pop()
    if (!outline) return { error: "请先生成剧本大纲" }
    data.outline_id = outline.id
  } else {
    if (!scriptNode) return { error: "画布上还没有分镜表" }
    if (!row) {
      const hints = {
        split_shot_beats: "所有镜头已有节拍",
        generate_storyboard: "没有待出分镜图的镜头",
        generate_video: "没有待生成视频的镜头",
      }
      return { error: hints[step] || "当前没有可执行的步骤" }
    }
    data.script_table_id = scriptNode.id
    data.row_id = row.id
  }

  const shotNum = row?.shotNumber ?? 1
  const summaries = {
    split_shot_beats: `已为镜 ${shotNum} 生成节拍提示词`,
    generate_storyboard: `镜 ${shotNum} 分镜图已提交生成`,
    generate_video: `镜 ${shotNum} 视频已提交生成`,
  }

  return {
    action: { type: "pipeline_step", step, data },
    statusLabel: STEP_LABELS[step] || "正在执行…",
    successSummary: summaries[step] || "本步已执行",
  }
}

function matchProductionCommand(text) {
  const t = text.trim()
  if (/节拍/.test(t) && /(生成|拆分)/.test(t)) return "split_shot_beats"
  if (/分镜图/.test(t) && /(生成|出)/.test(t)) return "generate_storyboard"
  if (/视频/.test(t) && /(生成|出)/.test(t)) return "generate_video"
  return null
}

function inferContinueAction(nodes, edges = []) {
  const scriptNode = findPrimaryScriptTable(nodes, edges)
  if (scriptNode && !scriptNode.data?.loading && !scriptNode.data?.generatingFromOutline) {
    const rows = scriptNode.data?.rows || []
    if (rows.length > 0) {
      const stage = inferProductionStage(scriptNode, nodes)
      const step = STAGE_TO_STEP[stage]
      if (step && !stage.startsWith("wait") && stage !== "pipeline_complete") {
        let row = null
        if (step === "split_shot_beats") row = findNextRowForBeats(scriptNode)
        else if (step === "generate_storyboard") row = findNextRowForStoryboard(scriptNode)
        else if (step === "generate_video") row = findNextRowForVideo(scriptNode, nodes)
        return buildPipelineAction(step, scriptNode, row, nodes, edges)
      }
      if (stage === "pipeline_complete") {
        return { error: "全部分镜制作已完成" }
      }
    }
  }

  const stage = inferPipelineStage(nodes, edges)
  const step = STAGE_TO_STEP[stage]
  if (!step || stage.startsWith("wait") || stage === "pipeline_complete" || stage === "chat_done") {
    return null
  }
  const fallbackScript = findPrimaryScriptTable(nodes, edges)
  let row = null
  if (step === "split_shot_beats") row = findNextRowForBeats(fallbackScript)
  else if (step === "generate_storyboard") row = findNextRowForStoryboard(fallbackScript)
  else if (step === "generate_video") row = findNextRowForVideo(fallbackScript, nodes)
  return buildPipelineAction(step, fallbackScript, row, nodes, edges)
}

/**
 * 短指令解析入口。统一返回 null，交由 LLM 分析画布后再经 manual/auto 确认执行。
 * inferContinueAction / buildPipelineAction 等仍保留，供 LLM 返回 pipeline_step 后由 runPipelineStep 使用。
 * @returns {null}
 */
export function resolveAgentUserCommand(_userInput, _nodes, _edges = []) {
  return null
}

export function getPipelineStepLabel(step) {
  return STEP_LABELS[step] || "正在执行本步…"
}
