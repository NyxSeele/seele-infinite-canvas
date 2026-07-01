import { useState } from "react"
import { LineIcon } from "../icons/LineIcons"
import { ensureMediaUrl } from "../../utils/mediaTicket"

export function parseUpdatedAt(iso) {
  if (!iso) return null
  const raw = String(iso)
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`
  const ts = Date.parse(normalized)
  return Number.isFinite(ts) ? ts : null
}

export function formatProjectDate(iso, neverEditedLabel = "尚未编辑") {
  const ts = parseUpdatedAt(iso)
  if (!ts) return neverEditedLabel
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function ProjectThumb({ previewUrl, empty }) {
  const [broken, setBroken] = useState(false)
  if (!previewUrl || broken) {
    return (
      <span className="ws-project-thumb-placeholder">
        <LineIcon name={empty ? "plus" : "thumb"} size={28} />
      </span>
    )
  }
  const url = ensureMediaUrl(previewUrl)
  const isVideo = /\.(mp4|webm|mov)(\?|$)/i.test(url)
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
