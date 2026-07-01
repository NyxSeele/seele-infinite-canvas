import { useEffect, useState } from "react"
import { readTeamAvatar, teamInitial } from "../../utils/teamAvatar"
import "./TeamAvatar.css"

export default function TeamAvatar({ teamId, name, size = 36, className = "" }) {
  const [avatarUrl, setAvatarUrl] = useState(() => (teamId ? readTeamAvatar(teamId) : ""))

  useEffect(() => {
    const sync = () => setAvatarUrl(teamId ? readTeamAvatar(teamId) : "")
    sync()
    window.addEventListener("team-avatar-changed", sync)
    return () => window.removeEventListener("team-avatar-changed", sync)
  }, [teamId])

  const letter = teamInitial(name, "P")

  return (
    <span
      className={`team-avatar${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      data-has-img={!!avatarUrl}
    >
      {avatarUrl ? (
        <img src={avatarUrl} alt="" draggable={false} />
      ) : (
        letter
      )}
    </span>
  )
}
