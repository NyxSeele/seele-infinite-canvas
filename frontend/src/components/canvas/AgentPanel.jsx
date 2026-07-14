import { useState, useRef, useEffect, useCallback } from "react"
import { useAuth } from "../../contexts/AuthContext"
import { useReferenceSelect } from "./CanvasActionsContext"
import { useCanvasAgent } from "../../hooks/canvas/useCanvasAgent"
import { useAgentVoiceInput } from "../../hooks/canvas/useAgentVoiceInput"
import {
  listAgentChatHistory,
  deleteAgentChatHistory,
} from "../../utils/canvas/agentChatHistory"
import { showDevNotice } from "../common/ProductNoticeModal"
import MentionTextarea from "./MentionTextarea"
import { VideoAtMentionList } from "./VideoAtMentionList"
import {
  appendReferenceImage,
  MAX_REFERENCE_IMAGES,
} from "./videoReferenceHelpers"
import { getUserDisplayName } from "../../utils/canvas/profileSync"
import { formatRelativeTime } from "../../utils/canvas/formatRelativeTime"
import { normalizeCastLibrary } from "../../utils/canvas/castLibrary"
import { normalizeSceneLibrary } from "../../utils/canvas/sceneLibrary"
import { uploadImageFile } from "../../services/uploadImage"
import { useAssetStore, useCanvasStore } from "../../stores"
import { getActiveTeamId } from "../../utils/teamContext"
import { assetKindToCastType, isSubjectKind } from "../../utils/canvas/globalAssets"
import AgentThoughtBlock from "./AgentThoughtBlock"
import AgentCreativeCards, { CastPendingCard, ScenePendingCard } from "./AgentCreativeCards"
import {
  IconChat,
  IconMic,
  IconSend,
  IconHistoryEmpty,
  IconAnalyze,
  IconPipeline,
  IconOrganize,
  IconManualMode,
  IconAutoMode,
  IconCanvasAdd,
  IconUpload,
  IconBrainstorm,
  IconSkills,
  IconThinking,
  IconCheck,
  IconStop,
  IconContinue,
  IconAcceptOnly,
  IconUndo,
} from "./AgentPanelIcons"
import "./AgentPanel.css"
import "./NodeBanner.css"

export const AGENT_REF_SOURCE_ID = "__agent__"

const QUICK_ACTIONS = [
  {
    id: "analyze",
    title: "分析当前画布",
    prompt: "请分析当前画布上的节点、文本与图像内容，总结创作进度并给出可执行的改进建议",
    Icon: IconAnalyze,
  },
  {
    id: "pipeline",
    title: "检查剧本链路",
    prompt: "请检查当前宣传片/剧本链路的进度（文本输入→剧本文本→大纲→分镜表），告诉我下一步该做什么",
    Icon: IconPipeline,
  },
  {
    id: "organize",
    title: "整理节点建议",
    prompt: "根据当前画布节点分布，给出整理与排版建议，并说明是否需要新建或连接节点",
    Icon: IconOrganize,
  },
]

const EXECUTION_MODES = [
  {
    id: "manual",
    label: "手动确认",
    desc: "每步需确认后才继续",
    Icon: IconManualMode,
  },
  {
    id: "auto",
    label: "自动生成",
    desc: "确认后自动继续",
    Icon: IconAutoMode,
  },
]

const PLUS_MENU_TOP = [
  { id: "canvas", label: "从画布添加", Icon: IconCanvasAdd },
  { id: "upload", label: "上传附件", Icon: IconUpload },
]

const PLUS_MENU_BOTTOM = [
  { id: "brainstorm", label: "头脑风暴", Icon: IconBrainstorm, placeholder: true },
  { id: "skills", label: "技能", Icon: IconSkills, placeholder: true },
  {
    id: "thinking",
    label: "思考等级",
    Icon: IconThinking,
    placeholder: true,
    suffix: "Standard",
  },
]

function ReviewActions({ roundId, compact, onAcceptContinue, onAccept, onUndo }) {
  return (
    <div
      className={`ap-review-actions${
        compact ? " ap-review-actions--compact" : " ap-review-actions--inline"
      }`}
    >
      <button
        type="button"
        className="ap-btn--confirm ap-btn--sm"
        onClick={() => onAcceptContinue(roundId)}
      >
        <span className="ap-btn__icon" aria-hidden>
          <IconContinue />
        </span>
        采纳并继续
      </button>
      <button type="button" className="ap-btn--ghost ap-btn--sm" onClick={() => onAccept(roundId)}>
        <span className="ap-btn__icon" aria-hidden>
          <IconAcceptOnly />
        </span>
        仅采纳
      </button>
      <button type="button" className="ap-btn--cancel ap-btn--sm" onClick={() => onUndo(roundId)}>
        <span className="ap-btn__icon" aria-hidden>
          <IconUndo />
        </span>
        撤销
      </button>
    </div>
  )
}

