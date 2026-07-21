import { useState } from "react"
import { LineIcon } from "../icons/LineIcons"
import { ensureMediaUrl } from "../../utils/mediaTicket"
export {
  formatProjectDate,
  formatProjectActivityTime,
  parseUpdatedAt,
  parseServerTimestamp,
} from "../../utils/datetime"

const ACCENT_PALETTES = [
  { from: "#7B68EE", to: "#B8A9FF", tone: "purple" },
  { from: "#4F8CFF", to: "#7EC8FF", tone: "blue" },
  { from: "#FF8A4C", to: "#FFC27A", tone: "orange" },
  { from: "#9B59F5", to: "#E0B0FF", tone: "violet" },
  { from: "#2EC4B6", to: "#7ADFE6", tone: "teal" },
]

/** 按项目 id 生成差异化渐变封面色 */
export function hashProjectAccent(projectId) {
  if (!projectId) return ACCENT_PALETTES[0]
  let hash = 0
  for (let i = 0; i < projectId.length; i += 1) {
    hash = (hash * 31 + projectId.charCodeAt(i)) >>> 0
  }
  return ACCENT_PALETTES[hash % ACCENT_PALETTES.length]
}

export function ProjectThumb({ previewUrl, coverMediaType, empty, projectId, compact }) {
  const [broken, setBroken] = useState(false)
  if (!previewUrl || broken) {
    if (empty) {
      return (
        <span className="ws-project-thumb-placeholder ws-project-thumb-placeholder--new">
          <LineIcon name="plus" size={compact ? 18 : 28} />
        </span>
      )
    }
    const accent = hashProjectAccent(projectId)
    return (
      <span
        className="ws-project-thumb-placeholder ws-project-thumb-placeholder--accent"
        style={{
          "--ws-thumb-from": accent.from,
          "--ws-thumb-to": accent.to,
        }}
      />
    )
  }
  const url = ensureMediaUrl(previewUrl)
  const isVideo = coverMediaType === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(url)
  if (isVideo) {
    return (
      <video
        src={url}
        muted
        playsInline
        onError={() => setBroken(true)}
      />
    )
  }
  return (
    <img src={url} alt="" draggable={false} onError={() => setBroken(true)} />
  )
}

export function RatioShape({ w, h }) {
  if (w === 0 && h === 0) {
    return (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
        <rect
          x="4"
          y="4"
          width="10"
          height="10"
          rx="1.5"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeDasharray="2.5 2"
        />
      </svg>
    )
  }
  const max = 14
  const denom = Math.max(w, h, 1)
  const rw = Math.max(4, Math.round((w / denom) * max))
  const rh = Math.max(4, Math.round((h / denom) * max))
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect
        x={(18 - rw) / 2}
        y={(18 - rh) / 2}
        width={rw}
        height={rh}
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1.2"
      />
    </svg>
  )
}

export function getEpisodeOptions(t) {
  const unit = t("ws.episodeUnit")
  return ["5", "10", "30", "60", "80", "100"].map((value) => ({
    value,
    label: value === "5" ? `05 ${unit}` : `${value} ${unit}`,
  }))
}

export function getRatioOptions(t) {
  return [
    { value: "default", label: t("ws.ratio.default"), icon: <RatioShape w={0} h={0} /> },
    { value: "9:16", label: t("ws.ratio.9_16"), icon: <RatioShape w={9} h={16} /> },
    { value: "16:9", label: t("ws.ratio.16_9"), icon: <RatioShape w={16} h={9} /> },
    { value: "3:4", label: "3:4", icon: <RatioShape w={3} h={4} /> },
    { value: "4:3", label: "4:3", icon: <RatioShape w={4} h={3} /> },
    { value: "1:1", label: "1:1", icon: <RatioShape w={1} h={1} /> },
  ]
}

export function getProjectActivityLabels(t) {
  return {
    neverEdited: t("ws.project.neverEdited"),
    justNow: t("ws.time.justNow"),
    minutesAgo: (n) => t("ws.time.minutesAgo", { n }),
    hoursAgo: (n) => t("ws.time.hoursAgo", { n }),
    todayAt: (hm) => t("ws.time.todayAt", { time: hm }),
    daysAgo: (n) => t("ws.time.daysAgo", { n }),
    weeksAgo: (n) => t("ws.time.weeksAgo", { n }),
  }
}
