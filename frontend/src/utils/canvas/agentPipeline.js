import { flushSync } from "react-dom"
import { addEdge } from "reactflow"
import {
  TEXT_MODES,
  TEXT_NOTE_WIDTH,
  NODE_WIDTHS_MAP,
  makeId,
} from "./nodeHelpers"
import { sortNodesByWorkflow } from "./organizeCanvasNodes"
import { organizeCanvasNodes } from "./organizeCanvasNodes"
import { normalizeTextResponseNode } from "./nodeNormalize"
import { parseTargetDurationSec } from "./videoDurationIntent"
import { getCanvasPipelineBusy, waitForNodeCondition } from "./canvasPipelineState"
import { findScriptTableForOutline } from "./scriptTableSegments"
import { splitShotBeats } from "./scriptPromptApi"
import {
  makeCastRefId,
  normalizeCastLibrary,
  normalizeCastLibraryEntry,
} from "./castLibrary"
import { touchLibraryById } from "./libraryUsage"
import {
  makeSceneRefId,
  normalizeSceneLibrary,
  normalizeSceneLibraryEntry,
} from "./sceneLibrary"
import {
  applyBeatsToBeatCard,
  beatCardHasBeatPrompts,
  beatCardStoryboardReady,
} from "./scriptBeatCard"
import {
  applyBeatsToRow,
  rowDirectImageReady,
  rowDirectVideoReady,
  rowHasBeatPrompts,
  rowStoryboardReady,
  rowVideoReady,
} from "./scriptTableKeyframes"
import {
  isOutlineLoadingStale,
  outlineLoadingPatch,
  parseOutlineStructureResponse,
  applyOutlineStructureToNodes,
  postOutlineStructure,
} from "./outlineStructureApi"

const NODE_WIDTH_FALLBACK = {
  "text-note": TEXT_NOTE_WIDTH,
  "text-response": 500,
  outline: 540,
  "script-table": 1120,
  "image-gen": 300,
  "video-gen": 440,
}

const PIPELINE_GAP = 80
const OUTLINE_OFFSET_X = 520

function findLinkedOutline(nodes, edges, responseId) {
  const linkedByEdge = edges.find(
    (e) =>
      e.source === responseId
      && nodes.some((n) => n.id === e.target && n.type === "outline")
  )?.target
  if (linkedByEdge) {
    return nodes.find((n) => n.id === linkedByEdge) || null
  }
  return nodes.find(
    (n) => n.type === "outline" && n.data?.linkedSourceId === responseId
  ) || null
}

function resolveOutlineNodeId(nodes, edges, { preferredId, responseId }) {
  if (nodes.some((n) => n.id === preferredId && n.type === "outline")) {
    return preferredId
  }
  const linked = findLinkedOutline(nodes, edges, responseId)
  return linked?.id || preferredId
}

function patchOutlineNode(setNodes, outlineId, patch) {
  flushSync(() => {
    setNodes((ns) =>
      ns.map((n) => {
        if (n.id !== outlineId || n.type !== "outline") return n
        return { ...n, data: { ...n.data, ...patch } }
      })
    )
  })
}

function nodeWidth(node) {
  return (
    node.width
    ?? node.style?.width
    ?? NODE_WIDTH_FALLBACK[node.type]
    ?? 320
  )
}

/** 按工作流顺序在末尾放置新节点，避免叠在一起 */
export function computeAgentNodePosition(nodes, edges, flowType) {
  const ordered = sortNodesByWorkflow(nodes, edges || [])
  if (ordered.length === 0) return { x: 120, y: 160 }

  const last = ordered[ordered.length - 1]
  const w = nodeWidth(last)
  const nextW = NODE_WIDTH_FALLBACK[flowType] || 400

  if (flowType === "outline" && last.type === "text-response") {
    return {
      x: last.position.x + OUTLINE_OFFSET_X,
      y: last.position.y,
    }
  }
  if (flowType === "script-table" && last.type === "outline") {
    return {
      x: last.position.x + 560,
      y: last.position.y,
    }
  }
  if (flowType === "text-response" && last.type === "text-note") {
    return {
      x: last.position.x + TEXT_NOTE_WIDTH + PIPELINE_GAP,
      y: last.position.y,
    }
  }

  return {
    x: last.position.x + w + PIPELINE_GAP,
    y: last.position.y,
  }
}

export function applyAgentCanvasLayout(setNodes, getEdges) {
  const edges = getEdges()
  setNodes((ns) => organizeCanvasNodes(ns, edges))
}

function chainSortKey(nodeId) {
  const nid = (nodeId || "").toString()
  if (nid.startsWith("agent_")) {
    const parts = nid.split("_")
    if (parts[1] && /^\d+$/.test(parts[1])) return Number(parts[1])
  }
  return 0
}

function buildEdgeMap(edges = []) {
  const map = {}
  for (const e of edges) {
    if (!e?.source) continue
    if (!map[e.source]) map[e.source] = []
    map[e.source].push(e.target)
  }
  return map
}

function followEdgeTarget(sourceId, edgeMap, nodesById, flowType) {
  if (!sourceId) return null
  for (const tid of edgeMap[sourceId] || []) {
    const node = nodesById[tid]
    if (node?.type === flowType) return node
  }
  return null
}

