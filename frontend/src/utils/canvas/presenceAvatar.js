import { ensureMediaUrl } from "../mediaTicket"
import { readUserAvatar, readUserAvatarRaw } from "./userAvatar"

export function resolveMemberAvatar(member, currentUserId) {
  if (!member) return ""
  let raw = member.avatar_url || ""
  if (currentUserId != null && Number(member.user_id) === Number(currentUserId)) {
    raw = readUserAvatarRaw() || raw
  }
  if (!raw) return ""
  if (raw.startsWith("data:") || raw.startsWith("blob:")) return raw
  return ensureMediaUrl(raw)
}

/** @deprecated presence 不再上传 data URL；保留导出避免旧引用报错 */
export function readPresenceAvatar() {
  const raw = readUserAvatarRaw()
  if (!raw || raw.startsWith("data:") || raw.startsWith("blob:")) return ""
  return raw
}
