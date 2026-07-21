import { resolveMemberAvatar } from "../../utils/canvas/presenceAvatar"
import "./CollaboratorAvatars.css"

function CollaboratorAvatar({ member, index }) {
  const label = member.display_name || member.username || ""
  const letter = (label[0] || "U").toUpperCase()
  const url = resolveMemberAvatar(member, null)

  return (
    <span
      className="ws-collab-avatar"
      style={{ "--ws-collab-index": index }}
      title={label}
    >
      {url ? (
        <img src={url} alt="" className="ws-collab-avatar-img" draggable={false} />
      ) : (
        <span className="ws-collab-avatar-letter">{letter}</span>
      )}
    </span>
  )
}

export default function CollaboratorAvatars({
  collaborators = [],
  extraCount = 0,
}) {
  if (!collaborators.length) return null

  const visible = collaborators.slice(0, 3)
  const extra = extraCount > 0 ? extraCount : Math.max(0, collaborators.length - 3)
  if (!visible.length) return null

  return (
    <div className="ws-collab-avatars" aria-label="Recent collaborators">
      {visible.map((member, index) => (
        <CollaboratorAvatar
          key={member.user_id ?? index}
          member={member}
          index={index}
        />
      ))}
      {extra > 0 && <span className="ws-collab-extra">+{extra}</span>}
    </div>
  )
}
