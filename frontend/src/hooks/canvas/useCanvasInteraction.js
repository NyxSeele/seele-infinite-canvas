import { useCallback, useRef } from "react"
import { message } from "antd"
import { addEdge, applyEdgeChanges } from "reactflow"
import { useCanvasStore } from "../../stores"
import { makeEmptyScriptRow } from "../../components/canvas/ScriptTableNode"
import { makeId, NODE_WIDTHS_MAP, isEmptyImageGenNode } from "../../utils/canvas/nodeHelpers"
import { buildIncomingEdgeDataPatch } from "../../components/canvas/videoReferenceHelpers"
import {
  hasFlyoutDrag,
  parseFlyoutDrop,
} from "../../utils/canvas/genHistoryDrag"
import { getT } from "../../utils/locale"
import { isPaneMenuSuppressed, markSuppressPaneMenu } from "../../utils/canvas/suppressPaneMenu"
import { uploadImageFileWithMeta, buildUploadedImageNodePatch } from "../../services/uploadImage"

export function useCanvasInteraction({
  nodes,
  setNodes,
  setEdges,
  getNode,
  createNode,
  buildData,
  selectedNodeId,
  setSelectedNodeId,
  pickerMenuRef,
  setPickerMenu,
  setContextMenu,
  connectingNodeRef,
  refSelectMode,
  exitRefSelectMode,
  raiseNodeToFront,
  commentMode = false,
  onCommentNodeClick,
  pushHistory,
  readOnly = false,
}) {
  const draggingRef = useRef(null)
  /** 拖线结束到菜单选择之间保留连线上下文（避免 pane click 清空 picker 后丢边） */
  const pendingEdgeCreateRef = useRef(null)

  const isRightSourceHandle = (handleId) =>
    !handleId || handleId === "src-right" || handleId === "src"

  const onConnect = useCallback(
    (params) => {
      pushHistory?.()
      setEdges((es) => addEdge({ ...params, type: "ghost", animated: false }, es))
      setNodes((ns) =>
        ns.map((n) => {
          if (n.id !== params.target) return n
          const sourceNode = ns.find((x) => x.id === params.source)
          const incomingPatch = buildIncomingEdgeDataPatch(sourceNode, n.type, n.data)
          return {
            ...n,
            data: {
              ...n.data,
              ...incomingPatch,
              linkedSourceData: sourceNode?.data || null,
            },
          }
        })
      )
    },
    [setEdges, setNodes, pushHistory]
  )

  const onEdgesChange = useCallback(
    (changes) => {
      changes.forEach((change) => {
        if (change.type === "remove") {
          setEdges((es) => {
            const removedEdge = es.find((e) => e.id === change.id)
            if (removedEdge) {
              setNodes((ns) =>
                ns.map((n) => {
                  if (n.id !== removedEdge.target) return n
                  const { linkedSourceId, linkedSourceType, linkedSourceData, ...rest } = n.data
                  return { ...n, data: rest }
                })
              )
            }
            return es.filter((e) => e.id !== change.id)
          })
        }
      })
      setEdges((es) => applyEdgeChanges(changes, es))
    },
    [setEdges, setNodes]
  )

  const onConnectStart = useCallback((_, { nodeId, handleType, handleId }) => {
    pendingEdgeCreateRef.current = null
    connectingNodeRef.current = { nodeId, handleType, handleId }
  }, [connectingNodeRef])

  const onConnectEnd = useCallback(
    (event) => {
      const connecting = connectingNodeRef.current
      connectingNodeRef.current = null
      if (!connecting?.nodeId) return

      // Drop on pane OR on a node body (not a valid target handle) → open picker
      const target = event.target
      const isHandle = target.classList.contains("react-flow__handle")
      const isPane =
        target.classList.contains("react-flow__pane") ||
        target.classList.contains("react-flow__background") ||
        target.tagName === "svg"
      // If dropped on a valid handle, RF's onConnect already fired — skip
      if (isHandle) return
      if (!isPane) {
        const droppedNodeId = target.closest(".react-flow__node")?.getAttribute("data-id")
        // 落在其他节点主体上也应打开创建菜单，而非直接连到该节点（避免落点显示已有图片）
        if (!droppedNodeId) return
      }

      if (connecting.handleId === 'src-left') {
        markSuppressPaneMenu()
        setPickerMenu({ x: event.clientX, y: event.clientY, nodeId: connecting.nodeId, handleId: connecting.handleId, toLeft: true, targetNodeId: connecting.nodeId })
      } else if (isRightSourceHandle(connecting.handleId)) {
        const sourceNode = nodes.find((n) => n.id === connecting.nodeId)
        const resolvedHandle =
          connecting.handleId === "src" ? "src" : "src-right"
        pendingEdgeCreateRef.current = {
          sourceNodeId: connecting.nodeId,
          sourceHandle: resolvedHandle,
        }
        markSuppressPaneMenu()
        setPickerMenu({
          x: event.clientX,
          y: event.clientY,
          nodeId: connecting.nodeId,
          handleId: resolvedHandle,
          fromEdge: true,
          sourceNodeId: connecting.nodeId,
          sourceNodeType: sourceNode?.type || null,
        })
      }
    },
    [nodes, connectingNodeRef, setPickerMenu]
  )

  const handleCreateNode = useCallback(
    (typeOrObj, menuContext) => {
      pushHistory?.()
      const type = typeof typeOrObj === "string" ? typeOrObj : typeOrObj.type
      const pm = menuContext ?? pickerMenuRef.current
      const pendingEdge = pendingEdgeCreateRef.current
      const edgeSourceId = pm?.sourceNodeId || pendingEdge?.sourceNodeId || null
      const edgeSourceHandle =
        pm?.handleId === "src"
          ? "src"
          : pm?.handleId || pendingEdge?.sourceHandle || "src-right"

      if (pm?.toLeft && pm?.targetNodeId) {
        const targetNode = nodes.find((n) => n.id === pm.targetNodeId)
        if (targetNode) {
          const newNodeWidth = NODE_WIDTHS_MAP[type] || 280
          const newId = makeId(type)
          const newPos = {
            x: targetNode.position.x - newNodeWidth - 80,
            y: targetNode.position.y,
          }
          setNodes((ns) => {
            const updated = ns.map((n) => {
              if (n.id !== pm.targetNodeId) return n
              return { ...n, data: { ...n.data, linkedSourceId: newId, linkedSourceType: type } }
            })
            return [...updated, { id: newId, type, position: newPos, data: buildData() }]
          })
          setEdges((es) =>
            addEdge({ id: `e-${newId}-${pm.targetNodeId}-${Date.now()}`, source: newId, target: pm.targetNodeId, sourceHandle: 'src-right', targetHandle: 'tgt', type: "ghost", animated: false }, es)
          )
          setPickerMenu(null)
          pendingEdgeCreateRef.current = null
          return
        }
      }

      const screenPos = pm ? { x: pm.x, y: pm.y } : { x: window.innerWidth / 2, y: window.innerHeight / 2 }
      let extra = type === "script-table"
        ? {
            label: getT()("canvas.node.labelScriptTable"),
            rows: [makeEmptyScriptRow(1)],
            globalStyle: "",
            themeContext: "",
            continuityMode: true,
            visualContinuity: false,
          }
        : type === "character-card"
          ? {
              label: getT()("canvas.characterCard.title"),
              name: "",
              appearance: "",
              referenceImages: [],
            }
          : {}

      const shouldLinkFromEdge = Boolean(
        (pm?.fromEdge && edgeSourceId)
        || (pendingEdge?.sourceNodeId && edgeSourceId)
      )

      if (shouldLinkFromEdge && edgeSourceId) {
        const sourceNode = nodes.find((n) => n.id === edgeSourceId)
        extra = {
          ...extra,
          ...buildIncomingEdgeDataPatch(sourceNode, type, extra),
        }
      }

      const placement = shouldLinkFromEdge && edgeSourceId
        ? { anchorNodeId: edgeSourceId }
        : { anchorNodeId: selectedNodeId || null }
      const newId = createNode(type, screenPos, extra, placement)
      if (shouldLinkFromEdge && edgeSourceId && newId) {
        setEdges((es) =>
          addEdge(
            {
              id: `e-${edgeSourceId}-${newId}-${Date.now()}`,
              source: edgeSourceId,
              target: newId,
              sourceHandle: edgeSourceHandle,
              targetHandle: "tgt",
              type: "ghost",
              animated: false,
            },
            es
          )
        )
      }
      if (newId) {
        setSelectedNodeId(newId)
        raiseNodeToFront(newId)
      }
      pendingEdgeCreateRef.current = null
      setPickerMenu(null)
    },
    [createNode, nodes, setEdges, setNodes, buildData, pickerMenuRef, setPickerMenu, pushHistory, selectedNodeId, setSelectedNodeId, raiseNodeToFront]
  )

  const handlePaneDblClick = useCallback((e) => {
    if (commentMode) return
    if (isPaneMenuSuppressed()) return
    if (
      e.target.closest(".react-flow__node")
      || e.target.closest(
        ".nb-banner, .tl-picker-menu, .tl-context-menu, .tl-topbar, .tl-left-toolbar, " +
        ".ctb-bar, .clt-toolbar, .cbt-bar, .wf-inspector, .rf-overlay, " +
        ".ghf-flyout, .alf-flyout, .agent-panel, " +
        ".cell-menu-portal, .gn2-dots-menu, .cell-dots-submenu"
      )
    ) {
      return
    }
    setPickerMenu({ x: e.clientX, y: e.clientY })
    setContextMenu(null)
  }, [commentMode, setPickerMenu, setContextMenu])

  const handlePaneContextMenu = useCallback((e) => {
    if (e.target.closest(".react-flow__node")) return
    e.preventDefault()
    if (commentMode) return
    if (isPaneMenuSuppressed()) return
    if (e.target.closest(
      ".ctb-bar, .clt-toolbar, .cbt-bar, .tl-topbar, .tl-left-toolbar, .wf-inspector, " +
      ".cell-menu-portal, .gn2-dots-menu, .cell-dots-submenu"
    )) return
    setContextMenu({ x: e.clientX, y: e.clientY })
    setPickerMenu(null)
  }, [commentMode, setPickerMenu, setContextMenu])

  const handlePaneClick = useCallback(() => {
    if (document.activeElement?.closest?.(".ccp-marker-pin")) {
      document.activeElement.blur()
    }
    if (commentMode) return
    window.dispatchEvent(new Event("canvas-close-param-panels"))
    if (!isPaneMenuSuppressed()) {
      setPickerMenu(null)
      pendingEdgeCreateRef.current = null
    }
    setContextMenu(null)
    if (refSelectMode.active) {
      exitRefSelectMode()
      return
    }
    setSelectedNodeId(null)
  }, [commentMode, refSelectMode.active, exitRefSelectMode, setPickerMenu, setContextMenu, setSelectedNodeId])

  const handleUploadImage = useCallback(() => {
    if (readOnly) {
      message.warning("当前为只读模式，无法上传图片")
      return
    }
    const input = document.createElement("input")
    input.type = "file"
    input.accept = "image/*"
    input.onchange = async (e) => {
      const file = e.target.files?.[0]
      if (!file) return
      const hideRef = { current: null }
      const showPhase = (text) => {
        hideRef.current?.()
        hideRef.current = message.loading(text, 0)
      }
      showPhase("正在上传…")
      try {
        const meta = await uploadImageFileWithMeta(file, {
          onPhase: (phase) => {
            if (phase === "upload") showPhase("正在上传…")
          },
        })
        const patch = buildUploadedImageNodePatch(meta)
        const selected = selectedNodeId ? getNode(selectedNodeId) : null
        if (isEmptyImageGenNode(selected) && selected.data?.onUpdate) {
          pushHistory?.()
          selected.data.onUpdate(selectedNodeId, patch)
          message.success("图片已上传")
          return
        }
        const screenPos = { x: window.innerWidth / 2, y: window.innerHeight / 2 }
        pushHistory?.()
        const id = createNode(
          "image-gen",
          screenPos,
          patch,
          { anchorNodeId: selectedNodeId || null },
        )
        if (id) {
          setSelectedNodeId(id)
          raiseNodeToFront(id)
          message.success("图片已上传")
        } else {
          message.error("无法创建图片节点，请确认您有画布编辑权限")
        }
      } catch (err) {
        console.error("上传失败", err)
        message.error(err.message || err.response?.data?.detail || "图片上传失败，请重试")
      } finally {
        hideRef.current?.()
      }
    }
    input.click()
  }, [createNode, getNode, pushHistory, raiseNodeToFront, readOnly, selectedNodeId, setSelectedNodeId])

  const handleAddNodeOfType = useCallback(
    (type) => {
      if (type === "image-upload") { handleUploadImage(); return }
      pushHistory?.()
      const id = createNode(
        type,
        { x: window.innerWidth / 2, y: window.innerHeight / 2 },
        {},
        { anchorNodeId: selectedNodeId || null },
      )
      if (id) {
        setSelectedNodeId(id)
        raiseNodeToFront(id)
      }
    },
    [createNode, handleUploadImage, pushHistory, raiseNodeToFront, selectedNodeId, setSelectedNodeId]
  )

  const handleQuickCreate = useCallback(
    (type) => {
      pushHistory?.()
      const id = createNode(
        type,
        { x: window.innerWidth / 2, y: window.innerHeight / 2 },
        {},
        { anchorNodeId: selectedNodeId || null },
      )
      if (id) {
        setSelectedNodeId(id)
        raiseNodeToFront(id)
      }
    },
    [createNode, pushHistory, raiseNodeToFront, selectedNodeId, setSelectedNodeId]
  )

  const handleNodeDragStart = useCallback((_e, node) => {
    draggingRef.current = node.id
    raiseNodeToFront(node.id)
    if (selectedNodeId === node.id) setSelectedNodeId(null)
  }, [selectedNodeId, raiseNodeToFront, setSelectedNodeId])

  const handleNodeDragStop = useCallback((_e, node) => {
    if (draggingRef.current === node.id) {
      draggingRef.current = null
      raiseNodeToFront(node.id)
      setSelectedNodeId(node.id)
    }
  }, [raiseNodeToFront, setSelectedNodeId])

  const handleNodeClick = useCallback((_e, node) => {
    if (commentMode) {
      onCommentNodeClick?.(node.id)
      return
    }
    if (refSelectMode.active) return
    raiseNodeToFront(node.id)
    setSelectedNodeId(node.id)
    useCanvasStore.getState().setLastFocusedNodeId(node.id)
  }, [commentMode, onCommentNodeClick, refSelectMode.active, raiseNodeToFront, setSelectedNodeId])

  const handleFlyoutDragOver = useCallback((e) => {
    if (!hasFlyoutDrag(e)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = "copy"
  }, [])

  const handleFlyoutDrop = useCallback(
    (e) => {
      const item = parseFlyoutDrop(e)
      if (!item) return
      e.preventDefault()
      e.stopPropagation()
      pushHistory?.()
      const screenPos = { x: e.clientX, y: e.clientY }
      let id
      if (item.source === "asset") {
        id = createNode("image-gen", screenPos, {
          prompt: item.name || "",
          status: "input",
          uploadedImage: item.imageUrl,
          imageSource: "asset",
        })
      } else if (item.type === "video-gen") {
        id = createNode("video-gen", screenPos, {
          prompt: item.prompt || "",
          status: "completed",
          videoUrl: item.resultUrl,
        })
      } else {
        id = createNode("image-gen", screenPos, {
          prompt: item.prompt || "",
          status: "input",
          uploadedImage: item.resultUrl,
          imageSource: "history",
        })
      }
      setSelectedNodeId(id)
      raiseNodeToFront(id)
    },
    [createNode, setSelectedNodeId, raiseNodeToFront, pushHistory]
  )

  const dismissPickerMenu = useCallback(() => {
    pendingEdgeCreateRef.current = null
    setPickerMenu(null)
  }, [setPickerMenu])

  return {
    handlePaneDblClick,
    handlePaneContextMenu,
    handlePaneClick,
    handleNodeDragStart,
    handleNodeDragStop,
    handleNodeClick,
    handleCreateNode,
    dismissPickerMenu,
    handleAddNodeOfType,
    handleQuickCreate,
    handleUploadImage,
    handleFlyoutDragOver,
    handleFlyoutDrop,
    onConnect,
    onEdgesChange,
    onConnectStart,
    onConnectEnd,
  }
}
