import { useCallback, useRef } from "react"
import { addEdge, applyEdgeChanges } from "reactflow"
import { useCanvasStore } from "../../stores"
import { makeEmptyScriptRow } from "../../components/canvas/ScriptTableNode"
import { makeId, NODE_WIDTHS_MAP, isEmptyImageGenNode } from "../../utils/canvas/nodeHelpers"
import {
  hasFlyoutDrag,
  parseFlyoutDrop,
} from "../../utils/canvas/genHistoryDrag"
import { getT } from "../../utils/locale"
import { isPaneMenuSuppressed } from "../../utils/canvas/suppressPaneMenu"

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
}) {
  const draggingRef = useRef(null)

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
          return {
            ...n,
            data: {
              ...n.data,
              linkedSourceId: params.source,
              linkedSourceType: sourceNode?.type || null,
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
        // dropped on node body — only open picker if same-source not already connected
        const droppedNodeId = target.closest(".react-flow__node")?.getAttribute("data-id")
        if (droppedNodeId && droppedNodeId !== connecting.nodeId) {
          // Direct connection to existing node
          if (isRightSourceHandle(connecting.handleId)) {
            pushHistory?.()
            setEdges((es) => addEdge({ id: `e-${connecting.nodeId}-${droppedNodeId}-${Date.now()}`, source: connecting.nodeId, target: droppedNodeId, sourceHandle: connecting.handleId === "src" ? "src" : "src-right", targetHandle: 'tgt', type: "ghost", animated: false }, es))
          }
          return
        }
        if (!droppedNodeId) return
      }

      if (connecting.handleId === 'src-left') {
        setPickerMenu({ x: event.clientX, y: event.clientY, nodeId: connecting.nodeId, handleId: connecting.handleId, toLeft: true, targetNodeId: connecting.nodeId })
      } else if (isRightSourceHandle(connecting.handleId)) {
        const sourceNode = nodes.find((n) => n.id === connecting.nodeId)
        const resolvedHandle =
          connecting.handleId === "src" ? "src" : "src-right"
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
    [nodes, setEdges, connectingNodeRef, setPickerMenu, pushHistory]
  )

  const handleCreateNode = useCallback(
    (typeOrObj) => {
      pushHistory?.()
      const type = typeof typeOrObj === "string" ? typeOrObj : typeOrObj.type
      const pm = pickerMenuRef.current

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
          return
        }
      }

      const screenPos = pm ? { x: pm.x, y: pm.y } : { x: window.innerWidth / 2, y: window.innerHeight / 2 }
      const extra = type === "script-table"
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
      const placement =
        pm?.fromEdge && pm?.sourceNodeId
          ? { anchorNodeId: pm.sourceNodeId }
          : { anchorNodeId: selectedNodeId || null }
      const newId = createNode(type, screenPos, extra, placement)
      if (pm?.fromEdge && pm?.sourceNodeId && newId) {
        const sourceNode = nodes.find((n) => n.id === pm.sourceNodeId)
        setEdges((es) =>
          addEdge(
            { id: `e-${pm.sourceNodeId}-${newId}-${Date.now()}`, source: pm.sourceNodeId, target: newId, sourceHandle: 'src-right', targetHandle: 'tgt', type: "ghost", animated: false },
            es
          )
        )
        setNodes((ns) =>
          ns.map((n) => {
            if (n.id !== newId) return n
            return { ...n, data: { ...n.data, linkedSourceId: pm.sourceNodeId, linkedSourceType: sourceNode?.type || null } }
          })
        )
      }
      setPickerMenu(null)
    },
    [createNode, nodes, setEdges, setNodes, buildData, pickerMenuRef, setPickerMenu, pushHistory, selectedNodeId]
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
    setPickerMenu(null)
    setContextMenu(null)
    if (refSelectMode.active) {
      exitRefSelectMode()
      return
    }
    setSelectedNodeId(null)
  }, [commentMode, refSelectMode.active, exitRefSelectMode, setPickerMenu, setContextMenu, setSelectedNodeId])

  const handleUploadImage = useCallback(() => {
    const input = document.createElement("input")
    input.type = "file"
    input.accept = "image/*"
    input.onchange = async (e) => {
      const file = e.target.files?.[0]
      if (!file) return
      try {
        const { uploadImageFile } = await import("../../services/uploadImage")
        const url = await uploadImageFile(file)
        const selected = selectedNodeId ? getNode(selectedNodeId) : null
        if (isEmptyImageGenNode(selected) && selected.data?.onUpdate) {
          pushHistory?.()
          selected.data.onUpdate(selectedNodeId, {
            uploadedImage: url,
            imageSource: "upload",
            status: "input",
            error: null,
          })
          return
        }
        const screenPos = { x: window.innerWidth / 2, y: window.innerHeight / 2 }
        pushHistory?.()
        const id = createNode(
          "image-gen",
          screenPos,
          {
            uploadedImage: url,
            imageSource: "upload",
            status: "input",
          },
          { anchorNodeId: selectedNodeId || null },
        )
        if (id) {
          setSelectedNodeId(id)
          raiseNodeToFront(id)
        }
      } catch (err) {
        console.error("上传失败", err)
      }
    }
    input.click()
  }, [createNode, getNode, pushHistory, raiseNodeToFront, selectedNodeId, setSelectedNodeId])

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

  return {
    handlePaneDblClick,
    handlePaneContextMenu,
    handlePaneClick,
    handleNodeDragStart,
    handleNodeDragStop,
    handleNodeClick,
    handleCreateNode,
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
