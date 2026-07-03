import { useMemo, useEffect, useState, useRef, useCallback } from "react"
import { useNodes, useReactFlow, useViewport } from "reactflow"
import { useLocale } from "../../utils/locale"
import { AVATAR_CHANGED_EVENT } from "../../utils/canvas/userAvatar"
import { resolveCommentAuthorName, resolveCommentAvatar } from "../../utils/canvas/commentUserDisplay"
import { getCommentPinPosition } from "../../utils/canvas/commentMarkerLayout"
import { isNodeCommentUnread } from "../../utils/canvas/commentReadState"
import "./CanvasCommentPanel.css"

function CommentPinAvatar({ msg, currentUserId, username }) {
  const [avatarTick, setAvatarTick] = useState(0)
  const [imgBroken, setImgBroken] = useState(false)
  useEffect(() => {
    const onChange = () => setAvatarTick((n) => n + 1)
    window.addEventListener(AVATAR_CHANGED_EVENT, onChange)
    return () => window.removeEventListener(AVATAR_CHANGED_EVENT, onChange)
  }, [])

  useEffect(() => {
    setImgBroken(false)
  }, [msg?.id, msg?.author_avatar_url, msg?.author_id, avatarTick])

  void avatarTick
  const url = resolveCommentAvatar(msg, currentUserId)
  const name = resolveCommentAuthorName(msg, currentUserId, username)
  const letter = (name?.[0] || "U").toUpperCase()

  if (url && !imgBroken) {
    return (
      <img
        src={url}
        alt=""
        className="ccp-marker-avatar-img"
        draggable={false}
        onError={() => setImgBroken(true)}
      />
    )
  }
  return <span className="ccp-marker-avatar-letter">{letter}</span>
}

function CommentMarkerPin({
  marker,
  commentMode,
  activeNodeId,
  currentUserId,
  username,
  onOpen,
  t,
}) {
  const [hovered, setHovered] = useState(false)
  const [tipFlipLeft, setTipFlipLeft] = useState(false)
  const pinRef = useRef(null)
  const isActive = activeNodeId === marker.nodeId
  const authorName = resolveCommentAuthorName(marker.msg, currentUserId, username)
  const preview = (marker.msg?.body || "").trim().slice(0, 48)
  const unreadLabel = marker.unread ? `, ${t("canvas.comment.unread")}` : ""
  const ariaLabel = authorName
    ? `${authorName}: ${preview || t("canvas.comment.cardTitle")}${unreadLabel}`
    : t("canvas.comment.cardTitle")

  const updateTipFlip = useCallback(() => {
    const el = pinRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const tipW = 220
    setTipFlipLeft(rect.right + 10 + tipW > window.innerWidth - 8)
  }, [])

  const handleOpen = useCallback((e) => {
    e?.stopPropagation?.()
    onOpen(marker.nodeId)
  }, [marker.nodeId, onOpen])

  return (
    <button
      ref={pinRef}
      type="button"
      className={`ccp-marker-pin${isActive ? " is-active" : ""}${commentMode ? " ccp-marker-pin--mode" : ""}`}
      style={{ left: marker.left, top: marker.top }}
      aria-label={ariaLabel}
      onMouseEnter={() => {
        setHovered(true)
        updateTipFlip()
      }}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => {
        setHovered(true)
        updateTipFlip()
      }}
      onBlur={() => setHovered(false)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          handleOpen(e)
        }
      }}
      onClick={handleOpen}
    >
      <span className="ccp-marker-avatar">
        <CommentPinAvatar msg={marker.msg} currentUserId={currentUserId} username={username} />
      </span>
      {marker.unread && <span className="ccp-marker-unread-dot" aria-hidden />}
      {hovered && (authorName || preview) && (
        <span
          className={`ccp-marker-hover-tip${tipFlipLeft ? " ccp-marker-hover-tip--left" : ""}`}
          role="tooltip"
        >
          {authorName && (
            <span className="ccp-marker-hover-tip-name">{authorName}</span>
          )}
          {preview && (
            <span className="ccp-marker-hover-tip-preview">{preview}</span>
          )}
        </span>
      )}
    </button>
  )
}

export default function CanvasCommentMarkers({
  projectId,
  threadsByNode,
  commentMode,
  activeNodeId,
  currentUserId,
  username,
  readTick = 0,
  onOpen,
}) {
  const { t } = useLocale()
  const { getNode } = useReactFlow()
  const nodes = useNodes()
  const { x, y, zoom } = useViewport()

  const markers = useMemo(() => {
    const list = []
    Object.entries(threadsByNode || {}).forEach(([nodeId, thread]) => {
      if (!thread?.messages?.length) return
      const node = getNode(nodeId)
      if (!node) return
      const pin = getCommentPinPosition(node)
      if (!pin) return
      const firstMsg = thread.messages[0]
      list.push({
        nodeId,
        left: pin.left,
        top: pin.top,
        msg: firstMsg,
        unread: isNodeCommentUnread(projectId, nodeId, thread, currentUserId),
      })
    })
    return list
  }, [threadsByNode, getNode, nodes, x, y, zoom, projectId, readTick, currentUserId])

  if (!markers.length) return null

  return (
    <div
      className="ccp-markers-layer"
      style={{
        transform: `translate(${x}px, ${y}px) scale(${zoom})`,
        transformOrigin: "0 0",
      }}
    >
      {markers.map((m) => (
        <CommentMarkerPin
          key={m.nodeId}
          marker={m}
          commentMode={commentMode}
          activeNodeId={activeNodeId}
          currentUserId={currentUserId}
          username={username}
          onOpen={onOpen}
          t={t}
        />
      ))}
    </div>
  )
}
