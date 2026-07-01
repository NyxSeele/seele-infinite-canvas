import { useMemo } from "react"
import { useNodes, useReactFlow, useViewport } from "reactflow"
import { useLocale } from "../../utils/locale"
import { AVATAR_CHANGED_EVENT } from "../../utils/canvas/userAvatar"
import { resolveCommentAuthorName, resolveCommentAvatar } from "../../utils/canvas/commentUserDisplay"
import { getCommentPinPosition } from "../../utils/canvas/commentMarkerLayout"
import { isNodeCommentUnread } from "../../utils/canvas/commentReadState"
import { useEffect, useState } from "react"
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
  }, [threadsByNode, getNode, nodes, x, y, zoom, projectId, readTick])

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
        <button
          key={m.nodeId}
          type="button"
          className={`ccp-marker-pin${activeNodeId === m.nodeId ? " is-active" : ""}${commentMode ? " ccp-marker-pin--mode" : ""}`}
          style={{ left: m.left, top: m.top }}
          title={t("canvas.comment.cardTitle")}
          onClick={(e) => {
            e.stopPropagation()
            onOpen(m.nodeId)
          }}
        >
          <span className="ccp-marker-avatar">
            <CommentPinAvatar msg={m.msg} currentUserId={currentUserId} username={username} />
          </span>
          {m.unread && <span className="ccp-marker-unread-dot" aria-hidden />}
        </button>
      ))}
    </div>
  )
}