/** 按 text-note 连边追踪最新一条独立创作链路 */
export function buildActiveChain(nodes, edges = []) {
  const edgeMap = buildEdgeMap(edges)
  const nodesById = Object.fromEntries((nodes || []).map((n) => [n.id, n]))
  const notes = (nodes || []).filter((n) => n.type === "text-note")
  const responses = (nodes || []).filter((n) => n.type === "text-response")
  const outlines = (nodes || []).filter((n) => n.type === "outline")
  const scripts = (nodes || []).filter((n) => n.type === "script-table")

  const chains = notes.map((note) => {
    const chain = { note }
    const resp =
      followEdgeTarget(note.id, edgeMap, nodesById, "text-response")
      || responses.find((r) => r.data?.sourceNodeId === note.id)
    if (resp) chain.response = resp

    const outline =
      (resp && followEdgeTarget(resp.id, edgeMap, nodesById, "outline"))
      || (resp && outlines.find((o) => o.data?.linkedSourceId === resp.id))
      || outlines.find((o) => o.data?.linkedSourceId === note.id)
      || followEdgeTarget(note.id, edgeMap, nodesById, "outline")
    if (outline) chain.outline = outline

    const script =
      (outline && followEdgeTarget(outline.id, edgeMap, nodesById, "script-table"))
      || (outline && scripts.find((s) => s.data?.sourceOutlineId === outline.id))
      || scripts.find((s) => s.data?.sourceOutlineId === outline?.id)
    if (script) chain.script = script

    return chain
  })

  chains.sort((a, b) => chainSortKey(b.note?.id) - chainSortKey(a.note?.id))
  return chains[0] || null
}

function inferStageFromChain(chain, nodes) {
  if (!chain?.note) return "create_text_note"
  const { note, response, outline, script } = chain
  if (!response) return "start_text_generation"
  if (response.data?.status === "generating") return "wait_text_generation"
  if (response.data?.status === "failed") return "start_text_generation"
  if (note.data?.textMode !== TEXT_MODES.SCREENPLAY) return "chat_done"
  if (!outline) return "generate_outline"
  if (outline.data?.loading) return "wait_outline"
  if (!Array.isArray(outline.data?.scenes) || outline.data.scenes.length === 0) {
    return "generate_outline"
  }
  if (!script) return "generate_script_table"
  if (script.data?.loading || script.data?.generatingFromOutline) return "wait_script_table"
  const rows = script.data?.rows || []
  if (rows.length > 0) return inferProductionStage(script, nodes)
  return "wait_script_table"
}

/** 根据画布推断下一推荐步骤（供调试；主逻辑在后端 Prompt） */
export function inferPipelineStage(nodes, edges = []) {
  const chain = buildActiveChain(nodes, edges)
  if (chain) return inferStageFromChain(chain, nodes)

  const scripts = nodes.filter((n) => n.type === "script-table")
  for (let i = scripts.length - 1; i >= 0; i -= 1) {
    const st = scripts[i]
    if (st.data?.loading || st.data?.generatingFromOutline) {
      return "wait_script_table"
    }
    const rows = st.data?.rows || []
    if (rows.length > 0) {
      return inferProductionStage(st, nodes)
    }
  }

  if ((nodes || []).filter((n) => n.type === "text-note").length === 0) {
    return "create_text_note"
  }
  return "start_text_generation"
}

function rowImageGenerating(row) {
  if (!row) return false
  if (row.directStatus === "generating" || row.status === "generating") return true
  const kfs = Array.isArray(row.keyframes) ? row.keyframes : []
  return kfs.some((kf) => kf?.status === "generating")
}

function rowVideoGenerating(row, allNodes = []) {
  if (!row) return false
  const vidId = row.directVideoGenNodeId || row.videoGenNodeId
  if (!vidId) return false
  if (rowDirectVideoReady(row, allNodes) || rowVideoReady(row, allNodes)) return false
  return allNodes.some(
    (vn) =>
      vn.id === vidId
      && vn.type === "video-gen"
      && (vn.data?.status === "generating" || vn.data?.status === "pending")
  )
}

/** 按镜号单线程：出图→视频；生成中 wait；当前镜视频完成前不进下一镜 */
export function inferProductionStage(scriptNode, allNodes = []) {
  const rows = scriptNode?.data?.rows || []
  if (rows.length === 0) return "wait_script_table"
  for (const row of rows) {
    if (rowImageGenerating(row)) return "wait_storyboard"
    if (rowVideoGenerating(row, allNodes)) return "wait_video"
    if (!rowDirectImageReady(row)) return "generate_storyboard"
    if (!rowDirectVideoReady(row, allNodes) && !rowVideoReady(row, allNodes)) {
      return "generate_video"
    }
  }
  return "pipeline_complete"
}

function findPrimaryScriptTable(nodes, edges = []) {
  const chain = buildActiveChain(nodes, edges)
  if (chain?.script) return chain.script
  const tables = nodes.filter((n) => n.type === "script-table")
  if (tables.length === 0) return null
  return tables[tables.length - 1]
}