export default function AgentPanel({
  open,
  projectId,
  readOnlyRef,
  readOnly,
  buildData,
  buildOutlineData,
  bumpZIndex,
  workflowRef,
  agentSendRef,
  onClose,
  agentRefPickRef,
}) {
  const {
    messages,
    thinking,
    streamingReply,
    error,
    retryErrorUserIndex,
    isRunning,
    awaitingReply,
    pipelineStatus,
    sendMessage,
    undoRound,
    acceptRound,
    stopGeneration,
    conversationLoading,
    reviewRoundId,
    executionMode,
    setExecutionMode,
    startNewChat,
    loadChatHistory,
    startNewChatFromHistory,
    startNewChatFromMessage,
    deleteMessageAt,
    retryFromMessage,
  } = useCanvasAgent({
    projectId,
    readOnlyRef,
    buildData,
    buildOutlineData,
    bumpZIndex,
    workflowRef,
  })

  const refSelect = useReferenceSelect()
  const { user } = useAuth()
  const [input, setInput] = useState("")
  const [mentions, setMentions] = useState([])
  const [referenceImages, setReferenceImages] = useState([])
  const [modeOpen, setModeOpen] = useState(false)
  const [plusOpen, setPlusOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyList, setHistoryList] = useState([])
  const [modeHover, setModeHover] = useState(false)
  const [atMentionOpen, setAtMentionOpen] = useState(false)
  const [atMentionQuery, setAtMentionQuery] = useState("")
  const [atMentionAnchor, setAtMentionAnchor] = useState(null)
  const messagesEndRef = useRef(null)
  const messagesScrollRef = useRef(null)
  const modeRef = useRef(null)
  const plusRef = useRef(null)
  const fileInputRef = useRef(null)
  const mentionEditorRef = useRef(null)
  const mentionListRef = useRef(null)
  const [displayName, setDisplayName] = useState(() => getUserDisplayName(user))
  const isEmpty =
    !historyOpen
    && !conversationLoading
    && messages.length === 0
    && !thinking
    && !isRunning
  const currentMode = EXECUTION_MODES.find((m) => m.id === executionMode) || EXECUTION_MODES[0]
  const refAtMax = referenceImages.length >= MAX_REFERENCE_IMAGES

  const assets = useAssetStore((s) => s.assets)
  const teamAssets = useAssetStore((s) => s.teamAssets)
  const fetchAssets = useAssetStore((s) => s.fetchAssets)
  const fetchTeamAssets = useAssetStore((s) => s.fetchTeamAssets)
  const addAssetFromUrl = useAssetStore((s) => s.addAssetFromUrl)
  const projectTeamId = useCanvasStore((s) => s.projectTeamId)
  const canvasId = useCanvasStore((s) => s.canvasId)
  const projectName = useCanvasStore((s) => s.projectName)
  const teamId = projectTeamId ?? getActiveTeamId()

  useEffect(() => {
    fetchAssets()
  }, [fetchAssets])

  useEffect(() => {
    if (!agentSendRef) return undefined
    agentSendRef.current = sendMessage
    return () => {
      if (agentSendRef.current === sendMessage) {
        agentSendRef.current = null
      }
    }
  }, [agentSendRef, sendMessage])

  useEffect(() => {
    if (teamId) fetchTeamAssets(false, teamId)
  }, [fetchTeamAssets, teamId])

  const patchCastImage = useCallback(
    ({ castId, scriptTableId, imageUrl, globalAssetId }) => {
      const setNodes = workflowRef?.current?.setNodes
      if (!setNodes || !castId || !scriptTableId || !imageUrl) return
      setNodes((ns) =>
        ns.map((n) => {
          if (n.id !== scriptTableId || n.type !== "script-table") return n
          const castLibrary = normalizeCastLibrary(
            (n.data.castLibrary || []).map((c) =>
              c.id === castId
                ? {
                    ...c,
                    imageUrl,
                    pendingImage: false,
                    ...(globalAssetId ? { globalAssetId } : {}),
                  }
                : c
            ),
            { requireImage: false }
          )
          return { ...n, data: { ...n.data, castLibrary } }
        })
      )
    },
    [workflowRef]
  )

  const patchSceneImage = useCallback(
    ({ sceneId, scriptTableId, imageUrl, globalAssetId }) => {
      const setNodes = workflowRef?.current?.setNodes
      if (!setNodes || !sceneId || !scriptTableId || !imageUrl) return
      setNodes((ns) =>
        ns.map((n) => {
          if (n.id !== scriptTableId || n.type !== "script-table") return n
          const sceneLibrary = normalizeSceneLibrary(
            (n.data.sceneLibrary || []).map((s) =>
              s.id === sceneId
                ? {
                    ...s,
                    imageUrl,
                    pendingImage: false,
                    ...(globalAssetId ? { globalAssetId } : {}),
                  }
                : s
            ),
            { requireImage: false }
          )
          return { ...n, data: { ...n.data, sceneLibrary } }
        })
      )
    },
    [workflowRef]
  )

  const saveCastToTeamLibrary = useCallback(
    async ({ name, imageUrl, type, description, scriptTableId, castId }) => {
      if (!teamId || !name?.trim() || !imageUrl) return null
      try {
        const asset = await addAssetFromUrl({
          name: String(name).trim(),
          kind: type === "scene" ? "scene" : "character",
          imageUrl,
          note: description ? String(description).trim() : "",
          sourceCanvasId: canvasId,
          sourceCanvasName: projectName,
          sourceNodeId: scriptTableId,
          teamId,
        })
        if (asset?.id && castId && scriptTableId) {
          patchCastImage({
            castId,
            scriptTableId,
            imageUrl,
            globalAssetId: asset.id,
          })
        }
        return asset
      } catch (err) {
        console.error("保存团队角色资产失败", err)
        return null
      }
    },
    [teamId, addAssetFromUrl, canvasId, projectName, patchCastImage]
  )

  const handleAssignFromCanvas = useCallback(
    ({ castId, name, scriptTableId, type, description, saveToTeam }) => {
      if (!castId || !scriptTableId) return
      const onComplete = saveToTeam
        ? (imageUrl) => {
            saveCastToTeamLibrary({
              name,
              imageUrl,
              type,
              description,
              scriptTableId,
              castId,
            })
          }
        : null
      refSelect?.enter?.(scriptTableId, `castAssign:${castId}`, onComplete ? { onComplete } : null)
    },
    [refSelect, saveCastToTeamLibrary]
  )

  const handleAssignFromUpload = useCallback(
    async ({ castId, scriptTableId, name, type, description, file, saveToTeam }) => {
      if (!file || !castId || !scriptTableId) return
      try {
        const url = await uploadImageFile(file)
        if (saveToTeam) {
          await saveCastToTeamLibrary({
            name,
            imageUrl: url,
            type,
            description,
            scriptTableId,
            castId,
          })
        } else {
          patchCastImage({ castId, scriptTableId, imageUrl: url })
        }
      } catch (err) {
        console.error("角色参考图上传失败", err)
      }
    },
    [patchCastImage, saveCastToTeamLibrary]
  )

  const getImportableAssets = useCallback(
    (scriptTableId, { assignCastId, assignCastType } = {}) => {
      const scriptNode = workflowRef?.current?.getNodes?.()?.find(
        (n) => n.id === scriptTableId && n.type === "script-table"
      )
      const castNames = new Set(
        (scriptNode?.data?.castLibrary || [])
          .filter((c) => c.id !== assignCastId)
          .map((c) => c.name?.toLowerCase())
          .filter(Boolean)
      )
      const pool = teamId ? (teamAssets || []) : (assets || [])
      return (pool || []).filter(
        (a) =>
          a?.name
          && a?.imageUrl
          && isSubjectKind(a.kind)
          && assetKindToCastType(a.kind) === assignCastType
          && !castNames.has(a.name.toLowerCase())
      )
    },
    [teamId, teamAssets, assets, workflowRef]
  )

  const handleAssignFromAsset = useCallback(
    ({ castId, scriptTableId, asset }) => {
      if (!asset?.imageUrl || !castId) return
      patchCastImage({
        castId,
        scriptTableId,
        imageUrl: asset.imageUrl,
        globalAssetId: asset.id,
      })
    },
    [patchCastImage]
  )

  const saveSceneToTeamLibrary = useCallback(
    async ({ name, imageUrl, description, scriptTableId, sceneId }) => {
      if (!teamId || !name?.trim() || !imageUrl) return null
      try {
        const asset = await addAssetFromUrl({
          name: String(name).trim(),
          kind: "scene",
          imageUrl,
          note: description ? String(description).trim() : "",
          sourceCanvasId: canvasId,
          sourceCanvasName: projectName,
          sourceNodeId: scriptTableId,
          teamId,
        })
        if (asset?.id && sceneId && scriptTableId) {
          patchSceneImage({
            sceneId,
            scriptTableId,
            imageUrl,
            globalAssetId: asset.id,
          })
        }
        return asset
      } catch (err) {
        console.error("保存团队场景资产失败", err)
        return null
      }
    },
    [teamId, addAssetFromUrl, canvasId, projectName, patchSceneImage]
  )

  const handleSceneAssignFromCanvas = useCallback(
    ({ sceneId, name, scriptTableId, description, saveToTeam }) => {
      if (!sceneId || !scriptTableId) return
      const onComplete = saveToTeam
        ? (imageUrl) => {
            saveSceneToTeamLibrary({
              name,
              imageUrl,
              description,
              scriptTableId,
              sceneId,
            })
          }
        : null
      refSelect?.enter?.(scriptTableId, `sceneAssign:${sceneId}`, onComplete ? { onComplete } : null)
    },
    [refSelect, saveSceneToTeamLibrary]
  )

  const handleSceneAssignFromUpload = useCallback(
    async ({ sceneId, scriptTableId, name, description, file, saveToTeam }) => {
      if (!file || !sceneId || !scriptTableId) return
      try {
        const url = await uploadImageFile(file)
        if (saveToTeam) {
          await saveSceneToTeamLibrary({
            name,
            imageUrl: url,
            description,
            scriptTableId,
            sceneId,
          })
        } else {
          patchSceneImage({ sceneId, scriptTableId, imageUrl: url })
        }
      } catch (err) {
        console.error("场景参考图上传失败", err)
      }
    },
    [patchSceneImage, saveSceneToTeamLibrary]
  )

  const getImportableSceneAssets = useCallback(
    (scriptTableId, { assignSceneId } = {}) => {
      const scriptNode = workflowRef?.current?.getNodes?.()?.find(
        (n) => n.id === scriptTableId && n.type === "script-table"
      )
      const sceneNames = new Set(
        (scriptNode?.data?.sceneLibrary || [])
          .filter((s) => s.id !== assignSceneId)
          .map((s) => s.name?.toLowerCase())
          .filter(Boolean)
      )
      const pool = teamId ? (teamAssets || []) : (assets || [])
      return (pool || []).filter(
        (a) =>
          a?.name
          && a?.imageUrl
          && a.kind === "scene"
          && !sceneNames.has(a.name.toLowerCase())
      )
    },
    [teamId, teamAssets, assets, workflowRef]
  )

  const handleSceneAssignFromAsset = useCallback(
    ({ sceneId, scriptTableId, asset }) => {
      if (!asset?.imageUrl || !sceneId) return
      patchSceneImage({
        sceneId,
        scriptTableId,
        imageUrl: asset.imageUrl,
        globalAssetId: asset.id,
      })
    },
    [patchSceneImage]
  )

  const appendVoiceText = useCallback((text) => {
    setInput((prev) => (prev ? `${prev} ${text}` : text))
  }, [])

  const { listening, toggleListening } = useAgentVoiceInput({
    onTranscript: appendVoiceText,
  })

  const refreshHistory = useCallback(() => {
    if (!projectId) return
    listAgentChatHistory(projectId).then(setHistoryList).catch(() => setHistoryList([]))
  }, [projectId])

  const addReferenceImage = useCallback((refItem) => {
    setReferenceImages((prev) => appendReferenceImage(prev, refItem, MAX_REFERENCE_IMAGES))
  }, [])

  useEffect(() => {
    if (!agentRefPickRef) return undefined
    agentRefPickRef.current = (refItem) => {
      addReferenceImage(refItem)
    }
    return () => {
      agentRefPickRef.current = null
    }
  }, [agentRefPickRef, addReferenceImage])

  useEffect(() => {
    if (historyOpen) {
      messagesScrollRef.current?.scrollTo({ top: 0 })
      return
    }
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, thinking, pipelineStatus, historyOpen])

  useEffect(() => {
    if (open) refreshHistory()
  }, [open, refreshHistory])

  useEffect(() => {
    const onTitleUpdated = (e) => {
      if (e.detail?.projectId === projectId) refreshHistory()
    }
    window.addEventListener("agent-chat-title-updated", onTitleUpdated)
    return () => window.removeEventListener("agent-chat-title-updated", onTitleUpdated)
  }, [projectId, refreshHistory])

  useEffect(() => {
    const onDocClick = (e) => {
      if (modeRef.current && !modeRef.current.contains(e.target)) setModeOpen(false)
      if (plusRef.current && !plusRef.current.contains(e.target)) {
        setPlusOpen(false)
      }
    }
    document.addEventListener("pointerdown", onDocClick)
    return () => document.removeEventListener("pointerdown", onDocClick)
  }, [])

  const handleSend = () => {
    const text = input.trim()
    if (!text && referenceImages.length === 0) return
    setHistoryOpen(false)
    sendMessage(text)
    setInput("")
    setMentions([])
    setReferenceImages([])
    if (mentionEditorRef.current) {
      mentionEditorRef.current.focus?.()
    }
  }

  const handleNewChat = async () => {
    await startNewChat()
    setHistoryOpen(false)
    setInput("")
    setMentions([])
    setReferenceImages([])
  }

  const openCanvasRefPicker = useCallback(() => {
    if (refAtMax) return
    setPlusOpen(false)
    refSelect?.enter?.(AGENT_REF_SOURCE_ID, "referenceImage")
  }, [refAtMax, refSelect])

  const handlePlusAction = (item) => {
    if (item.placeholder) {
      setPlusOpen(false)
      showDevNotice(item.label)
      return
    }
    if (item.id === "canvas") {
      openCanvasRefPicker()
      return
    }
    if (item.id === "upload") {
      setPlusOpen(false)
      fileInputRef.current?.click()
    }
  }

  const removeReferenceImage = useCallback((index) => {
    setReferenceImages((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const handleMentionEditorChange = useCallback(({ text, mentions: nextMentions }) => {
    setInput(text)
    setMentions(nextMentions)
  }, [])

  const handleMentionQuery = useCallback(({ active, query, anchorRect }) => {
    if (active) {
      setAtMentionOpen(true)
      setAtMentionQuery(query || "")
      setAtMentionAnchor(anchorRect || null)
    } else {
      setAtMentionOpen(false)
      setAtMentionQuery("")
      setAtMentionAnchor(null)
    }
  }, [])

  const handleAtMentionSelect = useCallback((item) => {
    mentionEditorRef.current?.insertMention(item)
    setAtMentionOpen(false)
    setAtMentionQuery("")
    setAtMentionAnchor(null)
  }, [])

  const stopPanelDblClick = useCallback((e) => {
    e.stopPropagation()
  }, [])

  const inputPlaceholder = awaitingReply
    ? "回复 AI 的问题…"
    : "描述创意或需求，/ 使用技能，添加画布内容，@ 引用参考"

  useEffect(() => {
    setDisplayName(getUserDisplayName(user))
    const onPrefs = () => setDisplayName(getUserDisplayName(user))
    window.addEventListener("canvas-prefs-changed", onPrefs)
    return () => window.removeEventListener("canvas-prefs-changed", onPrefs)
  }, [user])

  if (readOnly) {
    return (
      <aside
        className={`agent-panel${open ? " agent-panel--open" : ""} agent-panel--readonly`}
        onDoubleClick={stopPanelDblClick}
      >
        <div className="ap-header">
          <span className="ap-header__title">AI 助手</span>
          <button type="button" className="ap-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <div className="ap-readonly-msg">只有编辑者可以使用 AI 助手</div>
      </aside>
    )
  }

  return (
    <aside
      className={`agent-panel${open ? " agent-panel--open" : ""}${isEmpty && !historyOpen ? " agent-panel--welcome" : ""}`}
      aria-hidden={!open}
      onDoubleClick={stopPanelDblClick}
    >
      <div className="ap-header">
        {historyOpen ? (
          <button
            type="button"
            className="ap-history-back"
            onClick={() => setHistoryOpen(false)}
            aria-label="返回对话"
          >
            返回
          </button>
        ) : (
          <span className="ap-header__spacer" />
        )}
        <div className="ap-header__actions">
          <button
            type="button"
            className="ap-header-btn"
            title="新对话"
            onClick={handleNewChat}
          >
            +
          </button>
          <button
            type="button"
            className={`ap-header-btn${historyOpen ? " ap-header-btn--active" : ""}`}
            title="聊天记录"
            onClick={() => setHistoryOpen((v) => !v)}
          >
            <IconChat />
          </button>
          <button type="button" className="ap-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
      </div>

      <div className="ap-messages" ref={messagesScrollRef}>
        {historyOpen ? (
          <div className="ap-history">
            {historyList.length === 0 ? (
              <div className="ap-history-empty">
                <IconHistoryEmpty />
                <p>暂无历史记录</p>
              </div>
            ) : (
              <ul className="ap-history-list">
                {historyList.map((entry) => (
                  <li key={entry.id} className="ap-history-row">
                    <button
                      type="button"
                      className="ap-history-item"
                      onClick={() => {
                        loadChatHistory(entry)
                        setHistoryOpen(false)
                      }}
                    >
                      <span className="ap-history-item__title">{entry.title}</span>
                      <span className="ap-history-item__time">
                        {formatRelativeTime(entry.updatedAt)}
                      </span>
                    </button>
                    <div className="ap-history-item__actions">
                      <button
                        type="button"
                        className="ap-history-item__branch"
                        title="由此开启新对话"
                        onClick={(e) => {
                          e.stopPropagation()
                          void startNewChatFromHistory(entry).then(() => {
                            setHistoryOpen(false)
                            refreshHistory()
                          })
                        }}
                      >
                        由此开启新对话
                      </button>
                      <button
                        type="button"
                        className="ap-history-item__delete"
                        aria-label="删除"
                        onClick={(e) => {
                          e.stopPropagation()
                          void deleteAgentChatHistory(projectId, entry.id).then(refreshHistory)
                        }}
                      >
                        ×
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <>
            {conversationLoading && (
              <div className="ap-loading">加载对话历史…</div>
            )}

            {isEmpty && (
              <div className="ap-hero">
                <img
                  className="ap-hero__avatar"
                  src="/assets/agent-avatar.png"
                  alt=""
                  draggable={false}
                />
                <p className="ap-hero__greet">Hi {displayName}!</p>
                <h2 className="ap-hero__title">今天一起创作点什么？</h2>
                <div className="ap-quick-row">
                  {QUICK_ACTIONS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="ap-quick-pill"
                      onClick={() => sendMessage(item.prompt)}
                    >
                      <span className="ap-quick-pill__icon" aria-hidden>
                        <item.Icon />
                      </span>
                      <span>{item.title}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={`${msg.roundId || "m"}-${i}`}
                className={`ap-msg-wrap ap-msg-wrap--${msg.role}${
                  msg.creativeOptions?.length ? " ap-msg-wrap--creative" : ""
                }${msg.castPending?.length ? " ap-msg-wrap--creative" : ""}`}
              >
                {msg.role === "assistant" && msg.thinking && (
                  <AgentThoughtBlock
                    text={msg.thinking}
                    defaultOpen={false}
                  />
                )}
                {(msg.role === "user"
                  || msg.content
                  || (msg.canUndo
                    && msg.roundId
                    && reviewRoundId === msg.roundId
                    && executionMode === "manual")) && (
                <div
                  className={`ap-msg ap-msg--${msg.role}${
                    msg.kind === "ask"
                    && !msg.creativeOptions?.length
                    && !msg.castPending?.length
                      ? " ap-msg--ask"
                      : ""
                  }${msg.creativeOptions?.length ? " ap-msg--ask-intro" : ""}`}
                >
                  {msg.content ? (
                    <div className="ap-msg__body">{msg.content}</div>
                  ) : null}
                  {msg.canUndo
                    && msg.roundId
                    && reviewRoundId === msg.roundId
                    && executionMode === "manual" && (
                    <ReviewActions
                      roundId={msg.roundId}
                      onAcceptContinue={(id) => acceptRound(id, { continueNext: true })}
                      onAccept={acceptRound}
                      onUndo={undoRound}
                    />
                  )}
                </div>
                )}
                {msg.creativeOptions?.length > 0 && !msg.castPending?.length && (
                  <AgentCreativeCards
                    options={msg.creativeOptions}
                    groupTitle={msg.creativeGroupTitle}
                    groupSubtitle={msg.creativeGroupSubtitle}
                    disabled={readOnly || isRunning}
                    onSelect={(opt) => {
                      const title = opt.title || opt.label || ""
                      const focus = opt.focus ? `（${opt.focus}）` : ""
                      sendMessage(`我选择「${title}」${focus}`)
                    }}
                  />
                )}
                {msg.castPending?.length > 0 && (
                  <CastPendingCard
                    castPending={msg.castPending}
                    scriptTableId={msg.castPendingScriptTableId}
                    getImportableAssets={(castItem) =>
                      getImportableAssets(msg.castPendingScriptTableId, {
                        assignCastId: castItem?.id,
                        assignCastType: "character",
                      })
                    }
                    teamLibraryEnabled={!!teamId}
                    disabled={readOnly || isRunning}
                    onAssignFromCanvas={handleAssignFromCanvas}
                    onAssignFromUpload={handleAssignFromUpload}
                    onAssignFromAsset={handleAssignFromAsset}
                  />
                )}
                {msg.scenePending?.length > 0 && (
                  <ScenePendingCard
                    scenePending={msg.scenePending}
                    scriptTableId={msg.scenePendingScriptTableId || msg.castPendingScriptTableId}
                    getImportableAssets={(sceneItem) =>
                      getImportableSceneAssets(
                        msg.scenePendingScriptTableId || msg.castPendingScriptTableId,
                        { assignSceneId: sceneItem?.id }
                      )
                    }
                    teamLibraryEnabled={!!teamId}
                    disabled={readOnly || isRunning}
                    onAssignFromCanvas={handleSceneAssignFromCanvas}
                    onAssignFromUpload={handleSceneAssignFromUpload}
                    onAssignFromAsset={handleSceneAssignFromAsset}
                  />
                )}
                {msg.castPending?.length > 0 && msg.creativeOptions?.length > 0 && (
                  <div className="ap-suggestions ap-suggestions--list">
                    {msg.creativeOptions.map((opt, si) => {
                      const label = opt?.label || opt?.title || ""
                      if (!label) return null
                      return (
                        <span
                          key={`${msg.roundId || "m"}-cast-opt-${si}`}
                          className="ap-suggestion-item"
                        >
                          <span className="ap-suggestion-star" aria-hidden>
                            ✦
                          </span>
                          <button
                            type="button"
                            className="ap-suggestion-row"
                            disabled={readOnly || isRunning}
                            onClick={() => sendMessage(label)}
                          >
                            {label}
                          </button>
                        </span>
                      )
                    })}
                  </div>
                )}
                {msg.suggestions?.length > 0 && (
                  <div className="ap-suggestions ap-suggestions--list">
                    {msg.suggestions.map((s, si) => (
                      <span
                        key={`${msg.roundId || "m"}-sug-${si}`}
                        className="ap-suggestion-item"
                      >
                        <span className="ap-suggestion-star" aria-hidden>
                          ✦
                        </span>
                        <button
                          type="button"
                          className="ap-suggestion-row"
                          disabled={readOnly || isRunning}
                          onClick={() => sendMessage(s)}
                        >
                          {s}
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                {msg.role === "user" && !readOnly && !isRunning && (
                  <div className="ap-msg__actions">
                    <button
                      type="button"
                      className="ap-msg__action"
                      onClick={() => retryFromMessage(i)}
                      title="重试"
                    >
                      重试
                    </button>
                    <button
                      type="button"
                      className="ap-msg__action"
                      onClick={() => startNewChatFromMessage(i)}
                      title="由此开启新对话"
                    >
                      由此开启新对话
                    </button>
                    <button
                      type="button"
                      className="ap-msg__action"
                      onClick={() => deleteMessageAt(i)}
                      title="删除"
                    >
                      删除
                    </button>
                  </div>
                )}
              </div>
            ))}

            {isRunning && thinking && (
              <AgentThoughtBlock
                text={thinking}
                live={!pipelineStatus && !streamingReply}
              />
            )}
            {isRunning && streamingReply && !pipelineStatus && (
              <div className="ap-msg ap-msg--assistant ap-msg--streaming">
                <div className="ap-msg__body">{streamingReply}</div>
              </div>
            )}
            {isRunning && !thinking && !streamingReply && !pipelineStatus && (
              <div className="ap-thinking-status" aria-live="polite">
                思考中…
              </div>
            )}
            {pipelineStatus && (
              <div className="ap-step-status" aria-live="polite">
                {pipelineStatus}
              </div>
            )}
            {error && (
              <div className="ap-error">
                <span>{error}</span>
                {retryErrorUserIndex != null && !readOnly && !isRunning && (
                  <button
                    type="button"
                    className="ap-error__retry"
                    onClick={() => retryFromMessage(retryErrorUserIndex)}
                  >
                    重试
                  </button>
                )}
              </div>
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {reviewRoundId && executionMode === "auto" && !historyOpen && (
        <div className="ap-review-bar">
          <ReviewActions
            roundId={reviewRoundId}
            compact
            onAcceptContinue={(id) => acceptRound(id, { continueNext: true })}
            onAccept={acceptRound}
            onUndo={undoRound}
          />
        </div>
      )}

      <div className="ap-composer">
        <div className="ap-composer__box">
          {referenceImages.length > 0 && (
            <div className="ap-ref-tags ref-tags-scroll nodrag nopan">
              {referenceImages.map((ref, i) => (
                <div key={`${ref.imageId || ref.imageUrl}-${i}`} className="ref-tag nodrag nopan">
                  <img src={ref.imageUrl} alt="" draggable={false} />
                  <span className="ref-label">{ref.label || "参考图"}</span>
                  <button
                    type="button"
                    className="ref-remove nodrag nopan"
                    onClick={() => removeReferenceImage(i)}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="ap-mention-wrap" ref={mentionListRef}>
            <VideoAtMentionList
              open={atMentionOpen}
              query={atMentionQuery}
              anchorRect={atMentionAnchor}
              excludeNodeId={null}
              compact
              onSelect={handleAtMentionSelect}
              onClose={() => {
                setAtMentionOpen(false)
                setAtMentionQuery("")
                setAtMentionAnchor(null)
              }}
            />
            {(!input.trim() && !mentions.length)
              && !(isRunning || (!!reviewRoundId && executionMode === "manual")) && (
              <div className="ap-composer-placeholder" aria-hidden>
                {reviewRoundId
                  ? executionMode === "manual"
                    ? "请先采纳并继续，或撤销上一步…"
                    : "请在下方确认本步结果…"
                  : inputPlaceholder}
              </div>
            )}
            <MentionTextarea
              ref={mentionEditorRef}
              className="ap-mention-editor"
              placeholder=""
              value={input}
              mentions={mentions}
              disabled={isRunning || (!!reviewRoundId && executionMode === "manual")}
              onChange={handleMentionEditorChange}
              onMentionQuery={handleMentionQuery}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
            />
          </div>

          <div className="ap-composer__bar">
            <div className="ap-composer__tools">
              <div className="ap-composer__left" ref={plusRef}>
              <button
                type="button"
                className="ap-composer__plus"
                aria-label="更多"
                onClick={() => setPlusOpen((v) => !v)}
              >
                +
              </button>
              {plusOpen && (
                <div className="ap-plus-menu">
                  {PLUS_MENU_TOP.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="ap-plus-menu__item"
                      onClick={() => handlePlusAction(item)}
                    >
                      <span className="ap-plus-menu__icon" aria-hidden>
                        <item.Icon />
                      </span>
                      <span>{item.label}</span>
                    </button>
                  ))}
                  <div className="ap-plus-menu__sep" />
                  {PLUS_MENU_BOTTOM.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="ap-plus-menu__item"
                      onClick={() => handlePlusAction(item)}
                    >
                      <span className="ap-plus-menu__icon" aria-hidden>
                        <item.Icon />
                      </span>
                      <span className="ap-plus-menu__label">{item.label}</span>
                      {item.suffix && (
                        <span className="ap-plus-menu__suffix">{item.suffix}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div
              className="ap-mode-wrap"
              ref={modeRef}
              onMouseEnter={() => setModeHover(true)}
              onMouseLeave={() => setModeHover(false)}
            >
              {modeHover && !modeOpen && (
                <div className="ap-mode-tooltip">
                  <div className="ap-mode-tooltip__bar" />
                  {currentMode.desc}
                </div>
              )}
              <button
                type="button"
                className="ap-mode-trigger"
                disabled={isRunning}
                onClick={() => setModeOpen((v) => !v)}
              >
                <span className="ap-mode-trigger__icon" aria-hidden>
                  <currentMode.Icon />
                </span>
                <span>{currentMode.label}</span>
              </button>
              {modeOpen && (
                <ul className="ap-mode-menu" role="listbox">
                  {EXECUTION_MODES.map((mode) => (
                    <li key={mode.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={executionMode === mode.id}
                        className={`ap-mode-option${executionMode === mode.id ? " ap-mode-option--active" : ""}`}
                        onClick={() => {
                          setExecutionMode(mode.id)
                          setModeOpen(false)
                        }}
                      >
                        <span className="ap-mode-option__icon" aria-hidden>
                          <mode.Icon />
                        </span>
                        <span className="ap-mode-option__text">
                          <strong>{mode.label}</strong>
                          <small>{mode.desc}</small>
                        </span>
                        <span className="ap-mode-check">
                          {executionMode === mode.id ? <IconCheck /> : null}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            </div>

            <div className="ap-composer__spacer" />

            <div className="ap-composer__right">
              {isRunning ? (
                <button
                  type="button"
                  className="ap-stop"
                  onClick={stopGeneration}
                  aria-label="停止"
                  title="停止"
                >
                  <IconStop />
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className={`ap-mic-btn${listening ? " ap-mic-btn--active" : ""}`}
                    aria-label="语音输入"
                    title={listening ? "停止录音" : "语音输入"}
                    onClick={() => {
                      if (!toggleListening()) showDevNotice("当前浏览器不支持语音输入")
                    }}
                  >
                    <IconMic active={listening} />
                  </button>
                  <button
                    type="button"
                    className="ap-send ap-send--round"
                    onClick={handleSend}
                    disabled={
                      (!input.trim() && referenceImages.length === 0)
                      || (!!reviewRoundId && executionMode === "manual")
                    }
                    aria-label="发送"
                  >
                    <IconSend />
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          className="ap-file-input"
          accept="image/*,.pdf,.txt,.md,.doc,.docx"
          onChange={() => showDevNotice("附件上传")}
        />
      </div>
    </aside>
  )
}
