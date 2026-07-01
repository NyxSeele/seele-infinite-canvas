import { useEffect, useState } from "react"
import { useLocale } from "../../utils/locale"
import { resolveMemberAvatar } from "../../utils/canvas/presenceAvatar"
import { AVATAR_CHANGED_EVENT } from "../../utils/canvas/userAvatar"
import "./CanvasPresenceBar.css"

function PresenceAvatar({ member, currentUserId }) {
  const { t } = useLocale()
  const [avatarTick, setAvatarTick] = useState(0)

  useEffect(() => {
    const onAvatar = () => setAvatarTick((n) => n + 1)
    window.addEventListener(AVATAR_CHANGED_EVENT, onAvatar)
    return () => window.removeEventListener(AVATAR_CHANGED_EVENT, onAvatar)
  }, [])

  void avatarTick
  const label = member.display_name || member.username || ""
  const letter = (label[0] || "U").toUpperCase()
  const url = resolveMemberAvatar(member, currentUserId)
  const roleLabel = member.is_editor
    ? t("canvas.presence.roleEditor")
    : t("canvas.presence.roleViewer")

  return (
    <span className="cprs-avatar-wrap">
      <span
        className={`cprs-avatar${member.is_editor ? " cprs-avatar--editor" : ""}`}
        tabIndex={0}
      >
        {url ? (
          <img src={url} alt="" className="cprs-avatar-img" draggable={false} />
        ) : (
          <span className="cprs-avatar-letter">{letter}</span>
        )}
      </span>
      <div className="cprs-popover" role="tooltip">
        <div className="cprs-popover-inner">
          <div className="cprs-popover-head">
            <span className={`cprs-popover-avatar${member.is_editor ? " cprs-popover-avatar--editor" : ""}`}>
              {url ? (
                <img src={url} alt="" className="cprs-avatar-img" draggable={false} />
              ) : (
                <span className="cprs-avatar-letter">{letter}</span>
              )}
            </span>
            <div className="cprs-popover-meta">
              <span className="cprs-popover-name">{label}</span>
              {member.email ? (
                <span className="cprs-popover-email">{member.email}</span>
              ) : member.username && member.username !== label ? (
                <span className="cprs-popover-email">@{member.username}</span>
              ) : null}
            </div>
          </div>
          <span className={`cprs-popover-role${member.is_editor ? " cprs-popover-role--editor" : ""}`}>
            {roleLabel}
          </span>
        </div>
      </div>
    </span>
  )
}

export default function CanvasPresenceBar({ members = [], inline = false, currentUserId = null }) {
  const { t } = useLocale()
  const count = members.length
  const visible = members.slice(0, 6)
  const extra = count - visible.length

  return (
    <div
      className={`cprs-bar${inline ? " cprs-bar--inline" : ""}`}
      title={t("canvas.presence.title", { n: count || 1 })}
    >
      <span className="cprs-label">
        {count > 0
          ? t("canvas.presence.online", { n: count })
          : t("canvas.presence.connecting")}
      </span>
      <div className="cprs-avatars">
        {visible.map((m) => (
          <PresenceAvatar key={m.user_id} member={m} currentUserId={currentUserId} />
        ))}
        {extra > 0 && <span className="cprs-more">+{extra}</span>}
      </div>
    </div>
  )
}