function resolveScriptTableRow(scriptNode, rowIdOrData, nodes = []) {
  const rows = scriptNode?.data?.rows || []
  const data = rowIdOrData && typeof rowIdOrData === "object" ? rowIdOrData : null
  const rowId = data
    ? (data.row_id || data.rowId || null)
    : rowIdOrData
  if (rowId) return rows.find((r) => r.id === rowId) || null
  const shotNum = data?.shot_number ?? data?.shotNumber
  if (shotNum != null && shotNum !== "") {
    const hit = rows.find((r) => String(r.shotNumber) === String(shotNum))
    if (hit) return hit
  }
  return (
    findNextRowForStoryboard(scriptNode, nodes)
    || findNextRowForVideo(scriptNode, nodes)
    || rows[0]
    || null
  )
}

function findNextRowForBeats(scriptNode, allNodes = []) {
  for (const row of scriptNode?.data?.rows || []) {
    if (rowImageGenerating(row) || rowVideoGenerating(row, allNodes)) return null
    if (!row.beatCardNodeId) return row
    const card = allNodes.find((n) => n.id === row.beatCardNodeId)
    if (card && !beatCardHasBeatPrompts(card.data)) return row
    if (!rowDirectImageReady(row)) return null
    if (!rowDirectVideoReady(row, allNodes) && !rowVideoReady(row, allNodes)) return null
  }
  return null
}

function findNextRowForStoryboard(scriptNode, allNodes = []) {
  for (const r of scriptNode?.data?.rows || []) {
    if (rowImageGenerating(r) || rowVideoGenerating(r, allNodes)) return null
    if (!rowDirectImageReady(r)) return r
    if (!rowDirectVideoReady(r, allNodes) && !rowVideoReady(r, allNodes)) return null
  }
  return null
}

function findNextRowForVideo(scriptNode, nodes = []) {
  for (const r of scriptNode?.data?.rows || []) {
    if (rowImageGenerating(r) || rowVideoGenerating(r, nodes)) return null
    if (!rowDirectImageReady(r)) return null
    if (!rowDirectVideoReady(r, nodes) && !rowVideoReady(r, nodes)) return r
  }
  return null
}

function edgesBetween(nodes, a, b) {
  return false
}

/**
 * 执行单步 pipeline_step
 * @returns {{ ok: boolean, nodeIds?: string[], error?: string }}
 */
export async function executeAgentPipelineStep(action, ctx) {
  const step = action.step
  const data = action.data || {}
  const nodes = typeof ctx?.getNodes === "function" ? ctx.getNodes() : []
  const busy = getCanvasPipelineBusy(nodes)
  if (busy.busy) {
    return { ok: false, error: busy.reason || "当前步骤仍在生成中，请稍候" }
  }

  switch (step) {
    case "create_text_note":
      return ctx.createTextNote(data)
    case "start_text_generation":
      return ctx.startTextGeneration(data)
    case "generate_outline":
      return ctx.generateOutline(data)
    case "generate_script_table":
      return ctx.generateScriptTable(data)
    case "split_shot_beats":
      return ctx.splitShotBeats(data)
    case "generate_storyboard":
      return ctx.generateStoryboard(data)
    case "generate_video":
      return ctx.generateVideo(data)
    case "manage_cast":
      return ctx.manageCast(data)
    case "manage_scene":
      return ctx.manageScene(data)
    default:
      return { ok: false, error: `未知链路步骤：${step}` }
  }
}

