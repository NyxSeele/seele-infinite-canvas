import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNodesState, useEdgesState, addEdge } from "reactflow"
import { useAuth } from "../../contexts/AuthContext"
import { cancelCanvasTask } from "../../services/cancelTask"
import { stampEditMeta } from "../../utils/canvas/nodeEditMeta"
import {
  DEFAULT_KEYFRAMES,
  removeRefsSourcedFromNode,
} from "../../components/canvas/videoReferenceHelpers"
import { useCanvasStore } from "../../stores"
import { pickOutlineNodeFields, outlineSafePatch } from "../../utils/canvas/nodeCompose"
import {
  normalizeTextResponseNode,
  normalizeOutlineNode,
  normalizeShotScriptNode,
} from "../../utils/canvas/nodeNormalize"
import {
  makeId,
  resolveCreateNodePosition,
} from "../../utils/canvas/nodeHelpers"
import { useCanvasZIndex } from "./useCanvasZIndex"
import { getT } from "../../utils/locale"
import { isNodePatchNoop } from "../../utils/canvas/nodePatch"

export function useCanvasNodes({
  screenToFlowPosition,
  screenplayHandlersRef,
  stopPolling,
  runTextGeneration,
  updateResponseNodeData,
  getNode,
  readOnlyRef,
}) {
  const { user } = useAuth()
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const nodesRef = useRef([])
  const edgesRef = useRef([])
  useEffect(() => { nodesRef.current = nodes }, [nodes])
  useEffect(() => { edgesRef.current = edges }, [edges])

  const { zIndexCounterRef, bumpZIndex, raiseNodeToFront } = useCanvasZIndex(setNodes)
  const setHasShapes = useCanvasStore((s) => s.setHasShapes)

  useEffect(() => {
    setHasShapes(nodes.length > 0)
  }, [nodes.length, setHasShapes])

  // 清除 text-response / outline 上遗留的 dragHandle，恢复整卡拖动
  useEffect(() => {
    setNodes((ns) => {
      let changed = false
      const next = ns.map((n) => {
        if (n.type === "text-response" && n.dragHandle) {
          changed = true
          return normalizeTextResponseNode(n)
        }
        if (n.type === "outline" && n.dragHandle) {
          changed = true
          return normalizeOutlineNode(n)
        }
        if (n.type === "shot-script" && n.dragHandle) {
          changed = true
          return normalizeShotScriptNode(n)
        }
        return n
      })
      return changed ? next : ns
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedNodeId && !nodes.find(n => n.id === selectedNodeId)) {
      setSelectedNodeId(null)
    }
  }, [nodes, selectedNodeId])

  const isCommitBlocked = useCallback(
    () => readOnlyRef?.current === true,
    [readOnlyRef]
  )

  const applyNodePatch = useCallback((nodeId, patch) => {
    if (isCommitBlocked()) return
    queueMicrotask(() => {
      setNodes((ns) => {
        const target = ns.find((n) => n.id === nodeId)
        if (!target) return ns
        const skipPromptSync =
          target.type === "outline"
          || target.type === "shot-script"
          || target.type === "script-table"
          || target.type === "script-beat-card"
          || target.type === "image-gen"
          || target.type === "video-gen"
        if (!skipPromptSync && target.type === "text-note" && patch.content !== undefined) {
          useCanvasStore.getState().syncPromptBar(nodeId, patch.content)
        }
        if (target.type === "outline") {
          if (isNodePatchNoop(target.data, outlineSafePatch(patch))) return ns
          return ns.map((n) =>
            n.id === nodeId
              ? { ...n, data: { ...n.data, ...outlineSafePatch(patch) } }
              : n
          )
        }
        const stamped = stampEditMeta(patch, user)
        if (isNodePatchNoop(target.data, stamped)) return ns
        return ns.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...stamped } } : n
        )
      })
    })
  }, [setNodes, user, isCommitBlocked])

  const buildOutlineData = useCallback(
    (extra = {}) => {
      const outlineFields = pickOutlineNodeFields(extra)
      return {
        ...outlineFields,
        onUpdate: (nodeId, patch) => {
          if (isCommitBlocked()) return
          queueMicrotask(() => {
            setNodes((ns) =>
              ns.map((n) =>
                n.id === nodeId && n.type === "outline"
                  ? isNodePatchNoop(n.data, outlineSafePatch(patch))
                    ? n
                    : { ...n, data: { ...n.data, ...outlineSafePatch(patch) } }
                  : n
              )
            )
          })
        },
        onGenerateShotScript: (...args) =>
          screenplayHandlersRef.current.onGenerateShotScript?.(...args),
        onGenerateScriptTable: (...args) =>
          screenplayHandlersRef.current.onGenerateScriptTable?.(...args),
      }
    },
    [setNodes, screenplayHandlersRef, user, isCommitBlocked]
  )

  const buildData = useCallback(
    (extra = {}) => ({
      ...extra,
      onUpdate: applyNodePatch,
      onDelete: (id) => {
        if (isCommitBlocked()) return
        setNodes((ns) => ns.filter((n) => n.id !== id))
        setEdges((es) => es.filter((e) => e.source !== id && e.target !== id))
      },
      onDisconnectIncoming: (nodeId) => {
        if (isCommitBlocked()) return
        setEdges((es) => {
          const removed = es.filter((e) => e.target === nodeId)
          if (removed.length > 0) {
            setNodes((ns) =>
              ns.map((n) => {
                if (n.id !== nodeId) return n
                let nextData = { ...n.data }
                removed.forEach((edge) => {
                  const refPatch = removeRefsSourcedFromNode(nextData, edge.source) || {}
                  nextData = { ...nextData, ...refPatch }
                  if (nextData.linkedSourceId === edge.source) {
                    const { linkedSourceId, linkedSourceType, linkedSourceData, ...rest } = nextData
                    nextData = rest
                  }
                })
                return { ...n, data: nextData }
              })
            )
          }
          return es.filter((e) => e.target !== nodeId)
        })
      },
      onDisconnectIncomingFromSource: (targetNodeId, sourceNodeId) => {
        if (isCommitBlocked() || !targetNodeId || !sourceNodeId) return
        setEdges((es) =>
          es.filter((e) => !(e.target === targetNodeId && e.source === sourceNodeId))
        )
        setNodes((ns) =>
          ns.map((n) => {
            if (n.id !== targetNodeId) return n
            const refPatch = removeRefsSourcedFromNode(n.data, sourceNodeId) || {}
            let nextData = { ...n.data, ...refPatch }
            if (n.data.linkedSourceId === sourceNodeId) {
              const { linkedSourceId, linkedSourceType, linkedSourceData, ...rest } = nextData
              nextData = rest
            }
            return { ...n, data: nextData }
          })
        )
      },
      onApplyVideoReference: (targetVideoId, refItem, slot) => {
        if (isCommitBlocked()) return
        setNodes((ns) =>
          ns.map((n) => {
            if (n.id !== targetVideoId || n.type !== "video-gen") return n
            if (slot === "first") {
              const keyframes = { ...(n.data.keyframes || DEFAULT_KEYFRAMES), first: refItem }
              return { ...n, data: { ...n.data, referenceMode: "keyframe", keyframes } }
            }
            if (slot === "last") {
              const keyframes = { ...(n.data.keyframes || DEFAULT_KEYFRAMES), last: refItem }
              return { ...n, data: { ...n.data, referenceMode: "keyframe", keyframes } }
            }
            if (slot === "freeref") {
              const freeRefs = [...(n.data.freeRefs || [])]
              if (freeRefs.length >= 5 || freeRefs.some((r) => r.imageId === refItem.imageId)) {
                return n
              }
              return {
                ...n,
                data: { ...n.data, referenceMode: "freeref", freeRefs: [...freeRefs, refItem] },
              }
            }
            return n
          })
        )
        setSelectedNodeId(targetVideoId)
      },
      onStopGeneration: (responseNodeId) => {
        if (isCommitBlocked()) return
        stopPolling(responseNodeId)
        setNodes((ns) => {
          const node = ns.find((n) => n.id === responseNodeId)
          const tid = node?.data?.taskId
          if (tid) {
            cancelCanvasTask(tid).catch((err) =>
              console.error("[text] cancel failed:", err)
            )
          }
          return ns.map((n) =>
            n.id === responseNodeId
              ? {
                  ...n,
                  data: {
                    ...n.data,
                    status: "failed",
                    error: getT()("canvas.gen.stopped"),
                  },
                }
              : n
          )
        })
      },
      /** 仅用于创建 outline 节点，避免 buildData 注入 sourceNodeId / 跨节点 handlers */
      composeNodeData: (extra = {}) => buildOutlineData(extra),
      composeOutlineNodeData: (extra = {}) => buildOutlineData(extra),
      connectOutlineFromResponse: (responseNodeId, outlineNodeId) => {
        if (isCommitBlocked()) return
        setEdges((es) =>
          addEdge(
            {
              id: `e-${responseNodeId}-${outlineNodeId}-${Date.now()}`,
              source: responseNodeId,
              sourceHandle: "src-right",
              target: outlineNodeId,
              targetHandle: "tgt",
              type: "ghost",
              animated: false,
            },
            es
          )
        )
      },
      onGenerateScreenplay: (...args) =>
        screenplayHandlersRef.current.onGenerateScreenplay?.(...args),
      onGenerateShotScript: (...args) =>
        screenplayHandlersRef.current.onGenerateShotScript?.(...args),
      onGenerateScriptTable: (...args) =>
        screenplayHandlersRef.current.onGenerateScriptTable?.(...args),
      onImportScriptTable: (...args) =>
        screenplayHandlersRef.current.onImportScriptTable?.(...args),
      onMigrateShotScript: (...args) =>
        screenplayHandlersRef.current.onMigrateShotScript?.(...args),
    }),
    [setNodes, setEdges, stopPolling, buildOutlineData, screenplayHandlersRef, applyNodePatch, isCommitBlocked]
  )

  const createNode = useCallback(
    (type, screenPos, extra = {}, placement = {}) => {
      if (isCommitBlocked()) return null
      const flowPos = screenToFlowPosition({ x: screenPos.x, y: screenPos.y })
      let id = makeId(type)
      const z = bumpZIndex()
      const videoDefaults =
        type === "video-gen"
          ? {
              status: "input",
              referenceMode: "keyframe",
              panelMode: "keyframe",
              vidMode: "首尾帧",
              keyframes: DEFAULT_KEYFRAMES,
            }
          : {}
      const nodeData =
        type === "outline"
          ? buildOutlineData({ ...extra, zIndex: z })
          : buildData({ ...videoDefaults, ...extra, zIndex: z })
      setNodes((ns) => {
        const existingIds = new Set(ns.map((n) => n.id))
        while (existingIds.has(id)) {
          id = makeId(type)
        }
        const anchorNode = placement.anchorNodeId
          ? ns.find((n) => n.id === placement.anchorNodeId)
          : null
        const position = resolveCreateNodePosition(flowPos, type, ns, { anchorNode })
        return [
          ...ns,
          {
            id,
            type,
            position,
            zIndex: z,
            data: nodeData,
            style: { zIndex: z },
          },
        ]
      })
      return id
    },
    [screenToFlowPosition, setNodes, buildData, buildOutlineData, bumpZIndex, isCommitBlocked]
  )

  const selectedNodeType = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId)?.type || null,
    [nodes, selectedNodeId]
  )

  const handlePromptBarGenerate = useCallback(async (nodeId, params) => {
    if (isCommitBlocked()) return
    if (nodeId) useCanvasStore.getState().setLastFocusedNodeId(nodeId)

    if (selectedNodeType === "text-note") {
      await runTextGeneration(nodeId, params)
      return
    }

    if (selectedNodeType === "text-response") {
      const text = params.prompt?.trim() || ""
      updateResponseNodeData(nodeId, { content: text, prompt: text })
      return
    }

    setNodes((ns) => ns.map((n) => {
      if (n.id !== nodeId) return n
      return {
        ...n,
        data: {
          ...n.data,
          prompt:          params.prompt,
          mentions:        params.mentions || [],
          modelId:         params.modelId,
          sizeIndex:       params.sizeIndex,
          width:           params.width,
          height:          params.height,
          referenceImageUrl: params.referenceImage || null,
          referenceImages: params.referenceImages || [],
          reference_images: params.reference_images || params.referenceImages?.map((r) => r?.imageUrl).filter(Boolean) || [],
          referenceImage: params.referenceImage || null,
          referenceRef: params.referenceImages?.[0] ?? null,
          imgQuality:      params.imgQuality,
          imgRatio:        params.imgRatio,
          imgResolution:   params.imgResolution,
          imgSteps:        params.imgSteps,
          imgCfg:          params.imgCfg,
          vidMode:         params.vidMode,
          vidRatio:        params.vidRatio,
          vidQuality:      params.vidQuality,
          vidDuration:     params.vidDuration,
          vidAudio:        params.vidAudio,
          audioUrl:        params.audioUrl || null,
          referenceMode:   params.referenceMode
            || (params.vidMode === "参考"
              ? "freeref"
              : params.vidMode === "文生"
                ? "t2v"
                : "keyframe"),
          freeRefs:        params.freeRefs ?? n.data.freeRefs,
          qualityPresetId: params.qualityPresetId ?? n.data.qualityPresetId,
          cameraMove:      params.cameraMove ?? n.data.cameraMove ?? "auto",
          shotScale:       params.shotScale ?? n.data.shotScale ?? "auto",
          samplingProfile: params.samplingProfile
            ?? n.data.samplingProfile
            ?? ((params.cameraMove || n.data.cameraMove || "auto") !== "auto" ? "quality" : "fast"),
          count:           params.count,
          expectedCount:   params.count || 1,
          pendingTrigger:  Date.now(),
        },
      }
    }))
  }, [setNodes, selectedNodeType, runTextGeneration, updateResponseNodeData, isCommitBlocked])

  return {
    nodes,
    edges,
    setNodes,
    setEdges,
    onNodesChange,
    onEdgesChange,
    nodesRef,
    edgesRef,
    buildData,
    buildOutlineData,
    selectedNodeId,
    setSelectedNodeId,
    selectedNodeType,
    createNode,
    handlePromptBarGenerate,
    zIndexCounterRef,
    bumpZIndex,
    raiseNodeToFront,
  }
}
