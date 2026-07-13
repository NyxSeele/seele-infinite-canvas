import { useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { formatRelativeTime } from "../../utils/canvas/formatRelativeTime"
import { useLocale } from "../../utils/locale"
import { AVATAR_CHANGED_EVENT } from "../../utils/canvas/userAvatar"
import { resolveCommentAuthorName, resolveCommentAvatar } from "../../utils/canvas/commentUserDisplay"
import { getThemePageClass, getThemePortalRoot } from "../../utils/themePortalRoot"
import { Z_COMMENT_MSG_MENU } from "../../utils/zIndexLayers"
import "./CanvasCommentPanel.css"

const PANEL_WIDTH = 360
const PANEL_GAP = 12
const PANEL_MAX_H = 520

const MAX_LEN = 200

const TEAM_ROLE_KEYS = {
  owner: "canvas.comment.roleOwner",
  admin: "canvas.comment.roleAdmin",
  member: "canvas.comment.roleMember",
}

function CommentAuthorPreview({ open, anchorRef, member, authorName, avatar, imgBroken, onImgError, isMine, t, onClose, onMouseEnter, onMouseLeave }) {
  const wrapRef = useRef(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })

  useEffect(() => {
    if (!open || !anchorRef?.current) return undefined
    const update = () => {
      const r = anchorRef.current.getBoundingClientRect()
      setPos({ top: r.bottom + 6, left: r.left })
    }
    update()
    window.addEventListener("resize", update)
    window.addEventListener("scroll", update, true)
    return () => {
      window.removeEventListener("resize", update)
      window.removeEventListener("scroll", update, true)
    }
  }, [open, anchorRef])

  useEffect(() => {
    if (!open || onMouseEnter) return undefined
    const close = (e) => {
      if (wrapRef.current?.contains(e.target)) return
      if (anchorRef?.current?.contains(e.target)) return
      onClose?.()
    }
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [open, onClose, anchorRef, onMouseEnter])

  if (!open) return null

  const roleKey = TEAM_ROLE_KEYS[member?.role] || TEAM_ROLE_KEYS.member
  const letter = (authorName?.[0] || "U").toUpperCase()

  return createPortal(
    <div
      className={`ccp-author-preview ccp-author-preview--fixed ${getThemePageClass()}`}
      ref={wrapRef}
      style={{ top: pos.top, left: pos.left }}
      onPointerDown={(e) => e.stopPropagation()}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="ccp-author-preview-avatar">
        {avatar && !imgBroken ? (
          <img src={avatar} alt="" className="ccp-avatar-img" draggable={false} onError={onImgError} />
        ) : (
          letter
        )}
      </div>
      <div className="ccp-author-preview-text">
        <span className="ccp-author-preview-name">
          {authorName}
          {isMine && <span className="ccp-author-preview-you">{t("canvas.comment.you")}</span>}
        </span>
        {member?.email && <span className="ccp-author-preview-email">{member.email}</span>}
        {member?.role && (
          <span className="ccp-author-preview-role">{t(roleKey)}</span>
        )}
        {!member?.email && !member?.role && (
          <span className="ccp-author-preview-hint">{t("canvas.comment.authorHint")}</span>
        )}
      </div>
    </div>,
    getThemePortalRoot(),
  )
}

function MessageMenu({ onEdit, onDelete, t }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const btnRef = useRef(null)
  const menuRef = useRef(null)
  const [menuStyle, setMenuStyle] = useState(null)

  useEffect(() => {
    if (!open) {
      setMenuStyle(null)
      return undefined
    }
    const update = () => {
      const r = btnRef.current?.getBoundingClientRect()
      if (!r) return
      const menuW = 120
      setMenuStyle({
        position: "fixed",
        top: r.bottom + 6,
        left: Math.max(8, r.right - menuW),
        minWidth: menuW,
        zIndex: Z_COMMENT_MSG_MENU,
      })
    }
    update()
    window.addEventListener("resize", update)
    window.addEventListener("scroll", update, true)
    return () => {
      window.removeEventListener("resize", update)
      window.removeEventListener("scroll", update, true)
    }
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => {
      const path = e.composedPath?.() || []
      if (wrapRef.current && path.includes(wrapRef.current)) return
      if (menuRef.current && path.includes(menuRef.current)) return
      setOpen(false)
    }
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [open])

  const menuPortal = open && menuStyle
    ? createPortal(
        <div
          ref={menuRef}
          className={`ccp-msg-menu ccp-msg-menu--portal ${getThemePageClass()}`}
          style={menuStyle}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <button type="button" onClick={() => { setOpen(false); onEdit?.() }}>
            <span className="ccp-menu-icon">✎</span>
            {t("canvas.common.edit")}
          </button>
          <button type="button" className="ccp-menu-danger" onClick={() => { setOpen(false); onDelete?.() }}>
            <span className="ccp-menu-icon">🗑</span>
            {t("canvas.common.delete")}
          </button>
        </div>,
        getThemePortalRoot(),
      )
    : null

  return (
    <div className={`ccp-msg-menu-wrap${open ? " is-open" : ""}`} ref={wrapRef}>
      <button
        ref={btnRef}
        type="button"
        className="ccp-msg-menu-btn"
        aria-label={t("canvas.common.more")}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        ···
      </button>
      {menuPortal}
    </div>
  )
}

function MessageItem({ msg, currentUserId, username, teamMembers, onEdit, onDelete, highlighted, t }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(msg.body)
  const [avatarTick, setAvatarTick] = useState(0)
  const [imgBroken, setImgBroken] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const rootRef = useRef(null)
  const avatarBtnRef = useRef(null)
  const previewLeaveTimerRef = useRef(null)
  const isMine = currentUserId != null && Number(msg.author_id) === Number(currentUserId)
  const authorName = resolveCommentAuthorName(msg, currentUserId, username)
  const member = (teamMembers || []).find((m) => Number(m.user_id) === Number(msg.author_id))
  void avatarTick
  const avatar = resolveCommentAvatar(msg, currentUserId)

  useEffect(() => {
    const onChange = () => setAvatarTick((n) => n + 1)
    window.addEventListener(AVATAR_CHANGED_EVENT, onChange)
    return () => window.removeEventListener(AVATAR_CHANGED_EVENT, onChange)
  }, [])

  useEffect(() => {
    setImgBroken(false)
  }, [msg?.id, msg?.author_avatar_url, msg?.author_id, avatarTick])

  const showAuthorPreview = () => {
    clearTimeout(previewLeaveTimerRef.current)
    setPreviewOpen(true)
  }

  const hideAuthorPreview = () => {
    previewLeaveTimerRef.current = setTimeout(() => setPreviewOpen(false), 120)
  }

  const saveEdit = async () => {
    const text = draft.trim()
    if (!text || text === msg.body) {
      setEditing(false)
      setDraft(msg.body)
      return
    }
    await onEdit(text)
    setEditing(false)
  }

  return (
    <div
      ref={rootRef}
      className={`ccp-msg${highlighted ? " ccp-msg--highlight" : ""}`}
      data-message-id={msg.id}
    >
      <div className="ccp-msg-aside">
        <span className="ccp-avatar-wrap">
          <button
            ref={avatarBtnRef}
            type="button"
            className="ccp-avatar ccp-avatar-btn"
            aria-label={t("canvas.comment.viewProfile")}
            onMouseEnter={showAuthorPreview}
            onMouseLeave={hideAuthorPreview}
          >
            {avatar && !imgBroken ? (
              <img
                src={avatar}
                alt=""
                className="ccp-avatar-img"
                draggable={false}
                onError={() => setImgBroken(true)}
              />
            ) : (
              (authorName?.[0] || "U").toUpperCase()
            )}
          </button>
          <CommentAuthorPreview
            open={previewOpen}
            anchorRef={avatarBtnRef}
            member={member}
            authorName={authorName}
            avatar={avatar}
            imgBroken={imgBroken}
            onImgError={() => setImgBroken(true)}
            isMine={isMine}
            t={t}
            onClose={() => setPreviewOpen(false)}
            onMouseEnter={showAuthorPreview}
            onMouseLeave={hideAuthorPreview}
          />
        </span>
      </div>
      <div className="ccp-msg-content">
        <div className="ccp-msg-meta">
          <span className="ccp-msg-author">{authorName}</span>
          <span className="ccp-msg-time">{formatRelativeTime(msg.created_at)}</span>
          {isMine && !editing && (
            <MessageMenu
              onEdit={() => setEditing(true)}
              onDelete={onDelete}
              t={t}
            />
          )}
        </div>
        {editing ? (
          <div className="ccp-edit-row">
            <textarea
              className="ccp-textarea nodrag"
              value={draft}
              maxLength={MAX_LEN}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
            />
            <div className="ccp-edit-actions">
              <button type="button" className="ccp-btn-ghost" onClick={() => { setEditing(false); setDraft(msg.body) }}>{t("canvas.common.cancel")}</button>
              <button type="button" className="ccp-btn-primary" onClick={saveEdit}>{t("canvas.common.save")}</button>
            </div>
          </div>
        ) : (
          <p className="ccp-msg-body">{msg.body}</p>
        )}
      </div>
    </div>
  )
}

function getMentionQuery(text, caret) {
  const before = text.slice(0, caret)
  const match = before.match(/@([\w\u4e00-\u9fff.-]*)$/)
  if (!match) return null
  return match[1] || ""
}

export default function CanvasCommentPanel({
  open,
  nodeId,
  nodeLabel,
  anchor,
  thread,
  currentUserId,
  onClose,
  onSubmit,
  onEditMessage,
  onDeleteMessage,
  displayName,
  username,
  teamMembers = [],
  highlightMessageIds = [],
}) {
  const { t } = useLocale()
  const [text, setText] = useState("")
  const [mentions, setMentions] = useState([])
  const [mentionOpen, setMentionOpen] = useState(false)
  const [mentionQuery, setMentionQuery] = useState("")
  const [busy, setBusy] = useState(false)
  const [scrollToMessageId, setScrollToMessageId] = useState(null)
  const [messagesEntering, setMessagesEntering] = useState(false)
  const inputRef = useRef(null)
  const messagesRef = useRef(null)
  const pendingOpenScrollRef = useRef(null)

  const panelStyle = useMemo(() => {
    if (!anchor) {
      return { top: 72, right: 20, left: "auto" }
    }
    const maxH = Math.min(PANEL_MAX_H, window.innerHeight - 100)
    let left = anchor.left + anchor.width + PANEL_GAP
    if (left + PANEL_WIDTH > window.innerWidth - 16) {
      left = anchor.left - PANEL_WIDTH - PANEL_GAP
    }
    left = Math.max(16, Math.min(left, window.innerWidth - PANEL_WIDTH - 16))
    let top = anchor.top
    if (top + maxH > window.innerHeight - 16) {
      top = window.innerHeight - maxH - 16
    }
    top = Math.max(64, top)
    return { position: "fixed", left, top, right: "auto", width: PANEL_WIDTH, maxHeight: maxH }
  }, [anchor])

  const mentionCandidates = useMemo(() => {
    const q = mentionQuery.trim().toLowerCase()
    return (teamMembers || [])
      .filter((m) => Number(m.user_id) !== Number(currentUserId))
      .filter((m) => {
        if (!q) return true
        const name = (m.username || "").toLowerCase()
        const email = (m.email || "").toLowerCase()
        return name.includes(q) || email.includes(q)
      })
      .slice(0, 8)
  }, [teamMembers, mentionQuery, currentUserId])

  useEffect(() => {
    if (open) {
      setText("")
      setMentions([])
      setMentionOpen(false)
      setScrollToMessageId(null)
      pendingOpenScrollRef.current = nodeId
      setMessagesEntering(true)
      setTimeout(() => inputRef.current?.focus(), 50)
    } else {
      pendingOpenScrollRef.current = null
    }
  }, [open, nodeId])

  const messages = thread?.messages || []

  const scrollMessagesToBottom = (behavior = "smooth") => {
    const el = messagesRef.current
    if (!el) return
    const lastId = messages[messages.length - 1]?.id
    const lastEl = lastId ? el.querySelector(`[data-message-id="${lastId}"]`) : null
    if (lastEl) {
      lastEl.scrollIntoView({ block: "end", behavior })
    } else {
      el.scrollTo({ top: el.scrollHeight, behavior })
    }
  }

  useEffect(() => {
    if (!open || !nodeId || !messagesRef.current || !messages.length) return undefined
    if (pendingOpenScrollRef.current !== nodeId) return undefined
    const timer = window.setTimeout(() => {
      scrollMessagesToBottom("smooth")
      pendingOpenScrollRef.current = null
      window.setTimeout(() => setMessagesEntering(false), 480)
    }, 100)
    return () => window.clearTimeout(timer)
  }, [open, nodeId, messages])

  useEffect(() => {
    if (!scrollToMessageId || !messagesRef.current) return undefined
    const el = messagesRef.current
    const target = el.querySelector(`[data-message-id="${scrollToMessageId}"]`)
    if (!target) return undefined
    const timer = window.setTimeout(() => {
      target.scrollIntoView({ block: "end", behavior: "smooth" })
      setScrollToMessageId(null)
    }, 80)
    return () => window.clearTimeout(timer)
  }, [scrollToMessageId, messages])

  if (!open || !nodeId) return null

  const hasMessages = messages.length > 0
  const placeholder = hasMessages ? t("canvas.comment.replyPh") : t("canvas.comment.inputPh")

  const updateMentionState = (value, caret) => {
    const query = getMentionQuery(value, caret ?? value.length)
    if (query == null) {
      setMentionOpen(false)
      setMentionQuery("")
      return
    }
    setMentionOpen(true)
    setMentionQuery(query)
  }

  const insertMention = (member) => {
    const label = member.username || String(member.user_id)
    const el = inputRef.current
    const caret = el?.selectionStart ?? text.length
    const before = text.slice(0, caret)
    const after = text.slice(caret)
    const replaced = before.replace(/@([\w\u4e00-\u9fff.-]*)$/, `@${label} `)
    const next = `${replaced}${after}`
    setText(next.slice(0, MAX_LEN))
    setMentions((prev) => {
      if (prev.some((m) => Number(m.user_id) === Number(member.user_id))) return prev
      return [...prev, { user_id: member.user_id, username: label }]
    })
    setMentionOpen(false)
    setMentionQuery("")
    window.setTimeout(() => {
      if (el) {
        el.focus()
        const pos = replaced.length
        el.setSelectionRange(pos, pos)
      }
    }, 0)
  }

  const handleSend = async () => {
    const body = text.trim()
    if (!body || busy) return
    const mentionedUserIds = mentions
      .filter((m) => body.includes(`@${m.username}`))
      .map((m) => m.user_id)
    setBusy(true)
    try {
      const thread = await onSubmit(body, mentionedUserIds)
      setText("")
      setMentions([])
      setMentionOpen(false)
      const lastId = thread?.messages?.[thread.messages.length - 1]?.id
      if (lastId) setScrollToMessageId(lastId)
    } finally {
      setBusy(false)
    }
  }

  const handleKeyDown = (e) => {
    if (mentionOpen && e.key === "Escape") {
      e.preventDefault()
      setMentionOpen(false)
      return
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      className="ccp-panel nodrag nopan"
      style={panelStyle}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <header className="ccp-head">
        <div>
          <h3>{t("canvas.comment.cardTitle")}</h3>
          {nodeLabel && <p className="ccp-sub">{nodeLabel}</p>}
        </div>
        <button type="button" className="ccp-close" onClick={onClose} aria-label={t("canvas.common.close")}>×</button>
      </header>

      <div className={`ccp-messages${messagesEntering ? " ccp-messages--entering" : ""}`} ref={messagesRef}>
        {hasMessages ? (
          messages.map((msg) => (
            <MessageItem
              key={msg.id}
              msg={msg}
              currentUserId={currentUserId}
              username={username}
              teamMembers={teamMembers}
              highlighted={highlightMessageIds.includes(msg.id)}
              onEdit={(body) => onEditMessage(msg.id, body)}
              onDelete={() => onDeleteMessage(msg.id)}
              t={t}
            />
          ))
        ) : (
          <p className="ccp-empty">{t("canvas.comment.hint")}</p>
        )}
      </div>

      <footer className="ccp-compose">
        {mentionOpen && mentionCandidates.length > 0 && (
          <div className="ccp-mention-list">
            {mentionCandidates.map((member) => (
              <button
                key={member.user_id}
                type="button"
                className="ccp-mention-item"
                onClick={() => insertMention(member)}
              >
                <span className="ccp-mention-name">@{member.username}</span>
                {member.email && <span className="ccp-mention-email">{member.email}</span>}
              </button>
            ))}
          </div>
        )}
        <textarea
          ref={inputRef}
          className="ccp-textarea nodrag"
          placeholder={placeholder}
          value={text}
          maxLength={MAX_LEN}
          rows={2}
          onChange={(e) => {
            setText(e.target.value)
            updateMentionState(e.target.value, e.target.selectionStart)
          }}
          onClick={(e) => updateMentionState(text, e.target.selectionStart)}
          onKeyUp={(e) => updateMentionState(text, e.target.selectionStart)}
          onKeyDown={handleKeyDown}
        />
        <div className="ccp-compose-foot">
          <span className="ccp-count">{text.length}/{MAX_LEN}</span>
          <button
            type="button"
            className="ccp-send"
            disabled={!text.trim() || busy}
            onClick={handleSend}
            aria-label={t("canvas.common.send")}
          >
            ↑
          </button>
        </div>
      </footer>
    </div>
  )
}
