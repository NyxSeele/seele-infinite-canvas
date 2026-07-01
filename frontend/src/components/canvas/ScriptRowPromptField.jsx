import { useCallback, useMemo, useRef, useState } from "react"
import MentionTextarea from "./MentionTextarea"
import CastMentionPicker from "./CastMentionPicker"
import { formatScreenplayParagraphs } from "../../utils/canvas/textFormat"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { mergeCastAndGlobalAssets } from "../../utils/canvas/globalAssets"
import { resolveCastMentionsInText } from "../../utils/canvas/castLibrary"
import { useAssetStore } from "../../stores/assetStore"
import { useLocale } from "../../utils/locale"
import "./ScriptRowPromptField.css"

const sp = (e) => e.stopPropagation()

export default function ScriptRowPromptField({
  value = "",
  mentions = [],
  castLibrary = [],
  onChange,
  onPointerDown,
  placeholder,
  readOnly = false,
}) {
  const { t } = useLocale()
  const resolvedPlaceholder = placeholder ?? t("canvas.script.directorPh")
  const [atOpen, setAtOpen] = useState(false)
  const [atQuery, setAtQuery] = useState("")
  const editorRef = useRef(null)
  const globalAssets = useAssetStore((s) => s.assets)

  const mergedCast = useMemo(
    () => mergeCastAndGlobalAssets(castLibrary, globalAssets),
    [castLibrary, globalAssets]
  )

  const filteredCast = useMemo(() => {
    const q = atQuery.trim().toLowerCase()
    if (!q) return mergedCast
    return mergedCast.filter((c) => c.name.toLowerCase().includes(q))
  }, [mergedCast, atQuery])

  const displayMentions = useMemo(() => {
    const fromText = resolveCastMentionsInText(value, castLibrary, globalAssets)
    const byId = new Map()
    for (const m of [...(mentions || []), ...fromText]) {
      if (!m?.id && !m?.name) continue
      const key = m.id || m.name
      const cast = mergedCast.find((c) => c.id === m.id || c.name === m.name)
      byId.set(key, cast ? { ...m, imageUrl: cast.imageUrl } : m)
    }
    return [...byId.values()]
  }, [value, mentions, castLibrary, globalAssets, mergedCast])

  const handleMentionQuery = useCallback((payload) => {
    if (payload?.active) {
      setAtOpen(true)
      setAtQuery(payload.query || "")
    } else {
      setAtOpen(false)
      setAtQuery("")
    }
  }, [])

  const handleEditorChange = useCallback(
    ({ text, mentions: nextMentions }) => {
      const enriched = (nextMentions || []).map((m) => {
        const cast = mergedCast.find(
          (c) => c.id === m.id || c.name === m.name
        )
        if (!cast) return m
        if (cast.source === "global") {
          return {
            ...m,
            type: "asset",
            id: cast.id,
            name: cast.name,
            imageUrl: cast.imageUrl,
          }
        }
        return {
          ...m,
          type: "cast",
          id: cast.id,
          name: cast.name,
          imageUrl: cast.imageUrl,
        }
      })
      onChange?.({ prompt: text, description: text, promptMentions: enriched })
    },
    [mergedCast, onChange]
  )

  const handleBlur = useCallback(() => {
    const formatted = formatScreenplayParagraphs(value)
    if (formatted !== value) {
      onChange?.({
        prompt: formatted,
        description: formatted,
        promptMentions: mentions,
      })
    }
  }, [value, mentions, onChange])

  const getMentionImage = useCallback(
    (id, name) => {
      const item = mergedCast.find((c) => c.id === id || c.name === name)
      return item?.imageUrl ? ensureMediaUrl(item.imageUrl) : null
    },
    [mergedCast]
  )

  const handleCastSelect = useCallback((item) => {
    editorRef.current?.insertMention({
      id: item.id,
      type: item.source === "global" ? "asset" : "cast",
      name: item.name,
    })
    setAtOpen(false)
    setAtQuery("")
  }, [])

  if (readOnly) {
    return (
      <div className="st-prompt-field st-prompt-field--readonly nodrag" onPointerDown={onPointerDown || sp}>
        <p className="st-prompt-readonly cn-body">{value || resolvedPlaceholder}</p>
      </div>
    )
  }

  return (
    <div className="st-prompt-field nodrag" onPointerDown={onPointerDown || sp}>
      <CastMentionPicker
        open={atOpen}
        items={filteredCast}
        onSelect={handleCastSelect}
        onClose={() => setAtOpen(false)}
      />
      <MentionTextarea
        ref={editorRef}
        className="st-prompt-input mention-editor--script-row nodrag nowheel"
        placeholder={resolvedPlaceholder}
        value={value}
        mentions={displayMentions}
        getMentionImage={getMentionImage}
        onChange={handleEditorChange}
        onMentionQuery={handleMentionQuery}
        onPointerDown={sp}
        onMouseDown={sp}
        onBlur={handleBlur}
      />
    </div>
  )
}
