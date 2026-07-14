import { useCallback, useState, useEffect, useRef, useMemo } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router-dom"
import ReactFlow, {
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  MiniMap,
  Panel,
  useReactFlow,
  useViewport,
  addEdge,
} from "reactflow"
import "reactflow/dist/style.css"
import GenerationCardNode from "../components/canvas/GenerationCardNode"
import VideoGenerationNode from "../components/canvas/VideoGenerationNode"
import TextNode from "../components/canvas/TextNode"
import TextResponseNode from "../components/canvas/TextResponseNode"
import ScriptTableNode from "../components/canvas/ScriptTableNode"
import CharacterCardNode from "../components/canvas/CharacterCardNode"
import ScriptBeatCardNode from "../components/canvas/ScriptBeatCardNode"
import OutlineNode from "../components/canvas/OutlineNode"
import ShotScriptNode from "../components/canvas/ShotScriptNode"
import GhostEdge from "../components/canvas/GhostEdge"
import CanvasTopbar from "../components/canvas/CanvasTopbar"
import CanvasLeftToolbar from "../components/canvas/CanvasLeftToolbar"
import CanvasBottomToolbar from "../components/canvas/CanvasBottomToolbar"
import CanvasPromptBar from "../components/canvas/CanvasPromptBar"
import AssetLibraryFlyout from "../components/canvas/AssetLibraryFlyout"
import GenerationHistoryFlyout from "../components/canvas/GenerationHistoryFlyout"
import NodePickerMenu from "../components/canvas/NodePickerMenu"
import ImportDocumentModal from "../components/canvas/ImportDocumentModal"
import { CanvasActionsContext, ReferenceSelectContext } from "../components/canvas/CanvasActionsContext"
import CanvasRightClickMenu from "../components/canvas/CanvasRightClickMenu"
import CanvasEmptyState from "../components/canvas/CanvasEmptyState"
import CanvasCommentPanel from "../components/canvas/CanvasCommentPanel"
import CanvasCommentMarkers from "../components/canvas/CanvasCommentMarkers"
import { getCommentAnchorRect } from "../utils/canvas/commentMarkerLayout"
import { useCanvasComments } from "../hooks/canvas/useCanvasComments"
import { markNodeMentionNotificationsRead } from "../utils/notificationThread"
import { emitNotificationUnread } from "../hooks/useNotificationUnread"
import { fetchNotifications } from "../services/notificationsApi"
import {
  countUnreadCommentNodes,
  getMentionHighlightIds,
  markMentionsSeen,
  markNodeCommentsSeen,
} from "../utils/canvas/commentReadState"
import { useCanvasPresence } from "../hooks/canvas/useCanvasPresence"
import { readDisplayName, personLabel } from "../utils/canvas/commentUserDisplay"
import { listTeamMembers } from "../services/teamApi"
import { getActiveTeamId } from "../utils/teamContext"
import { canvasWsManager } from "../services/canvasWs"
import PromptTracePanel from "../components/canvas/PromptTracePanel"
import { CanvasThemeProvider } from "../components/canvas/CanvasThemeContext"
import { PromptIntentGateProvider } from "../components/canvas/PromptIntentGateContext"
import { TEXT_MODES, sortScriptRows } from "../utils/canvas/nodeHelpers"
import { wsManager } from "../services/ws"
import { useAuth } from "../contexts/AuthContext"
import { useAssetStore, useCanvasStore, useModelStore, useTaskStore, useTeamStore } from "../stores"
import {
  DEFAULT_KEYFRAMES,
  getImageNodeImages,
} from "../components/canvas/videoReferenceHelpers"
import { makeCastRefId, normalizeCastLibrary } from "../utils/canvas/castLibrary"
import { touchLibraryById } from "../utils/canvas/libraryUsage"
import { normalizeSceneLibrary, makeSceneRefId } from "../utils/canvas/sceneLibrary"
import {
  buildBeatCardCreatePayload,
  BEAT_CARD_NODE_TYPE,
  syncBeatCardFromKeyframes,
} from "../utils/canvas/scriptBeatCard"
import { syncRowFromKeyframes, asKeyframeArray } from "../utils/canvas/scriptTableKeyframes"
import ImageReferencePicker from "../components/canvas/ImageReferencePicker"
import { stripMediaTicket } from "../utils/mediaTicket"
import { useLocale } from "../utils/locale"
import { normalizeCanvasNode } from "../utils/canvas/nodeNormalize"
import { getCanvasNavFlowProps } from "../utils/canvas/canvasNavMode"
import { organizeCanvasNodes } from "../utils/canvas/organizeCanvasNodes"
import { createCanvasProject, deleteCanvasProject, loadCanvasProject, migrateCanvasProjectToTeam } from "../services/canvasApi"
import { useCanvasNodes } from "../hooks/canvas/useCanvasNodes"
import { useCanvasSave } from "../hooks/canvas/useCanvasSave"
import { useCanvasSession } from "../hooks/canvas/useCanvasSession"
import { useTextGeneration } from "../hooks/canvas/useTextGeneration"
import { useScreenplay } from "../hooks/canvas/useScreenplay"
import { useScriptTableGenerate } from "../hooks/canvas/useScriptTableGenerate"
import { useCanvasInteraction } from "../hooks/canvas/useCanvasInteraction"
import { useCanvasHistory, isCanvasShortcutTarget } from "../hooks/canvas/useCanvasHistory"
import { useCanvasDragPlace } from "../hooks/canvas/useCanvasDragPlace"
import { useRefSelectMode } from "../hooks/canvas/useRefSelectMode"
import CanvasDragGhost from "../components/canvas/CanvasDragGhost"
import CanvasProfileModal from "../components/canvas/CanvasProfileModal"
import MigrateToTeamModal, { getMigratableTeams } from "../components/workspace/MigrateToTeamModal"
import AgentPanel, { AGENT_REF_SOURCE_ID } from "../components/canvas/AgentPanel"
import CanvasAgentFab from "../components/canvas/CanvasAgentFab"
import OnboardingTour from "../components/Onboarding/OnboardingTour"
import { CANVAS_STEPS } from "../components/Onboarding/tourSteps"
import "./Canvas.css"
import "../styles/promptBarTokens.css"
import "../components/canvas/menus-portal.css"
import "../components/canvas/textWorkflowTheme.css"
import "../components/canvas/AgentPanel.css"
import "../components/canvas/CanvasAgentFab.css"

function PendingConnectionLine({ pickerMenu, theme }) {
  if (!pickerMenu?.nodeId || !pickerMenu?.handleId) return null

  const handleEl = document.querySelector(
    `[data-nodeid="${pickerMenu.nodeId}"][data-handleid="${pickerMenu.handleId}"]`
  )
  if (!handleEl) return null
  const r = handleEl.getBoundingClientRect()
  const ax = r.left + r.width / 2
  const ay = r.top + r.height / 2
  const bx = pickerMenu.x, by = pickerMenu.y
  const fromLeft = pickerMenu.handleId === 'src-left'
  const dx = bx - ax
  const offset = Math.max(dx * 0.45, 80)
  const cp1x = fromLeft ? ax - offset : ax + offset
  const cp2x = fromLeft ? bx + offset : bx - offset
  const d = `M ${ax} ${ay} C ${cp1x} ${ay}, ${cp2x} ${by}, ${bx} ${by}`
  const isLight = theme === "light"
  const stroke = isLight ? "rgba(0,0,0,0.52)" : "rgba(255,255,255,0.9)"
  const filter = isLight
    ? undefined
    : "drop-shadow(0 0 3px rgba(255,255,255,0.7)) drop-shadow(0 0 8px rgba(255,255,255,0.35))"

  return (
    <svg style={{ position: "fixed", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 450 }}>
      <path d={d} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" fill="none"
        style={filter ? { filter } : undefined} />
    </svg>
  )
}

const NODE_TYPES = {
  "image-gen": GenerationCardNode,
  "video-gen": VideoGenerationNode,
  "text-note": TextNode,
  "text-response": TextResponseNode,
  "script-table": ScriptTableNode,
  "character-card": CharacterCardNode,
  "script-beat-card": ScriptBeatCardNode,
  outline: OutlineNode,
  "shot-script": ShotScriptNode,
}

const EDGE_TYPES = {
  ghost: GhostEdge,
}