export function createAgentPipelineContext({
  getNodes,
  getEdges,
  setNodes,
  setEdges,
  buildData,
  buildOutlineData,
  bumpZIndex,
  runTextGeneration,
  onGenerateScriptTable,
  getDefaultTextModelId,
  getDefaultImageModelId,
  getDefaultVideoModelId,
  patchScriptTableRow,
  runScriptTableRowGenerate,
  runScriptTableRowVideoGenerate,
  createBeatCardForRow,
  patchBeatCard,
  readOnlyRef,
  signal,
}) {
  const waitOpts = (opts = {}) => ({ ...opts, signal })
  const createTextNote = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const prompt = (data.prompt || data.content || "").trim()
    if (!prompt) return { ok: false, error: "缺少文本输入内容" }

    const intent = (data.intent || "screenplay").toLowerCase()
    const textMode = intent === "chat" ? TEXT_MODES.CHAT : TEXT_MODES.SCREENPLAY
    const nodes = getNodes()
    const edges = getEdges()
    const position =
      data.position || computeAgentNodePosition(nodes, edges, "text-note")
    const id = makeId("text-note")
    const z = bumpZIndex?.() ?? 1

    setNodes((ns) => [
      ...ns,
      {
        id,
        type: "text-note",
        position,
        zIndex: z,
        style: { zIndex: z },
        data: buildData({
          label: data.label || "文本",
          prompt,
          content: prompt,
          textMode,
          zIndex: z,
        }),
      },
    ])
    return { ok: true, nodeIds: [id] }
  }

  const startTextGeneration = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const sourceId = data.source_id || data.text_note_id
    if (!sourceId) return { ok: false, error: "缺少 text-note id" }

    const note = getNodes().find((n) => n.id === sourceId)
    if (!note || note.type !== "text-note") {
      return { ok: false, error: "找不到文本输入卡" }
    }

    const modelId = data.model_id || getDefaultTextModelId?.()
    if (!modelId) return { ok: false, error: "未配置文本模型" }

    const prompt = (data.prompt || note.data?.prompt || note.data?.content || "").trim()
    if (!prompt) return { ok: false, error: "文本输入为空" }

    const notePrompt = (note.data?.prompt || note.data?.content || "").trim()
    const requestedPrompt = (data.prompt || "").trim()
    const existingResponse = getNodes().find(
      (n) => n.type === "text-response" && n.data?.sourceNodeId === sourceId
    )
    if (existingResponse) {
      const status = existingResponse.data?.status
      if (status === "completed") {
        if (requestedPrompt && requestedPrompt !== notePrompt) {
          return {
            ok: false,
            error: "该文本输入卡已有生成结果，新主题请先 create_text_note 新建节点",
          }
        }
        return { ok: true, nodeIds: [sourceId, existingResponse.id] }
      }
      if (status === "generating") {
        const waitResult = await waitForNodeCondition(
          getNodes,
          existingResponse.id,
          (node) => {
            const s = node.data?.status
            if (s === "generating") return { done: false }
            if (s === "failed") {
              return {
                done: true,
                ok: false,
                error: node.data?.error || "剧本文本生成失败",
              }
            }
            if (s === "completed") {
              const text = (node.data?.content || "").trim()
              if (!text) {
                return { done: true, ok: false, error: "剧本文本生成完成但内容为空，请重试" }
              }
              return { done: true, ok: true, nodeIds: [sourceId, existingResponse.id] }
            }
            return { done: false }
          },
          waitOpts({
            timeoutMs: 180000,
            timeoutError: "剧本文本生成超时，请稍后再点「继续」",
            missingError: "文本回复节点未出现，请重试",
          })
        )
        return waitResult
      }
      if (status === "failed") {
        if (requestedPrompt && requestedPrompt !== notePrompt) {
          return {
            ok: false,
            error: "该文本输入卡已有生成结果，新主题请先 create_text_note 新建节点",
          }
        }
      } else if (requestedPrompt && requestedPrompt !== notePrompt) {
        return {
          ok: false,
          error: "该文本输入卡已有生成结果，新主题请先 create_text_note 新建节点",
        }
      }
      const reuseId = await runTextGeneration(
        sourceId,
        { modelId, prompt, count: 1 },
        existingResponse.id
      )
      if (!reuseId) {
        return { ok: false, error: "文本生成启动失败" }
      }
      const waitReuse = await waitForNodeCondition(
        getNodes,
        reuseId,
        (node) => {
          const s = node.data?.status
          if (s === "generating") return { done: false }
          if (s === "failed") {
            return {
              done: true,
              ok: false,
              error: node.data?.error || "剧本文本生成失败",
            }
          }
          if (s === "completed") {
            const text = (node.data?.content || "").trim()
            if (!text) {
              return { done: true, ok: false, error: "剧本文本生成完成但内容为空，请重试" }
            }
            return { done: true, ok: true, nodeIds: [sourceId, reuseId] }
          }
          return { done: false }
        },
        waitOpts({
          timeoutMs: 180000,
          timeoutError: "剧本文本生成超时，请稍后再点「继续」",
          missingError: "文本回复节点未出现，请重试",
        })
      )
      return waitReuse
    }

    const responseId = await runTextGeneration(sourceId, {
      modelId,
      prompt,
      count: 1,
    })
    if (!responseId) {
      return { ok: false, error: "文本生成启动失败" }
    }

    const waitResult = await waitForNodeCondition(
      getNodes,
      responseId,
      (node) => {
        const status = node.data?.status
        if (status === "generating") return { done: false }
        if (status === "failed") {
          return {
            done: true,
            ok: false,
            error: node.data?.error || "剧本文本生成失败",
          }
        }
        if (status === "completed") {
          const text = (node.data?.content || "").trim()
          if (!text) {
            return { done: true, ok: false, error: "剧本文本生成完成但内容为空，请重试" }
          }
          return { done: true, ok: true, nodeIds: [sourceId, responseId] }
        }
        return { done: false }
      },
      waitOpts({ timeoutMs: 180000, timeoutError: "剧本文本生成超时，请稍后再点「继续」", missingError: "文本回复节点未出现，请重试" })
    )
    return waitResult
  }

  const generateOutline = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const responseId = data.text_response_id || data.source_id
    const responseNode = getNodes().find((n) => n.id === responseId)
    if (!responseNode || responseNode.type !== "text-response") {
      return { ok: false, error: "找不到已完成的文本回复卡" }
    }
    if (responseNode.data?.status === "generating") {
      return { ok: false, error: "文本仍在生成中，请稍后再继续" }
    }

    const edges = getEdges()
    let existingOutline = findLinkedOutline(getNodes(), edges, responseId)
    if (existingOutline?.data?.loading) {
      if (!isOutlineLoadingStale(existingOutline)) {
        return { ok: false, error: "大纲正在生成中，请稍候" }
      }
      patchOutlineNode(setNodes, existingOutline.id, {
        loading: false,
        outlineLoadingStartedAt: undefined,
        error: null,
      })
      existingOutline = {
        ...existingOutline,
        data: {
          ...existingOutline.data,
          loading: false,
          outlineLoadingStartedAt: undefined,
          error: null,
        },
      }
    }

    const screenplayText = (responseNode.data?.content || "").trim()
    if (!screenplayText) {
      return { ok: false, error: "文本回复内容为空，无法生成大纲" }
    }

    const sourceId = responseNode.data?.sourceNodeId
    const sourceNote = sourceId ? getNodes().find((n) => n.id === sourceId) : null
    const sourceIdea = (sourceNote?.data?.prompt || responseNode.data?.prompt || "").trim()
    const targetVideoDurationSec =
      parseTargetDurationSec(sourceIdea || screenplayText) ?? undefined

    const reuseOutline =
      existingOutline
      && (!Array.isArray(existingOutline.data?.scenes) || existingOutline.data.scenes.length === 0)

    const outlineId = reuseOutline ? existingOutline.id : makeId("outline")
    const outlineIdRef = { current: outlineId }
    const z = reuseOutline
      ? (existingOutline.zIndex ?? existingOutline.data?.zIndex ?? bumpZIndex?.() ?? 1)
      : (bumpZIndex?.() ?? 1)
    const position = reuseOutline
      ? existingOutline.position
      : computeAgentNodePosition(getNodes(), edges, "outline")

    const outlinePatch = buildOutlineData(
      outlineLoadingPatch({
        title: "",
        scenes: [],
        versions: [],
        selectedVersionIndex: 0,
        error: null,
        truncated: false,
        linkedSourceId: responseId,
        zIndex: z,
      })
    )

    if (reuseOutline) {
      patchOutlineNode(setNodes, outlineId, outlinePatch)
    } else {
      flushSync(() => {
        setNodes((ns) => [
          ...ns,
          {
            id: outlineId,
            type: "outline",
            position,
            width: NODE_WIDTHS_MAP.outline,
            zIndex: z,
            draggable: true,
            data: outlinePatch,
            style: { zIndex: z, width: NODE_WIDTHS_MAP.outline },
          },
        ])
        setEdges((es) =>
          addEdge(
            {
              id: `e-${responseId}-${outlineId}-${Date.now()}`,
              source: responseId,
              sourceHandle: "src-right",
              target: outlineId,
              targetHandle: "tgt",
              type: "ghost",
              animated: false,
            },
            es
          )
        )
      })
    }

    const waitCreate = await waitForNodeCondition(
      getNodes,
      outlineId,
      (node) => {
        if (!node || node.type !== "outline") return { done: false }
        if (node.data?.loading) return { done: true, ok: true }
        return { done: false }
      },
      waitOpts({
        timeoutMs: 8000,
        missingError: "大纲节点创建失败，请重试",
        timeoutError: "大纲节点创建失败，请重试",
      })
    )
    if (!waitCreate.ok) {
      return { ok: false, error: waitCreate.error || "大纲节点创建失败，请重试" }
    }

    try {
      const res = await postOutlineStructure({
        text: screenplayText,
        target_duration_sec: targetVideoDurationSec ?? null,
        source_idea: sourceIdea || screenplayText,
      })
      const outlineFields = parseOutlineStructureResponse(res, {
        sourceIdea: sourceIdea || screenplayText,
        targetVideoDurationSec,
      })
      if (!outlineFields.scenes.length) {
        patchOutlineNode(setNodes, outlineIdRef.current, {
          loading: false,
          outlineLoadingStartedAt: undefined,
          error: "大纲服务返回为空，请检查剧本文本后重试",
        })
        return { ok: false, error: "大纲服务返回为空，请检查剧本文本后重试" }
      }

      const nodesAfter = getNodes()
      const edgesAfter = getEdges()
      const targetOutlineId = resolveOutlineNodeId(nodesAfter, edgesAfter, {
        preferredId: outlineIdRef.current,
        responseId,
      })

      const applied = applyOutlineStructureToNodes(setNodes, {
        preferredOutlineId: outlineIdRef.current,
        responseId,
        outlineNodeId: targetOutlineId,
        outlineFields: {
          ...outlineFields,
          linkedSourceId: responseId,
        },
      })
      if (!applied.ok) {
        return applied
      }
      return { ok: true, nodeIds: applied.nodeIds }
    } catch (err) {
      const msg =
        err.response?.data?.detail || err.message || "大纲生成失败"
      patchOutlineNode(setNodes, outlineIdRef.current, {
        loading: false,
        outlineLoadingStartedAt: undefined,
        error: typeof msg === "string" ? msg : "大纲生成失败",
      })
      return { ok: false, error: typeof msg === "string" ? msg : "大纲生成失败" }
    }
  }

  const generateScriptTable = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const outlineId = data.outline_id || data.source_id
    if (!outlineId) return { ok: false, error: "缺少大纲节点 id" }

    const outlineNode = getNodes().find((n) => n.id === outlineId && n.type === "outline")
    if (!outlineNode) return { ok: false, error: "找不到大纲节点" }
    if (outlineNode.data?.loading) {
      return { ok: false, error: "大纲仍在生成中，请稍候" }
    }
    const scenes = outlineNode.data?.scenes
    if (!Array.isArray(scenes) || scenes.length === 0) {
      return { ok: false, error: "大纲无场景内容，请先生成大纲" }
    }

    let scriptTableId = findScriptTableForOutline(outlineId, getNodes(), getEdges())
    if (scriptTableId) {
      const existing = getNodes().find((n) => n.id === scriptTableId)
      if (existing && !existing.data?.loading && !existing.data?.generatingFromOutline) {
        const rows = existing.data?.rows || []
        const segments = existing.data?.segments || []
        if (rows.length > 0 || segments.length > 0) {
          return { ok: true, nodeIds: [outlineId, scriptTableId] }
        }
      }
    }

    try {
      await onGenerateScriptTable?.(outlineId)

      if (!scriptTableId) {
        scriptTableId = findScriptTableForOutline(outlineId, getNodes(), getEdges())
      }
      if (!scriptTableId) {
        return { ok: false, error: "分镜表节点未创建" }
      }

      const waitResult = await waitForNodeCondition(
        getNodes,
        scriptTableId,
        (node) => {
          if (!node || node.type !== "script-table") return { done: false }
          if (node.data?.loading || node.data?.generatingFromOutline) return { done: false }
          if (node.data?.error) {
            return {
              done: true,
              ok: false,
              error: node.data.error || "分镜表生成失败",
            }
          }
          const rows = node.data?.rows
          const segments = node.data?.segments
          const hasRows = Array.isArray(rows) && rows.length > 0
          const hasSegments = Array.isArray(segments) && segments.length > 0
          if (!hasRows && !hasSegments) {
            return { done: true, ok: false, error: "分镜表生成完成但内容为空" }
          }
          return { done: true, ok: true, nodeIds: [outlineId, scriptTableId] }
        },
        waitOpts({ timeoutMs: 180000, timeoutError: "分镜表生成超时，请稍后再点「继续」" })
      )
      return waitResult
    } catch (err) {
      return {
        ok: false,
        error: err?.message || "分镜表生成失败",
      }
    }
  }

  const splitShotBeatsStep = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const scriptTableId = data.script_table_id || data.source_id
    let scriptNode = scriptTableId
      ? getNodes().find((n) => n.id === scriptTableId && n.type === "script-table")
      : findPrimaryScriptTable(getNodes(), getEdges())
    if (!scriptNode) return { ok: false, error: "找不到分镜表节点" }
    const tableId = scriptNode.id

    if (scriptNode.data?.loading) {
      return { ok: false, error: "分镜表仍在生成中，请稍候" }
    }

    const row = data.row_id
      ? resolveScriptTableRow(scriptNode, data, getNodes())
      : findNextRowForBeats(scriptNode, getNodes())
    if (!row) return { ok: false, error: "没有需要拆分节拍的镜头" }

    let beatCardId = row.beatCardNodeId
    if (!beatCardId) {
      beatCardId = createBeatCardForRow?.(tableId, row.id)
    }
    if (!beatCardId) return { ok: false, error: "无法创建节拍卡片" }

    const beatNode = getNodes().find((n) => n.id === beatCardId)
    if (beatNode && beatCardHasBeatPrompts(beatNode.data) && !data.resplit) {
      return { ok: false, error: `镜 ${row.shotNumber ?? 1} 已有节拍，请打开节拍卡片继续` }
    }

    const castLibrary = scriptNode.data?.castLibrary || []
    const sceneLibrary = scriptNode.data?.sceneLibrary || []
    const res = await splitShotBeats(row, castLibrary, { useLlm: true, sceneLibrary })
    if (!res?.beats?.length) {
      return { ok: false, error: "节拍拆分失败，请重试" }
    }

    const updated = applyBeatsToBeatCard(beatNode?.data || {}, res.beats)
    patchBeatCard?.(beatCardId, {
      keyframes: updated.keyframes,
      beatsSplitAt: updated.beatsSplitAt,
      beatsSplitSource: res.source || "llm",
      status: updated.status,
    })

    const waitResult = await waitForNodeCondition(
      getNodes,
      beatCardId,
      (node) => {
        if (!node || node.type !== "script-beat-card") return { done: false }
        if (beatCardHasBeatPrompts(node.data)) {
          return { done: true, ok: true, nodeIds: [tableId, beatCardId] }
        }
        return { done: false }
      },
      waitOpts({ timeoutMs: 30000, timeoutError: "节拍写入超时，请重试" })
    )
    return waitResult
  }

  const generateStoryboard = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const scriptTableId = data.script_table_id || data.source_id
    let scriptNode = scriptTableId
      ? getNodes().find((n) => n.id === scriptTableId && n.type === "script-table")
      : findPrimaryScriptTable(getNodes(), getEdges())
    if (!scriptNode) return { ok: false, error: "找不到分镜表节点" }
    const tableId = scriptNode.id

    const row = data.row_id
      ? resolveScriptTableRow(scriptNode, data, getNodes())
      : findNextRowForStoryboard(scriptNode, getNodes())
    if (!row) return { ok: false, error: "没有待出图的镜头" }
    if (rowDirectImageReady(row)) {
      return { ok: true, nodeIds: [tableId] }
    }

    const modelId = data.model_id || scriptNode.data?.modelId || getDefaultImageModelId?.()
    if (!modelId) return { ok: false, error: "未配置图像模型，请在分镜表选择模型" }

    const started = await runScriptTableRowGenerate?.(tableId, row.id, { modelId })
    if (!started?.ok) {
      return { ok: false, error: `镜 ${row.shotNumber ?? 1} 出图启动失败` }
    }

    const triggerAt = Number(started?.triggerAt) || Date.now()
    const waitResult = await waitForNodeCondition(
      getNodes,
      tableId,
      (node) => {
        const r = (node.data?.rows || []).find((x) => x.id === row.id)
        if (!r) return { done: false }
        const imgId = r.directImageGenNodeId
        const imgNode = imgId
          ? getNodes().find((n) => n.id === imgId && n.type === "image-gen")
          : null
        const imgStatus = imgNode?.data?.status
        if (r.directStatus === "generating" || imgStatus === "pending" || imgStatus === "generating") {
          return { done: false }
        }
        if (r.directStatus === "failed" || imgStatus === "failed" || imgStatus === "error") {
          return {
            done: true,
            ok: false,
            error: r.error || imgNode?.data?.error || `镜 ${row.shotNumber ?? 1} 出图失败`,
          }
        }
        if (rowDirectImageReady(r)) {
          const completedAt = Number(imgNode?.data?.completedAt) || 0
          if (triggerAt > 0 && (!completedAt || completedAt <= triggerAt)) {
            return { done: false }
          }
          return { done: true, ok: true, nodeIds: [tableId] }
        }
        return { done: false }
      },
      waitOpts({
        timeoutMs: 300000,
        timeoutError: `镜 ${row.shotNumber ?? 1} 分镜图生成超时，请稍后再点「继续」`,
      })
    )
    return waitResult
  }

  const generateVideo = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const scriptTableId = data.script_table_id || data.source_id
    let scriptNode = scriptTableId
      ? getNodes().find((n) => n.id === scriptTableId && n.type === "script-table")
      : findPrimaryScriptTable(getNodes(), getEdges())
    if (!scriptNode) return { ok: false, error: "找不到分镜表节点" }
    const tableId = scriptNode.id

    const row = data.row_id
      ? resolveScriptTableRow(scriptNode, data, getNodes())
      : findNextRowForVideo(scriptNode, getNodes())
    if (!row) return { ok: false, error: "没有待生成视频的镜头" }
    if (!rowDirectImageReady(row)) {
      return { ok: false, error: `镜 ${row.shotNumber ?? 1} 须先完成出图` }
    }

    const videoModelId =
      data.video_model_id || scriptNode.data?.videoModelId || getDefaultVideoModelId?.()
    if (!videoModelId) {
      return { ok: false, error: "未配置视频模型，请在分镜表选择视频模型" }
    }

    const started = await runScriptTableRowVideoGenerate?.(tableId, row.id, {
      videoModelId,
      lane: "direct",
      direct: true,
    })
    if (!started?.ok && !started?.videoGenId) {
      return { ok: false, error: `镜 ${row.shotNumber ?? 1} 视频启动失败` }
    }

    let videoGenId = started?.videoGenId || null
    if (!videoGenId) {
      // setNodes 异步：短轮询等待 directVideoGenNodeId
      const deadline = Date.now() + 3000
      while (!videoGenId && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 50))
        const rowAfter = getNodes()
          .find((n) => n.id === tableId)
          ?.data?.rows?.find((r) => r.id === row.id)
        videoGenId = rowAfter?.directVideoGenNodeId || null
      }
    }
    if (!videoGenId) {
      return { ok: false, error: "视频节点未创建" }
    }

    const triggerAt = Number(started?.triggerAt) || Date.now()
    const waitResult = await waitForNodeCondition(
      getNodes,
      videoGenId,
      (node) => {
        if (!node || node.type !== "video-gen") return { done: false }
        const status = node.data?.status
        const pending = node.data?.pendingTrigger
        // 复用旧节点时：pendingTrigger 清空后、尚未进入 generating 前，勿把旧 completed 当成功
        if (pending != null) return { done: false }
        if (status === "generating" || status === "pending") return { done: false }
        if (status === "completed") {
          const completedAt = Number(node.data?.completedAt) || 0
          if (!completedAt || completedAt <= triggerAt) return { done: false }
          return { done: true, ok: true, nodeIds: [tableId, videoGenId] }
        }
        if (status === "failed" || status === "error") {
          return {
            done: true,
            ok: false,
            error: node.data?.error || `镜 ${row.shotNumber ?? 1} 视频生成失败`,
          }
        }
        return { done: false }
      },
      waitOpts({
        timeoutMs: 300000,
        timeoutError: `镜 ${row.shotNumber ?? 1} 视频生成超时，请稍后再点「继续」`,
        missingError: "视频节点未出现，请重试",
      })
    )
    return waitResult
  }

  const manageCast = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const scriptTableId = data.script_table_id || data.node_id || data.source_id
    let scriptNode = scriptTableId
      ? getNodes().find((n) => n.id === scriptTableId && n.type === "script-table")
      : null
    if (!scriptNode) {
      scriptNode = findPrimaryScriptTable(getNodes(), getEdges())
    }
    if (!scriptNode) return { ok: false, error: "找不到分镜表节点" }

    const castItems = Array.isArray(data.cast_items) ? data.cast_items : []
    if (castItems.length === 0) {
      return { ok: false, error: "manage_cast 缺少 cast_items" }
    }

    const currentLib = normalizeCastLibrary(scriptNode.data?.castLibrary || [], {
      requireImage: false,
    })
    const nextLib = [...currentLib]

    for (const item of castItems) {
      const name = String(item?.name || "").trim()
      if (!name) continue
      const itemAction = String(item?.action || "add").toLowerCase()
      const castType = "character"

      if (itemAction === "update") {
        const idx = nextLib.findIndex(
          (c) => c.name.toLowerCase() === name.toLowerCase()
        )
        if (idx >= 0) {
          nextLib[idx] = {
            ...nextLib[idx],
            ...(item.description != null
              ? { description: String(item.description).trim() }
              : {}),
            ...(item.type ? { type: castType } : {}),
            ...(item.imageUrl || item.image_url
              ? { imageUrl: item.imageUrl || item.image_url, pendingImage: false }
              : {}),
          }
        }
        continue
      }

      const exists = nextLib.some(
        (c) => c.name.toLowerCase() === name.toLowerCase()
      )
      if (exists) continue

      const entry = normalizeCastLibraryEntry({
        id: makeCastRefId(),
        name,
        type: castType,
        description: item.description || "",
        imageUrl: item.imageUrl || item.image_url || null,
      })
      if (entry) nextLib.push(entry)
    }

    const tableId = scriptNode.id
    flushSync(() => {
      setNodes((ns) =>
        ns.map((n) =>
          n.id === tableId
            ? { ...n, data: { ...n.data, castLibrary: nextLib } }
            : n
        )
      )
    })

    const castPending = nextLib
      .filter((c) => !c.imageUrl)
      .map((c) => ({ id: c.id, name: c.name, type: c.type }))

    return {
      ok: true,
      nodeIds: [tableId],
      castPending,
      scriptTableId: tableId,
    }
  }

  const manageScene = async (data) => {
    if (readOnlyRef?.current) return { ok: false, error: "只读模式" }
    const scriptTableId = data.script_table_id || data.node_id || data.source_id
    let scriptNode = scriptTableId
      ? getNodes().find((n) => n.id === scriptTableId && n.type === "script-table")
      : null
    if (!scriptNode) {
      scriptNode = findPrimaryScriptTable(getNodes(), getEdges())
    }
    if (!scriptNode) return { ok: false, error: "找不到分镜表节点" }

    const sceneItems = Array.isArray(data.scene_items) ? data.scene_items : []
    if (sceneItems.length === 0) {
      return { ok: false, error: "manage_scene 缺少 scene_items" }
    }

    const currentLib = normalizeSceneLibrary(scriptNode.data?.sceneLibrary || [], {
      requireImage: false,
    })
    const nextLib = [...currentLib]

    for (const item of sceneItems) {
      const name = String(item?.name || "").trim()
      if (!name) continue
      const itemAction = String(item?.action || "add").toLowerCase()

      if (itemAction === "update") {
        const idx = nextLib.findIndex(
          (s) => s.name.toLowerCase() === name.toLowerCase()
        )
        if (idx >= 0) {
          nextLib[idx] = {
            ...nextLib[idx],
            ...(item.description != null
              ? { description: String(item.description).trim() }
              : {}),
            ...(item.imageUrl || item.image_url
              ? { imageUrl: item.imageUrl || item.image_url, pendingImage: false }
              : {}),
          }
        }
        continue
      }

      const exists = nextLib.some(
        (s) => s.name.toLowerCase() === name.toLowerCase()
      )
      if (exists) continue

      const entry = normalizeSceneLibraryEntry({
        id: makeSceneRefId(),
        name,
        description: item.description || "",
        imageUrl: item.imageUrl || item.image_url || null,
      })
      if (entry) nextLib.push(entry)
    }

    const sceneByName = new Map(
      nextLib.map((s) => [s.name.toLowerCase(), s])
    )
    const rowAssignments = Array.isArray(data.row_assignments)
      ? data.row_assignments
      : []
    const currentRows = scriptNode.data?.rows || []
    const touchedSceneIds = new Set()
    const nextRows = currentRows.map((row) => {
      const assign = rowAssignments.find(
        (a) =>
          a.row_id === row.id
          || a.rowId === row.id
          || String(a.shot_number || a.shotNumber || "") === String(row.shotNumber ?? "")
      )
      if (!assign) return row
      const sceneName = String(
        assign.scene_name || assign.sceneName || assign.name || ""
      ).trim()
      if (!sceneName) return row
      const scene = sceneByName.get(sceneName.toLowerCase())
      if (!scene?.id) return row
      touchedSceneIds.add(scene.id)
      return { ...row, locationId: scene.id }
    })

    const sceneLibraryWithUsage = [...touchedSceneIds].reduce(
      (lib, sid) => touchLibraryById(lib, sid),
      nextLib
    )

    const tableId = scriptNode.id
    flushSync(() => {
      setNodes((ns) =>
        ns.map((n) =>
          n.id === tableId
            ? {
                ...n,
                data: {
                  ...n.data,
                  sceneLibrary: sceneLibraryWithUsage,
                  rows: nextRows,
                },
              }
            : n
        )
      )
    })

    const scenePending = nextLib
      .filter((s) => !s.imageUrl)
      .map((s) => ({ id: s.id, name: s.name, type: "scene" }))

    return {
      ok: true,
      nodeIds: [tableId],
      scenePending,
      scriptTableId: tableId,
    }
  }

  return {
    createTextNote,
    startTextGeneration,
    generateOutline,
    generateScriptTable,
    splitShotBeats: splitShotBeatsStep,
    generateStoryboard,
    generateVideo,
    manageCast,
    manageScene,
  }
}

export function clearAgentThinking(setNodes) {
  void setNodes
}