function CanvasInner() {
  const { t } = useLocale()
  const navigate = useNavigate()
  const { projectId: routeProjectId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const shareToken = searchParams.get("share")
  const projectId = shareToken ? null : routeProjectId
  const shareReadOnly = !!shareToken
  const reloadFromServerRef = useRef(async () => {})
  const {
    isEditor,
    getSessionId,
    kickedNotice,
    clearKickedNotice,
    remoteSyncNotice,
    clearRemoteSyncNotice,
    editorPromotedNotice,
    clearEditorPromotedNotice,
    lockHolder,
    sessionReady,
    incomingEditRequest,
    editRequestPending,
    editRequestNotice,
    clearEditRequestNotice,
    requestEditPermission,
    respondEditRequest,
  } = useCanvasSession(projectId, {
    enabled: !shareToken && !!projectId,
    onRemoteUpdate: () => reloadFromServerRef.current(),
  })
  const readOnly = shareReadOnly || !isEditor
  const collabReadOnly = !shareReadOnly && !isEditor
  const readOnlyRef = useRef(readOnly)
  useEffect(() => {
    readOnlyRef.current = readOnly
  }, [readOnly])
  const [shareBanner, setShareBanner] = useState(readOnly)
  const commentMode = useCanvasStore((s) => s.commentMode)
  const setCommentMode = useCanvasStore((s) => s.setCommentMode)
  const commentTargetNodeId = useCanvasStore((s) => s.commentTargetNodeId)
  const setCommentTargetNodeId = useCanvasStore((s) => s.setCommentTargetNodeId)
  const [topbarToast, setTopbarToast] = useState(null)
  const [commentReadTick, setCommentReadTick] = useState(0)
  const [highlightMessageIds, setHighlightMessageIds] = useState([])
  const [agentOpen, setAgentOpen] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [fullscreenChrome, setFullscreenChrome] = useState(false)

  useEffect(() => {
    const onNativeChange = () => {
      if (!document.fullscreenElement) {
        setIsFullscreen(false)
        setFullscreenChrome(false)
      }
    }
    document.addEventListener("fullscreenchange", onNativeChange)
    return () => document.removeEventListener("fullscreenchange", onNativeChange)
  }, [])

  useEffect(() => {
    if (!isFullscreen) {
      setFullscreenChrome(false)
      return undefined
    }
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        setIsFullscreen(false)
        if (document.fullscreenElement) {
          void document.exitFullscreen().catch(() => {})
        }
      }
    }
    const onMove = (e) => {
      const nearTop = e.clientY <= 52
      const nearBottom = e.clientY >= window.innerHeight - 52
      setFullscreenChrome(nearTop || nearBottom)
    }
    document.addEventListener("keydown", onKeyDown)
    window.addEventListener("mousemove", onMove)
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      window.removeEventListener("mousemove", onMove)
    }
  }, [isFullscreen])

  const toggleFullscreen = useCallback(async () => {
    if (isFullscreen) {
      setIsFullscreen(false)
      if (document.fullscreenElement) {
        try {
          await document.exitFullscreen()
        } catch {
          /* ignore */
        }
      }
    } else {
      setIsFullscreen(true)
      try {
        await document.documentElement.requestFullscreen()
      } catch {
        /* 浏览器拒绝时仅 CSS 模拟全屏 */
      }
    }
  }, [isFullscreen])

  const [pickerMenu, setPickerMenu] = useState(null)
  const [importDocumentOpen, setImportDocumentOpen] = useState(false)
  const [contextMenu, setContextMenu] = useState(null)
  const pickerMenuRef = useRef(null)
  const connectingNodeRef = useRef(null)
  const screenplayHandlersRef = useRef({})
  const agentWorkflowRef = useRef({})
  const agentSendRef = useRef(null)
  const agentRefPickRef = useRef(null)
  const savePauseRef = useRef(false)

  const { user } = useAuth()
  const {
    threadsByNode,
    getThread,
    postComment,
    editMessage,
    removeMessage,
  } = useCanvasComments(projectId, { enabled: !shareToken && !!projectId, userId: user?.id })

  const unreadCommentNodes = useMemo(() => {
    void commentReadTick
    return countUnreadCommentNodes(projectId, threadsByNode, user?.id)
  }, [projectId, threadsByNode, commentReadTick, user?.id])

  useEffect(() => {
    if (!projectId) return undefined
    const onRead = (e) => {
      if (e.detail?.projectId === projectId) setCommentReadTick((n) => n + 1)
    }
    window.addEventListener("canvas-comment-read-changed", onRead)
    return () => window.removeEventListener("canvas-comment-read-changed", onRead)
  }, [projectId])

  useEffect(() => {
    if (!projectId || !commentTargetNodeId) return
    const thread = threadsByNode[commentTargetNodeId]
    if (thread?.messages?.length) {
      markNodeCommentsSeen(projectId, commentTargetNodeId, thread)
    }
    const mentionIds = getMentionHighlightIds(projectId, commentTargetNodeId, thread, user?.id)
    if (mentionIds.length) {
      setHighlightMessageIds((prev) => [...new Set([...prev, ...mentionIds])])
    }
  }, [projectId, commentTargetNodeId, threadsByNode, user?.id])
  const { screenToFlowPosition, getNode, fitView, setCenter, getZoom } = useReactFlow()
  const { x: vpX, y: vpY, zoom } = useViewport()
  const setCanvasId = useCanvasStore((s) => s.setCanvasId)
  const setProjectName = useCanvasStore((s) => s.setProjectName)
  const snapToGrid = useCanvasStore((s) => s.snapToGrid)
  const minimapOpen = useCanvasStore((s) => s.minimapOpen)
  const fetchAssets = useAssetStore((s) => s.fetchAssets)
  const assetLibraryOpen = useCanvasStore((s) => s.assetLibraryOpen)
  const setAssetLibraryOpen = useCanvasStore((s) => s.setAssetLibraryOpen)
  const genHistoryOpen = useCanvasStore((s) => s.genHistoryOpen)
  const setGenHistoryOpen = useCanvasStore((s) => s.setGenHistoryOpen)
  const theme = useCanvasStore((s) => s.theme)
  const setProjectTeamId = useCanvasStore((s) => s.setProjectTeamId)
  const projectTeamId = useCanvasStore((s) => s.projectTeamId)
  const projectName = useCanvasStore((s) => s.projectName)
  const allTeams = useTeamStore((s) => s.allTeams)
  const ensureTeamsLoaded = useTeamStore((s) => s.ensureTeamsLoaded)
  const [teamMembers, setTeamMembers] = useState([])
  const [migrateOpen, setMigrateOpen] = useState(false)
  const presenceEnabled = !shareReadOnly && !!projectId && !!user
  const canvasNavMode = useCanvasStore((s) => s.canvasNavMode)
  const navFlowProps = useMemo(
    () => getCanvasNavFlowProps(canvasNavMode),
    [canvasNavMode]
  )
  const connectionLineStyle = useMemo(
    () => (theme === "light"
      ? { stroke: "rgba(0,0,0,0.52)", strokeWidth: 1.5, strokeLinecap: "round" }
      : {
          stroke: "rgba(255,255,255,0.9)",
          strokeWidth: 1.5,
          strokeLinecap: "round",
          filter: "drop-shadow(0 0 3px rgba(255,255,255,0.7)) drop-shadow(0 0 8px rgba(255,255,255,0.35))",
        }),
    [theme]
  )

  const stopPollingRef = useRef(() => {})
  const stopPolling = useCallback((responseNodeId) => {
    stopPollingRef.current(responseNodeId)
  }, [])

  const runTextGenerationRef = useRef(async () => {})
  const runTextGeneration = useCallback(
    (...args) => runTextGenerationRef.current(...args),
    []
  )

  const updateResponseNodeDataRef = useRef(() => {})
  const updateResponseNodeData = useCallback(
    (...args) => updateResponseNodeDataRef.current(...args),
    []
  )

  const {
    nodes,
    edges,
    setNodes,
    setEdges,
    onNodesChange,
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
  } = useCanvasNodes({
    screenToFlowPosition,
    screenplayHandlersRef,
    stopPolling,
    runTextGeneration,
    updateResponseNodeData,
    getNode,
    readOnlyRef,
  })

  useEffect(() => {
    if (selectedNodeId) {
      useCanvasStore.getState().setLastFocusedNodeId(selectedNodeId)
    }
  }, [selectedNodeId])

  const dragPlaceSession = useCanvasStore((s) => s.dragPlaceSession)
  const { getCardPointerHandlers } = useCanvasDragPlace({
    createNode,
    setSelectedNodeId,
    raiseNodeToFront,
  })

  const {
    refSelectMode,
    exitRefSelectMode,
    enterRefSelectMode,
    setRefSelectHover,
    setRefSelectSelected,
    setRefSelectHighlight,
    resetReferencePickerState,
  } = useRefSelectMode(setSelectedNodeId)

  const {
    updateResponseNodeData: _updateResponseNodeData,
    runTextGeneration: _runTextGeneration,
    textRetryRef,
    patchNodeData,
    stopPolling: _stopPolling,
  } = useTextGeneration({
    setNodes,
    setEdges,
    getNode,
    buildData,
    setSelectedNodeId,
  })

  stopPollingRef.current = _stopPolling
  runTextGenerationRef.current = _runTextGeneration
  updateResponseNodeDataRef.current = _updateResponseNodeData

  const {
    pushHistory,
    undo,
    redo,
    resetHistory,
    onNodeDragStart: historyDragStart,
    onNodeDragStop: historyDragStop,
    wrapOnNodesChange,
    wrapOnEdgesChange,
  } = useCanvasHistory({
    nodesRef,
    edgesRef,
    setNodes,
    setEdges,
    buildData,
    buildOutlineData,
    textRetryRef,
    zIndexCounterRef,
    readOnlyRef,
    projectId,
  })

  useScreenplay({
    setNodes,
    setEdges,
    getNode,
    buildData,
    bumpZIndex,
    nodesRef,
    edgesRef,
    patchNodeData,
    screenplayHandlersRef,
    readOnlyRef,
  })

  const {
    runScriptTableRowGenerate,
    runScriptTableDirectImageGenerate,
    runScriptTableDirectVideoGenerate,
    runBeatCardRowGenerate,
    runScriptTableKeyframeGenerate,
    runScriptTableGenerateAll,
    runScriptTableGenerateAllVideo,
    runScriptTableRowVideoGenerate,
    patchScriptTableRow,
    patchBeatCard,
  } = useScriptTableGenerate({
    nodes,
    setNodes,
    setEdges,
    getNode,
    nodesRef,
    edgesRef,
    buildData,
    bumpZIndex,
  })

  const createBeatCardForRow = useCallback(
    (scriptTableNodeId, rowId) => {
      const scriptNode = nodesRef.current.find((n) => n.id === scriptTableNodeId)
      if (!scriptNode || scriptNode.type !== "script-table") return null
      const rows = sortScriptRows(scriptNode.data.rows || [])
      const row = rows.find((r) => r.id === rowId)
      if (!row) return null
      if (row.beatCardNodeId) {
        const existing = nodesRef.current.find((n) => n.id === row.beatCardNodeId)
        if (existing) return row.beatCardNodeId
      }
      const rowIndex = rows.findIndex((r) => r.id === rowId)
      const { beatCardId, node } = buildBeatCardCreatePayload(scriptNode, row, rowIndex)
      const z = bumpZIndex()
      const beatNode = {
        ...node,
        zIndex: z,
        data: buildData({ ...node.data, zIndex: z }),
        style: { zIndex: z },
      }
      setNodes((ns) => [...ns, beatNode])
      setEdges((es) =>
        addEdge(
          {
            id: `e-${scriptTableNodeId}-${beatCardId}-${Date.now()}`,
            source: scriptTableNodeId,
            target: beatCardId,
            sourceHandle: "src-right",
            targetHandle: "tgt",
            type: "ghost",
            animated: false,
          },
          es
        )
      )
      patchScriptTableRow(scriptTableNodeId, rowId, { beatCardNodeId: beatCardId })
      return beatCardId
    },
    [buildData, bumpZIndex, patchScriptTableRow, setNodes, setEdges]
  )

  const unlinkBeatCard = useCallback(
    (scriptTableNodeId, rowId, beatCardNodeId) => {
      patchScriptTableRow(scriptTableNodeId, rowId, { beatCardNodeId: null })
      setNodes((ns) => ns.filter((n) => n.id !== beatCardNodeId))
      setEdges((es) =>
        es.filter((e) => e.source !== beatCardNodeId && e.target !== beatCardNodeId)
      )
    },
    [patchScriptTableRow, setNodes, setEdges]
  )

  const focusBeatCard = useCallback(
    (beatCardNodeId) => {
      if (!beatCardNodeId) return
      setSelectedNodeId(beatCardNodeId)
      fitView({ nodes: [{ id: beatCardNodeId }], padding: 0.4, duration: 320, maxZoom: 1 })
    },
    [fitView, setSelectedNodeId]
  )

  agentWorkflowRef.current = {
    runTextGeneration: _runTextGeneration,
    onGenerateScriptTable: (outlineId) =>
      screenplayHandlersRef.current.onGenerateScriptTable?.(outlineId),
    getDefaultTextModelId: () => useModelStore.getState().textModels[0]?.id,
    getDefaultImageModelId: () => useModelStore.getState().imageModels[0]?.id,
    getDefaultVideoModelId: () => useModelStore.getState().videoModels[0]?.id,
    patchScriptTableRow,
    runScriptTableRowGenerate,
    runScriptTableDirectImageGenerate,
    runScriptTableRowVideoGenerate,
    createBeatCardForRow,
    patchBeatCard,
    getNodes: () => nodesRef.current,
    getEdges: () => edgesRef.current,
    setNodes,
    setEdges,
    fitView: (opts) => fitView(opts),
    setCenter: (x, y, opts) => setCenter(x, y, opts),
  }

  const { reloadFromServer } = useCanvasSave({
    projectId,
    nodes,
    edges,
    setNodes,
    setEdges,
    buildData,
    buildOutlineData,
    zIndexCounterRef,
    textRetryRef,
    shareToken,
    readOnly,
    getSessionId,
    onShareLoaded: (name) => {
      if (name) useCanvasStore.getState().setProjectName(name)
      setShareBanner(true)
    },
    onProjectLoaded: (res) => {
      if (res?.id) setCanvasId(res.id)
      resetHistory()
    },
    onVersionConflict: (detail) => {
      if (detail?.merged) {
        setTopbarToast(t("canvas.conflict.synced"))
      } else {
        setTopbarToast(t("canvas.conflict.syncFail"))
      }
    },
    savePauseRef,
  })

  useEffect(() => {
    reloadFromServerRef.current = reloadFromServer
  }, [reloadFromServer])

  useEffect(() => {
    if (!shareToken && !projectId) {
      navigate("/workspace", { replace: true })
    }
  }, [shareToken, projectId, navigate])

  useEffect(() => {
    if (!projectId || shareToken) return
    setNodes([])
    setEdges([])
    setSelectedNodeId(null)
    setProjectName(t("ws.default.canvasName"))
  }, [projectId, shareToken, setNodes, setEdges, setSelectedNodeId, setProjectName, t])

  useEffect(() => {
    if (!topbarToast) return undefined
    const t = setTimeout(() => setTopbarToast(null), 2200)
    return () => clearTimeout(t)
  }, [topbarToast])

  useEffect(() => {
    if (!remoteSyncNotice) return undefined
    const timer = setTimeout(() => clearRemoteSyncNotice(), 5000)
    return () => clearTimeout(timer)
  }, [remoteSyncNotice, clearRemoteSyncNotice])

  useEffect(() => {
    if (!editorPromotedNotice) return undefined
    const timer = setTimeout(() => clearEditorPromotedNotice(), 8000)
    return () => clearTimeout(timer)
  }, [editorPromotedNotice, clearEditorPromotedNotice])

  const clearCanvas = useCallback(() => {
    setNodes([])
    setEdges([])
    setSelectedNodeId(null)
    setTimeout(() => fitView({ padding: 0.25, duration: 280 }), 60)
  }, [setNodes, setEdges, setSelectedNodeId, fitView])

  const handleOrganizeCanvas = useCallback(() => {
    if (readOnly || nodes.length === 0) return
    savePauseRef.current = true
    setNodes((ns) => organizeCanvasNodes(ns, edges))
    requestAnimationFrame(() => {
      fitView({ padding: 0.22, duration: 280, maxZoom: 1 })
      setTimeout(() => {
        savePauseRef.current = false
      }, 600)
    })
  }, [readOnly, nodes.length, edges, setNodes, fitView])

  const handleRecenterViewport = useCallback(() => {
    const lastId = useCanvasStore.getState().lastFocusedNodeId
    if (lastId && getNode(lastId)) {
      fitView({
        nodes: [{ id: lastId }],
        padding: 0.32,
        duration: 420,
        maxZoom: 1.15,
      })
      return
    }
    if (nodes.length > 0) {
      fitView({ nodes: nodes.map((n) => ({ id: n.id })), padding: 0.3, duration: 420 })
    }
  }, [getNode, fitView, nodes])

  const handleNewProject = useCallback(async () => {
    if (!window.confirm(t("canvas.project.newConfirm"))) return
    try {
      const teamId = getActiveTeamId()
      const created = await createCanvasProject({
        name: t("ws.default.canvasName"),
        team_id: teamId,
      })
      navigate(`/canvas/${created.id}`)
    } catch (err) {
      console.error(err)
      window.alert(t("canvas.project.createFail"))
    }
  }, [navigate, t])

  const handleDeleteProject = useCallback(async () => {
    if (!projectId) return
    if (!window.confirm(t("canvas.project.deleteConfirm"))) return
    try {
      await deleteCanvasProject(projectId)
      navigate("/workspace")
    } catch (err) {
      console.error(err)
      window.alert(t("canvas.project.deleteFail"))
    }
  }, [projectId, navigate, t])

  const migratableTeams = useMemo(() => getMigratableTeams(allTeams), [allTeams])
  const canMigrateToTeam = !shareReadOnly && !projectTeamId && migratableTeams.length > 0

  useEffect(() => {
    if (canMigrateToTeam) ensureTeamsLoaded()
  }, [canMigrateToTeam, ensureTeamsLoaded])

  const handleMigrateConfirm = useCallback(async (teamId) => {
    if (!projectId) return
    const team = migratableTeams.find((item) => item.id === teamId)
    try {
      await migrateCanvasProjectToTeam(projectId, teamId)
      setProjectTeamId(teamId)
      setMigrateOpen(false)
      setTopbarToast(t("ws.project.migrateSuccess", { team: team?.name || "" }))
    } catch (err) {
      console.error(err)
      window.alert(t("ws.project.migrateFail"))
      throw err
    }
  }, [projectId, migratableTeams, setProjectTeamId, t])

  const handleOpenAssets = useCallback((pref) => {
    useCanvasStore.getState().openAssetLibrary(pref)
  }, [])

  const handleStarterTemplate = useCallback((message) => {
    if (readOnly || !message) return
    setAgentOpen(true)
    window.setTimeout(() => {
      agentSendRef.current?.(message)
    }, 0)
  }, [readOnly])

  const handleCommentNodeClick = useCallback((nodeId) => {
    if (!commentMode) return
    setCommentTargetNodeId(nodeId)
    setSelectedNodeId(null)
  }, [commentMode, setCommentTargetNodeId, setSelectedNodeId])

  const handleCloseCommentPanel = useCallback(() => {
    setCommentTargetNodeId(null)
  }, [setCommentTargetNodeId])

  useEffect(() => {
    if (!projectId) return
    setCommentMode(false)
    setCommentTargetNodeId(null)
  }, [projectId, setCommentMode, setCommentTargetNodeId])

  const openCommentNode = searchParams.get("openComment")
  const highlightParam = searchParams.get("highlightComments")

  useEffect(() => {
    if (!highlightParam) return
    const ids = highlightParam.split(",").map((s) => s.trim()).filter(Boolean)
    if (ids.length) setHighlightMessageIds(ids)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete("highlightComments")
      return next
    }, { replace: true })
  }, [highlightParam, setSearchParams])

  useEffect(() => {
    if (!highlightMessageIds.length) return undefined
    const ids = [...highlightMessageIds]
    const nodeId = commentTargetNodeId
    const timer = window.setTimeout(() => {
      if (projectId && nodeId) markMentionsSeen(projectId, nodeId, ids)
      setHighlightMessageIds([])
    }, 3200)
    return () => window.clearTimeout(timer)
  }, [highlightMessageIds, projectId, commentTargetNodeId])

  useEffect(() => {
    if (!openCommentNode || shareReadOnly || !sessionReady) return
    setCommentMode(true)
    setCommentTargetNodeId(openCommentNode)
  }, [openCommentNode, shareReadOnly, sessionReady, setCommentMode, setCommentTargetNodeId])

  useEffect(() => {
    if (!projectId || !commentTargetNodeId || shareReadOnly) return undefined
    let cancelled = false
    markNodeMentionNotificationsRead(projectId, commentTargetNodeId).then(async ({ ids, commentIds }) => {
      if (cancelled) return
      if (ids.length) {
        try {
          const data = await fetchNotifications({ limit: 1 })
          emitNotificationUnread(data?.unread_count ?? 0)
        } catch {
          /* ignore */
        }
      }
      if (commentIds.length) {
        setHighlightMessageIds((prev) => [...new Set([...prev, ...commentIds])])
      }
    })
    return () => { cancelled = true }
  }, [projectId, commentTargetNodeId, shareReadOnly])

  useEffect(() => {
    const teamId = projectTeamId || getActiveTeamId()
    if (!teamId) {
      setTeamMembers([])
      return undefined
    }
    let cancelled = false
    listTeamMembers(teamId)
      .then((members) => {
        if (!cancelled) setTeamMembers(Array.isArray(members) ? members : [])
      })
      .catch(() => {
        if (!cancelled) setTeamMembers([])
      })
    return () => { cancelled = true }
  }, [projectTeamId])

  useEffect(() => {
    if (!projectId || !user?.id) return undefined
    const off = canvasWsManager.addListener((msg) => {
      if (msg?.type !== "comment_mention") return
      if (Number(msg.recipient_user_id) !== Number(user.id)) return
      const who = personLabel(msg.mentioner, t("canvas.topbar.otherUser"))
      setTopbarToast(t("canvas.session.mentionToast", { who }))
      window.setTimeout(() => setTopbarToast(null), 4500)
    })
    return off
  }, [projectId, user?.id, t])

  const { members: presenceMembers } = useCanvasPresence(projectId, {
    enabled: presenceEnabled,
    isEditor,
    username: user?.username || "",
  })

  useEffect(() => {
    if (!projectId || shareReadOnly) return undefined
    let cancelled = false
    loadCanvasProject(projectId)
      .then((res) => {
        if (cancelled) return
        setProjectTeamId(res?.team_id || null)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [projectId, shareReadOnly, setProjectTeamId])

  const commentDisplayName = useMemo(
    () => readDisplayName(user?.username),
    [user?.username]
  )

  useEffect(() => {
    if (commentMode) exitRefSelectMode()
  }, [commentMode, exitRefSelectMode])

  const commentNodeLabel = useMemo(() => {
    if (!commentTargetNodeId) return ""
    const n = nodes.find((x) => x.id === commentTargetNodeId)
    return n?.data?.label || n?.type || commentTargetNodeId
  }, [commentTargetNodeId, nodes])

  const commentAnchor = useMemo(() => {
    if (!commentTargetNodeId) return null
    const node = getNode(commentTargetNodeId)
    if (!node) return null
    const rect = getCommentAnchorRect(node)
    if (!rect) return null
    return {
      left: rect.x * zoom + vpX,
      top: rect.y * zoom + vpY,
      width: rect.width * zoom,
      height: rect.height * zoom,
    }
  }, [commentTargetNodeId, getNode, vpX, vpY, zoom])

  const {
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
  } = useCanvasInteraction({
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
    commentMode,
    onCommentNodeClick: handleCommentNodeClick,
    pushHistory,
    readOnly,
  })

  const handleNodesChange = useCallback(
    (changes) => wrapOnNodesChange(changes, onNodesChange),
    [wrapOnNodesChange, onNodesChange]
  )

  const handleEdgesChangeWrapped = useCallback(
    (changes) => wrapOnEdgesChange(changes, onEdgesChange),
    [wrapOnEdgesChange, onEdgesChange]
  )

  const handleNodeDragStartCombined = useCallback(
    (e, node) => {
      historyDragStart()
      handleNodeDragStart(e, node)
    },
    [historyDragStart, handleNodeDragStart]
  )

  const handleNodeDragStopCombined = useCallback(
    (e, node) => {
      handleNodeDragStop(e, node)
      historyDragStop()
    },
    [handleNodeDragStop, historyDragStop]
  )

  useEffect(() => {
    if (readOnly) return undefined
    const onKeyDown = (e) => {
      if (isCanvasShortcutTarget(e.target)) return
      const mod = e.ctrlKey || e.metaKey
      if (!mod) return
      const key = e.key.toLowerCase()
      if (key === "z") {
        e.preventDefault()
        if (e.shiftKey) {
          if (redo()) setSelectedNodeId(null)
        } else if (undo()) {
          setSelectedNodeId(null)
        }
      } else if (key === "y") {
        e.preventDefault()
        if (redo()) setSelectedNodeId(null)
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [readOnly, undo, redo, setSelectedNodeId])

  useEffect(() => {
    if (localStorage.getItem("access_token")) {
      fetchAssets()
    }
  }, [fetchAssets])

  useEffect(() => {
    if (projectId) setCanvasId(projectId)
  }, [projectId, setCanvasId])

  useEffect(() => {
    if (!assetLibraryOpen && !genHistoryOpen) return undefined
    const closeFlyouts = (e) => {
      if (e.target.closest(".alf-flyout, .ghf-flyout, .clt-toolbar, .clt-add-menu, .clt-avatar-menu")) {
        return
      }
      setAssetLibraryOpen(false)
      setGenHistoryOpen(false)
    }
    document.addEventListener("pointerdown", closeFlyouts)
    return () => document.removeEventListener("pointerdown", closeFlyouts)
  }, [assetLibraryOpen, genHistoryOpen, setAssetLibraryOpen, setGenHistoryOpen])

  useEffect(() => { pickerMenuRef.current = pickerMenu }, [pickerMenu])

  useEffect(() => {
    const handler = (e) => {
      if (e.key !== "Escape") return
      if (refSelectMode.active) { exitRefSelectMode(); return }
      if (commentMode) {
        if (commentTargetNodeId) {
          setCommentTargetNodeId(null)
          return
        }
        setCommentMode(false)
        return
      }
      dismissPickerMenu()
      setContextMenu(null)
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [
    refSelectMode.active,
    exitRefSelectMode,
    commentMode,
    commentTargetNodeId,
    setCommentMode,
    setCommentTargetNodeId,
    dismissPickerMenu,
  ])

  const refSelectCtx = useMemo(() => {
    const selectReference = ({ nodeId: pickedNodeId, imageIndex, imageUrl, imageId, label }) => {
      const targetId = refSelectMode.sourceNodeId
      if (!targetId || !imageUrl || imageIndex === undefined || imageIndex === null) return
      const pickTarget = refSelectMode.pickTarget || "referenceImage"
      const refItem = {
        nodeId: pickedNodeId,
        imageIndex,
        imageUrl,
        imageId: imageId ?? `${pickedNodeId}_${imageIndex}`,
        label: label && String(label).trim() ? String(label).trim() : "Image",
      }

      if (targetId === AGENT_REF_SOURCE_ID) {
        agentRefPickRef.current?.(refItem)
        exitRefSelectMode()
        return
      }

      setNodes((ns) =>
        ns.map((n) => {
          if (n.id !== targetId) return n

          if (n.type === "script-table") {
            if (pickTarget.startsWith("castNew:")) {
              const rest = pickTarget.slice("castNew:".length)
              const colon = rest.indexOf(":")
              const castType = rest.slice(0, colon) === "scene" ? "scene" : "character"
              const castName = decodeURIComponent(rest.slice(colon + 1) || "")
              if (!castName.trim()) return n
              const castLibrary = normalizeCastLibrary([
                ...(n.data.castLibrary || []),
                {
                  id: makeCastRefId(),
                  name: castName.trim(),
                  type: castType,
                  imageUrl,
                },
              ], { requireImage: false })
              return { ...n, data: { ...n.data, castLibrary } }
            }
            if (pickTarget.startsWith("sceneNew:")) {
              const sceneName = decodeURIComponent(pickTarget.slice("sceneNew:".length) || "")
              if (!sceneName.trim()) return n
              const sceneLibrary = normalizeSceneLibrary([
                ...(n.data.sceneLibrary || []),
                {
                  id: makeSceneRefId(),
                  name: sceneName.trim(),
                  imageUrl,
                },
              ], { requireImage: false })
              return { ...n, data: { ...n.data, sceneLibrary } }
            }
            if (pickTarget.startsWith("sceneAssign:")) {
              const sceneId = pickTarget.slice("sceneAssign:".length)
              if (!sceneId) return n
              const sceneLibrary = touchLibraryById(
                normalizeSceneLibrary(
                  (n.data.sceneLibrary || []).map((s) =>
                    s.id === sceneId
                      ? { ...s, imageUrl, pendingImage: false }
                      : s
                  ),
                  { requireImage: false }
                ),
                sceneId
              )
              return { ...n, data: { ...n.data, sceneLibrary } }
            }
            if (pickTarget.startsWith("castAssign:")) {
              const castId = pickTarget.slice("castAssign:".length)
              if (!castId) return n
              const castLibrary = touchLibraryById(
                normalizeCastLibrary(
                  (n.data.castLibrary || []).map((c) =>
                    c.id === castId
                      ? { ...c, imageUrl, pendingImage: false }
                      : c
                  ),
                  { requireImage: false }
                ),
                castId
              )
              return { ...n, data: { ...n.data, castLibrary } }
            }
          }

          if (n.type === "video-gen") {
            if (pickTarget === "first") {
              const keyframes = { ...(n.data.keyframes || DEFAULT_KEYFRAMES), first: refItem }
              return { ...n, data: { ...n.data, referenceMode: "keyframe", keyframes } }
            }
            if (pickTarget === "last") {
              const keyframes = { ...(n.data.keyframes || DEFAULT_KEYFRAMES), last: refItem }
              return { ...n, data: { ...n.data, referenceMode: "keyframe", keyframes } }
            }
            if (pickTarget === "freeref") {
              const freeRefs = [...(n.data.freeRefs || [])]
              if (freeRefs.length >= 5 || freeRefs.some((r) => r.imageId === refItem.imageId)) {
                return n
              }
              return {
                ...n,
                data: { ...n.data, referenceMode: "freeref", freeRefs: [...freeRefs, refItem] },
              }
            }
          }

          const existing = Array.isArray(n.data.referenceImages)
            ? n.data.referenceImages
            : n.data.referenceRef
              ? [n.data.referenceRef]
              : n.data.referenceImageUrl || n.data.referenceImage
                ? [{
                    ...refItem,
                    imageUrl: n.data.referenceImageUrl || n.data.referenceImage,
                  }]
                : []
          if (
            existing.length >= 5
            || existing.some(
              (r) => (r.imageId || `${r.nodeId}_${r.imageIndex ?? 0}`)
                === (refItem.imageId || `${refItem.nodeId}_${refItem.imageIndex ?? 0}`)
            )
          ) {
            return n
          }
          const next = [...existing, refItem]
          const first = next[0]
          return {
            ...n,
            data: {
              ...n.data,
              referenceImages: next,
              referenceImage: first?.imageUrl ?? imageUrl,
              referenceImageUrl: first?.imageUrl ?? imageUrl,
              referenceRef: first ?? refItem,
            },
          }
        })
      )
      if (
        (pickTarget.startsWith("castAssign:") || pickTarget.startsWith("sceneAssign:"))
        && refSelectMode.pickMeta?.onComplete
      ) {
        try {
          refSelectMode.pickMeta.onComplete(imageUrl)
        } catch (err) {
          console.error("castAssign onComplete failed", err)
        }
      }
      exitRefSelectMode()
      setSelectedNodeId(targetId)
    }

    return {
      mode: refSelectMode,
      enter: enterRefSelectMode,
      exit: exitRefSelectMode,
      resetReferencePickerState,
      setHoverRef: setRefSelectHover,
      setSelectedRef: setRefSelectSelected,
      setHighlightRef: setRefSelectHighlight,
      selectReference,
      selectNode: (imageUrl, pickedNodeId) => {
        const picked = nodes.find((n) => n.id === pickedNodeId)
        const pickedLabel =
          (picked?.data?.label && String(picked.data.label).trim()) || "Image"
        selectReference({
          nodeId: pickedNodeId,
          imageIndex: 0,
          imageUrl,
          imageId: `${pickedNodeId}_0`,
          label: pickedLabel,
        })
      },
    }
  }, [
    refSelectMode,
    enterRefSelectMode,
    exitRefSelectMode,
    resetReferencePickerState,
    setRefSelectHover,
    setRefSelectSelected,
    setRefSelectHighlight,
    setNodes,
    nodes,
    setSelectedNodeId,
  ])

  const scriptTableSyncRef = useRef(new Map())

  useEffect(() => {
    const pendingRowUpdates = []
    const pendingBeatUpdates = []

    for (const n of nodes) {
      if (n.type !== "script-table" || !Array.isArray(n.data.rows)) continue
      for (const row of n.data.rows) {
        const targets = []
        if (row.directImageGenNodeId) {
          targets.push({ kind: "direct", row, genId: row.directImageGenNodeId })
        }
        const beatCard = row.beatCardNodeId
          ? nodes.find((x) => x.id === row.beatCardNodeId && x.type === BEAT_CARD_NODE_TYPE)
          : null
        const beatKfs = beatCard
          ? asKeyframeArray(beatCard.data?.keyframes)
          : asKeyframeArray(row.keyframes)
        for (const kf of beatKfs) {
          if (kf.imageGenNodeId) {
            targets.push({
              kind: "kf",
              row,
              kf,
              beatCardNodeId: beatCard?.id || null,
            })
          }
        }

        for (const target of targets) {
          const genId = target.kind === "direct" ? target.genId : target.kf.imageGenNodeId
          const syncId =
            target.kind === "direct"
              ? `direct:${row.id}`
              : `${row.id}:${target.kf.id}`
          const imgNode = nodes.find((x) => x.id === genId)
          if (!imgNode) continue
          const imgStatus = imgNode.data?.status
          const resultUrl =
            imgNode.data?.results?.find(Boolean) || imgNode.data?.imageUrl || null
          const syncKey = `${imgStatus}|${resultUrl || ""}|${imgNode.data?.error || ""}`
          if (scriptTableSyncRef.current.get(syncId) === syncKey) continue
          scriptTableSyncRef.current.set(syncId, syncKey)

          let nextStatus =
            target.kind === "direct"
              ? row.directStatus
              : target.kf.status
          if (imgStatus === "pending" || imgStatus === "generating") {
            nextStatus = "generating"
          } else if (imgStatus === "completed" && resultUrl) {
            nextStatus = "completed"
          } else if (imgStatus === "failed" || imgStatus === "error") {
            nextStatus = "failed"
          }

          const patch = {}
          if (
            nextStatus
            !== (target.kind === "direct" ? row.directStatus : target.kf.status)
          ) {
            patch.status = nextStatus
          }
          if (resultUrl) {
            const cleanUrl = stripMediaTicket(resultUrl)
            const prevUrl =
              target.kind === "direct" ? row.directResultUrl : target.kf.resultUrl
            if (cleanUrl && prevUrl !== cleanUrl) patch.resultUrl = cleanUrl
          } else if (
            (imgStatus === "pending" || imgStatus === "generating")
            && (target.kind === "direct" ? row.directResultUrl : target.kf.resultUrl)
          ) {
            patch.resultUrl = null
          }
          if (imgNode.data?.error) {
            const prevErr = target.kind === "direct" ? row.error : target.kf.error
            if (prevErr !== imgNode.data.error) patch.error = imgNode.data.error
          }
          if (Object.keys(patch).length === 0) continue

          if (target.kind === "direct") {
            pendingRowUpdates.push({
              scriptTableNodeId: n.id,
              rowId: row.id,
              patch: {
                directStatus: patch.status,
                directResultUrl:
                  patch.resultUrl !== undefined ? patch.resultUrl : row.directResultUrl,
                status: patch.status,
                resultUrl: patch.resultUrl !== undefined ? patch.resultUrl : row.directResultUrl,
                error: patch.error ?? row.error,
              },
            })
          } else if (target.beatCardNodeId) {
            pendingBeatUpdates.push({
              beatCardNodeId: target.beatCardNodeId,
              keyframeId: target.kf.id,
              patch,
            })
          } else {
            pendingRowUpdates.push({
              scriptTableNodeId: n.id,
              rowId: row.id,
              keyframeId: target.kf.id,
              patch,
            })
          }
        }
      }
    }

    for (const n of nodes) {
      if (n.type !== "script-table" || !Array.isArray(n.data.rows)) continue
      for (const row of n.data.rows) {
        const videoTargets = []
        if (row.directVideoGenNodeId) {
          videoTargets.push({ row, genId: row.directVideoGenNodeId })
        }
        const beatCard = row.beatCardNodeId
          ? nodes.find((x) => x.id === row.beatCardNodeId && x.type === BEAT_CARD_NODE_TYPE)
          : null
        if (beatCard?.data?.videoGenNodeId) {
          videoTargets.push({ row, genId: beatCard.data.videoGenNodeId })
        }
        for (const vt of videoTargets) {
          const vidNode = nodes.find((x) => x.id === vt.genId)
          if (!vidNode) continue
          const vidStatus = vidNode.data?.status
          if (vidStatus !== "failed" && vidStatus !== "error" && vidStatus !== "timeout") continue
          const err = vidNode.data?.error
          if (!err || row.error === err) continue
          const syncId = `video:${vt.genId}|${err}`
          if (scriptTableSyncRef.current.get(syncId) === syncId) continue
          scriptTableSyncRef.current.set(syncId, syncId)
          pendingRowUpdates.push({
            scriptTableNodeId: n.id,
            rowId: row.id,
            patch: { error: err, status: "failed" },
          })
        }
      }
    }

    if (pendingRowUpdates.length === 0 && pendingBeatUpdates.length === 0) return
    setNodes((ns) =>
      ns.map((node) => {
        const rowHits = pendingRowUpdates.filter((u) => u.scriptTableNodeId === node.id)
        const beatHits = pendingBeatUpdates.filter((u) => u.beatCardNodeId === node.id)
        if (rowHits.length === 0 && beatHits.length === 0) return node

        if (node.type === "script-table" && rowHits.length > 0) {
          const rows = (node.data.rows || []).map((row) => {
            const hits = rowHits.filter((u) => u.rowId === row.id)
            if (hits.length === 0) return row
            let nextRow = { ...row }
            for (const upd of hits) {
              if (upd.keyframeId) {
                const keyframes = (nextRow.keyframes || []).map((kf) =>
                  kf.id === upd.keyframeId ? { ...kf, ...upd.patch } : kf
                )
                nextRow = { ...nextRow, keyframes }
              } else {
                nextRow = { ...nextRow, ...upd.patch }
              }
            }
            return syncRowFromKeyframes(nextRow)
          })
          return { ...node, data: { ...node.data, rows } }
        }

        if (node.type === BEAT_CARD_NODE_TYPE && beatHits.length > 0) {
          let nextData = { ...node.data }
          for (const upd of beatHits) {
            const keyframes = (nextData.keyframes || []).map((kf) =>
              kf.id === upd.keyframeId ? { ...kf, ...upd.patch } : kf
            )
            nextData = syncBeatCardFromKeyframes({ ...nextData, keyframes })
          }
          return { ...node, data: nextData }
        }

        return node
      })
    )
  }, [nodes, setNodes])

  const canvasActions = useMemo(() => ({
    openPickerAt: (x, y, opts = {}) => setPickerMenu({ x, y, ...opts }),
    runScriptTableRowGenerate,
    runScriptTableDirectImageGenerate,
    runScriptTableDirectVideoGenerate,
    runBeatCardRowGenerate,
    runScriptTableKeyframeGenerate,
    runScriptTableGenerateAll,
    runScriptTableGenerateAllVideo,
    runScriptTableRowVideoGenerate,
    createBeatCardForRow,
    unlinkBeatCard,
    focusBeatCard,
  }), [
    runScriptTableRowGenerate,
    runScriptTableDirectImageGenerate,
    runScriptTableDirectVideoGenerate,
    runBeatCardRowGenerate,
    runScriptTableKeyframeGenerate,
    runScriptTableGenerateAll,
    runScriptTableGenerateAllVideo,
    runScriptTableRowVideoGenerate,
    createBeatCardForRow,
    unlinkBeatCard,
    focusBeatCard,
  ])

  const hasNodes = nodes.length > 0

  const nodesWithRefClass = useMemo(() => {
    if (!refSelectMode.active) return nodes
    if (refSelectMode.pickTarget === "referenceImage") {
      const srcId = refSelectMode.sourceNodeId
      return nodes.map((n) => {
        if (n.id === srcId) return n
        const d = n.data || {}
        const rawResults = Array.isArray(d.results) ? d.results : []
        const hasImage = !!(
          d.uploadedImage
          || d.imageUrl
          || d.generatedImage
          || d.resultUrl
          || rawResults.some(Boolean)
        )
        const isSelectable = n.type === "image-gen" && hasImage
        return isSelectable ? n : { ...n, className: `${n.className || ""} ref-select-dim`.trim() }
      })
    }
    const srcId = refSelectMode.sourceNodeId
    return nodes.map((n) => {
      if (n.id === srcId) return n
      const d = n.data || {}
      const rawResults = Array.isArray(d.results) ? d.results : []
      const hasImage = !!(
        d.uploadedImage
        || d.imageUrl
        || d.generatedImage
        || d.resultUrl
        || rawResults.some(Boolean)
      )
      const isSelectable = n.type === "image-gen" && hasImage
      return isSelectable ? n : { ...n, className: `${n.className || ""} ref-select-dim`.trim() }
    })
  }, [nodes, refSelectMode])

  const nodesWithCommentClass = useMemo(() => {
    if (!commentMode) return nodesWithRefClass
    return nodesWithRefClass.map((n) => ({
      ...n,
      className: `${n.className || ""} comment-select-target`.trim(),
    }))
  }, [nodesWithRefClass, commentMode])

  const flowNodes = useMemo(
    () =>
      nodesWithCommentClass.map((n) => {
        const normalized = normalizeCanvasNode(n)
        const z = normalized.zIndex ?? normalized.data?.zIndex ?? normalized.style?.zIndex ?? 0
        return {
          ...normalized,
          data: { ...normalized.data, readOnly },
          zIndex: z,
          style: { ...normalized.style, zIndex: z },
        }
      }),
    [nodesWithCommentClass, readOnly]
  )

  const imageRefCandidates = useMemo(() => {
    if (!refSelectMode.active || refSelectMode.pickTarget !== "referenceImage") return []
    const srcId = refSelectMode.sourceNodeId
    const list = []
    nodes.forEach((node) => {
      if (node.id === srcId || node.type !== "image-gen") return
      getImageNodeImages(node).forEach((img) => list.push(img))
    })
    return list
  }, [nodes, refSelectMode.active, refSelectMode.pickTarget, refSelectMode.sourceNodeId])

  const showImageReferencePicker =
    refSelectMode.active && refSelectMode.pickTarget === "referenceImage"

  const handleSwitchTextScreenplay = useCallback(() => {
    if (!selectedNodeId) return
    const n = getNode(selectedNodeId)
    if (n?.type === "text-note" && n.data?.onUpdate) {
      n.data.onUpdate(selectedNodeId, { textMode: TEXT_MODES.SCREENPLAY })
    }
  }, [selectedNodeId, getNode])

  return (
    <PromptIntentGateProvider onSwitchTextScreenplay={handleSwitchTextScreenplay}>
    <ReferenceSelectContext.Provider value={refSelectCtx}>
    <CanvasActionsContext.Provider value={canvasActions}>
    <div
      className={`rf-page rf-page--${theme} rf-page--nav-${canvasNavMode}${selectedNodeId ? " rf-page--node-focused" : ""}${agentOpen ? " rf-page--agent-open" : ""}${isFullscreen ? " rf-page--fullscreen" : ""}${isFullscreen && fullscreenChrome ? " rf-page--fullscreen-chrome" : ""}${pickerMenu?.fromEdge ? " picker-open" : ""}${refSelectMode.active ? " ref-select-active" : ""}${commentMode ? " comment-select-active" : ""}`}
      onDoubleClick={handlePaneDblClick}
      onDragOver={handleFlyoutDragOver}
      onDrop={handleFlyoutDrop}
    >
      <ReactFlow
        nodes={flowNodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onConnect={onConnect}
        onEdgesChange={handleEdgesChangeWrapped}
        onConnectStart={onConnectStart}
        onConnectEnd={onConnectEnd}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        nodesDraggable={!refSelectMode.active && !commentMode && !readOnly}
        nodesConnectable={!commentMode && !readOnly}
        snapToGrid={snapToGrid && !commentMode && !readOnly}
        snapGrid={[24, 24]}
        fitView={false}
        proOptions={{ hideAttribution: true }}
        deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
        onPaneClick={handlePaneClick}
        onDragOver={handleFlyoutDragOver}
        onDrop={handleFlyoutDrop}
        onNodeClick={handleNodeClick}
        onNodeDragStart={handleNodeDragStartCombined}
        onNodeDragStop={handleNodeDragStopCombined}
        onContextMenu={handlePaneContextMenu}
        minZoom={0.15}
        maxZoom={2.5}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        zoomOnDoubleClick={false}
        selectNodesOnDrag={false}
        {...navFlowProps}
        connectionRadius={60}
        connectionLineStyle={connectionLineStyle}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1.5}
          color={theme === "dark" ? "#333333" : "#bbbbbb"}
        />
        {minimapOpen && (
          <MiniMap
            className="canvas-minimap"
            nodeColor={theme === "dark" ? "#4a4a4a" : "#c8c8c8"}
            maskColor={theme === "dark" ? "rgba(0, 0, 0, 0.42)" : "rgba(255, 255, 255, 0.48)"}
            maskStrokeColor={theme === "dark" ? "#6b6b6b" : "#a8a8a8"}
            maskStrokeWidth={2}
            pannable
            zoomable
          />
        )}
        {commentMode && (
          <Panel position="top-left" className="comment-select-backdrop-panel">
            <div className="comment-select-backdrop" aria-hidden />
          </Panel>
        )}
        {!shareReadOnly && (
          <CanvasCommentMarkers
            projectId={projectId}
            threadsByNode={threadsByNode}
            commentMode={commentMode}
            activeNodeId={commentTargetNodeId}
            currentUserId={user?.id}
            username={user?.username}
            readTick={commentReadTick}
            onOpen={(nodeId) => {
              if (!commentMode) setCommentMode(true)
              setCommentTargetNodeId(nodeId)
            }}
          />
        )}
      </ReactFlow>

      {refSelectMode.active && (
        <div className="ref-select-banner" onClick={(e) => e.stopPropagation()}>
          <span>{showImageReferencePicker ? t("canvas.ref.banner") : t("canvas.ref.pick")}</span>
          <div className="ref-select-banner-sep" />
          <button className="ref-select-exit-btn nodrag" onClick={exitRefSelectMode}>{t("canvas.ref.exit")}</button>
        </div>
      )}

      <ImageReferencePicker
        open={showImageReferencePicker}
        images={imageRefCandidates}
        selectedRef={refSelectMode.selectedRef}
        hoverRef={refSelectMode.hoverRef}
        onHover={setRefSelectHover}
        onSelect={setRefSelectSelected}
        onConfirm={refSelectCtx.selectReference}
        onCancel={exitRefSelectMode}
        onReset={resetReferencePickerState}
      />

      {commentMode && (
        <div className="comment-select-banner" onClick={(e) => e.stopPropagation()}>
          <span>{t("canvas.comment.banner")}</span>
          <div className="ref-select-banner-sep" />
          <button
            type="button"
            className="ref-select-exit-btn nodrag"
            onClick={() => {
              setCommentTargetNodeId(null)
              setCommentMode(false)
            }}
          >
            {t("canvas.comment.exit")}
          </button>
        </div>
      )}

      <div className={`rf-overlay${refSelectMode.active || commentMode ? " rf-overlay--dimmed" : ""}`}>
        <CanvasTopbar
          projectId={projectId}
          nodes={nodes}
          edges={edges}
          readOnly={readOnly}
          collabReadOnly={collabReadOnly}
          lockHolder={lockHolder}
          presenceMembers={presenceMembers}
          presenceEnabled={presenceEnabled}
          agentOpen={agentOpen}
          agentReadOnly={readOnly}
          onToggleAgent={
            projectId && !readOnly ? () => setAgentOpen((v) => !v) : undefined
          }
          onShareToast={setTopbarToast}
          mentionToast={topbarToast}
          onNewProject={handleNewProject}
          onDeleteProject={handleDeleteProject}
          onMigrateToTeam={canMigrateToTeam ? () => setMigrateOpen(true) : undefined}
        />
        {collabReadOnly && lockHolder && (
          <div className="ctb-viewer-banner">
            <span>
              {t("canvas.session.viewerBanner", {
                who: personLabel(lockHolder, t("canvas.topbar.otherUser")),
              })}
            </span>
            <button
              type="button"
              className="ctb-viewer-banner__btn"
              disabled={editRequestPending}
              onClick={requestEditPermission}
            >
              {editRequestPending
                ? t("canvas.session.requestEditPending")
                : t("canvas.session.requestEdit")}
            </button>
          </div>
        )}
        {incomingEditRequest && isEditor && (
          <div className="ctb-share-banner ctb-share-banner--edit-request">
            <span>
              {t("canvas.session.editRequestIncoming", {
                who: personLabel(incomingEditRequest.requester, t("canvas.topbar.otherUser")),
              })}
            </span>
            <button
              type="button"
              className="ctb-banner-action ctb-banner-action--approve"
              onClick={() => respondEditRequest(true)}
            >
              {t("canvas.session.editRequestApprove")}
            </button>
            <button
              type="button"
              className="ctb-banner-action"
              onClick={() => respondEditRequest(false)}
            >
              {t("canvas.session.editRequestDeny")}
            </button>
          </div>
        )}
        {shareBanner && shareReadOnly && (
          <div className="ctb-share-banner">{t("canvas.share.readonly")}</div>
        )}
        {kickedNotice && (
          <div className="ctb-share-banner ctb-share-banner--warn">
            {kickedNotice}
            <button type="button" className="ctb-banner-dismiss" onClick={clearKickedNotice}>{t("canvas.share.ok")}</button>
          </div>
        )}
        {remoteSyncNotice && (
          <div className={`ctb-share-banner ctb-share-banner--info${collabReadOnly && lockHolder ? " ctb-share-banner--stacked" : ""}`}>
            {remoteSyncNotice}
            <button type="button" className="ctb-banner-dismiss" onClick={clearRemoteSyncNotice}>{t("canvas.share.ok")}</button>
          </div>
        )}
        {editorPromotedNotice && (
          <div className={`ctb-share-banner ctb-share-banner--info${collabReadOnly && lockHolder ? " ctb-share-banner--stacked" : ""}`}>
            {editorPromotedNotice}
            <button type="button" className="ctb-banner-dismiss" onClick={clearEditorPromotedNotice}>{t("canvas.share.ok")}</button>
          </div>
        )}
        {editRequestNotice && (
          <div className={`ctb-share-banner ctb-share-banner--info${collabReadOnly && lockHolder ? " ctb-share-banner--stacked" : ""}`}>
            {editRequestNotice}
            <button type="button" className="ctb-banner-dismiss" onClick={clearEditRequestNotice}>{t("canvas.share.ok")}</button>
          </div>
        )}
        <div className="rf-canvas-area">
          <CanvasLeftToolbar
            onAddNodeOfType={handleAddNodeOfType}
            onUploadImage={handleUploadImage}
            isFullscreen={isFullscreen}
            onToggleFullscreen={toggleFullscreen}
            hasUnreadComments={unreadCommentNodes > 0}
          />
          <CanvasBottomToolbar
            readOnly={readOnly}
            onRecenterViewport={handleRecenterViewport}
            onOrganizeCanvas={handleOrganizeCanvas}
          />
          {!hasNodes && (
            <CanvasEmptyState
              onQuickCreate={handleQuickCreate}
              onOpenAssets={handleOpenAssets}
              onStarterTemplate={handleStarterTemplate}
            />
          )}
        </div>
      </div>

      {!commentMode && (
        <CanvasPromptBar
          selectedNodeId={selectedNodeId}
          selectedNodeType={selectedNodeType}
          onGenerate={handlePromptBarGenerate}
          onClearSelection={() => setSelectedNodeId(null)}
          projectId={projectId}
          readOnly={readOnly}
        />
      )}

      {!shareReadOnly && (
        <CanvasCommentPanel
          open={!!commentTargetNodeId}
          nodeId={commentTargetNodeId}
          nodeLabel={commentNodeLabel}
          anchor={commentAnchor}
          thread={commentTargetNodeId ? getThread(commentTargetNodeId) : null}
          currentUserId={user?.id}
          onClose={handleCloseCommentPanel}
          onSubmit={async (body, mentionedUserIds) => {
            const thread = await postComment(commentTargetNodeId, body, commentDisplayName, mentionedUserIds)
            if (thread && projectId && commentTargetNodeId) {
              markNodeCommentsSeen(projectId, commentTargetNodeId, thread)
            }
            return thread
          }}
          displayName={commentDisplayName}
          username={user?.username}
          teamMembers={teamMembers}
          highlightMessageIds={highlightMessageIds}
          onEditMessage={(messageId, body) => editMessage(messageId, body)}
          onDeleteMessage={async (messageId) => {
            const res = await removeMessage(messageId)
            if (res?.deleted && commentTargetNodeId) {
              setCommentTargetNodeId(null)
            }
          }}
        />
      )}

      <AssetLibraryFlyout
        open={assetLibraryOpen}
        onClose={() => setAssetLibraryOpen(false)}
        getCardPointerHandlers={getCardPointerHandlers}
      />
      <GenerationHistoryFlyout
        open={genHistoryOpen}
        onClose={() => setGenHistoryOpen(false)}
        getCardPointerHandlers={getCardPointerHandlers}
      />

      <CanvasProfileModal />
      {migrateOpen && (
        <MigrateToTeamModal
          open={migrateOpen}
          onClose={() => setMigrateOpen(false)}
          projectName={projectName}
          teams={migratableTeams}
          onConfirm={handleMigrateConfirm}
        />
      )}

      <CanvasDragGhost session={dragPlaceSession} />

      <PendingConnectionLine pickerMenu={pickerMenu} theme={theme} />

      {pickerMenu && (
        <NodePickerMenu
          x={pickerMenu.x}
          y={pickerMenu.y}
          fromEdge={pickerMenu.fromEdge || false}
          sourceNodeType={pickerMenu.sourceNodeType || null}
          onSelect={(item) => {
            if (item.action === "import-document") {
              setPickerMenu(null)
              setImportDocumentOpen(true)
              return
            }
            handleCreateNode(item, pickerMenu)
          }}
          onClose={dismissPickerMenu}
        />
      )}

      {projectId && (
        <ImportDocumentModal
          open={importDocumentOpen}
          onClose={() => setImportDocumentOpen(false)}
          projectId={projectId}
          theme={theme}
          canvasBridge={{
            getNodes: () => nodesRef.current || nodes,
            setNodes,
            setEdges,
          }}
          onApplied={() => {
            reloadFromServerRef.current?.()
          }}
        />
      )}

      {contextMenu && (
        <CanvasRightClickMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onCreateNode={(type) => {
            pushHistory()
            createNode(type, { x: contextMenu.x, y: contextMenu.y })
            setContextMenu(null)
          }}
          onUploadImage={() => { setContextMenu(null); handleUploadImage() }}
          onUndo={() => { if (undo()) setSelectedNodeId(null) }}
          onRedo={() => { if (redo()) setSelectedNodeId(null) }}
          onPaste={() => document.execCommand("paste")}
          onClose={() => setContextMenu(null)}
        />
      )}

      {user?.role === "admin" && <PromptTracePanel />}

      {projectId && (
        <CanvasAgentFab
          open={agentOpen}
          disabled={!projectId || readOnly}
          onToggle={() => setAgentOpen((v) => !v)}
        />
      )}

      {projectId && (
        <AgentPanel
          open={agentOpen}
          projectId={projectId}
          readOnlyRef={readOnlyRef}
          readOnly={readOnly}
          buildData={buildData}
          buildOutlineData={buildOutlineData}
          bumpZIndex={bumpZIndex}
          workflowRef={agentWorkflowRef}
          agentSendRef={agentSendRef}
          agentRefPickRef={agentRefPickRef}
          onClose={() => setAgentOpen(false)}
        />
      )}

      <OnboardingTour tourId="canvas" steps={CANVAS_STEPS} startDelayMs={1000} />
    </div>
    </CanvasActionsContext.Provider>
    </ReferenceSelectContext.Provider>
    </PromptIntentGateProvider>
  )
}

export default function Canvas() {
  const fetchModels = useModelStore((s) => s.fetchModels)
  const startListening = useTaskStore((s) => s.startListening)
  const stopListening = useTaskStore((s) => s.stopListening)

  useEffect(() => {
    document.documentElement.classList.add("rf-canvas-page-active")
    if (localStorage.getItem("access_token")) {
      wsManager.connect()
    }
    startListening()
    fetchModels()
    return () => {
      document.documentElement.classList.remove("rf-canvas-page-active")
      stopListening()
    }
  }, [])

  return (
    <CanvasThemeProvider>
      <ReactFlowProvider>
        <CanvasInner />
      </ReactFlowProvider>
    </CanvasThemeProvider>
  )
}
