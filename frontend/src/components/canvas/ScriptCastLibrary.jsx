import { useCallback, useEffect, useState } from "react"
import { useReferenceSelect } from "./CanvasActionsContext"
import AddRefHoverPanel from "./AddRefHoverPanel"
import { uploadImageFile } from "../../services/uploadImage"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { useAssetStore, useCanvasStore } from "../../stores"
import { getActiveTeamId } from "../../utils/teamContext"
import { assetKindToCastType, isSubjectKind } from "../../utils/canvas/globalAssets"
import {
  makeCastRefId,
  normalizeCastLibrary,
} from "../../utils/canvas/castLibrary"
import { isRecentlyUsed, sortLibraryEntries } from "../../utils/canvas/libraryUsage"
import { useLocale } from "../../utils/locale"
import "./ScriptCastLibrary.css"
import "./canvasTypography.css"

const sp = (e) => e.stopPropagation()

export default function ScriptCastLibrary({
  nodeId,
  castLibrary = [],
  onChange,
  readOnly = false,
}) {
  const { t } = useLocale()
  const refSelect = useReferenceSelect()
  const assets = useAssetStore((s) => s.assets)
  const teamAssets = useAssetStore((s) => s.teamAssets)
  const fetchAssets = useAssetStore((s) => s.fetchAssets)
  const fetchTeamAssets = useAssetStore((s) => s.fetchTeamAssets)
  const projectTeamId = useCanvasStore((s) => s.projectTeamId)
  const teamId = projectTeamId ?? getActiveTeamId()
  const [newName, setNewName] = useState("")
  const [sortMode, setSortMode] = useState("default")

  useEffect(() => {
    fetchAssets()
  }, [fetchAssets])

  useEffect(() => {
    if (teamId) fetchTeamAssets(false, teamId)
  }, [fetchTeamAssets, teamId])

  const sync = useCallback(
    (next) => {
      onChange?.(normalizeCastLibrary(next, { requireImage: false }))
    },
    [onChange]
  )

  const addEntry = useCallback(
    (name, imageUrl) => {
      const trimmed = String(name || "").trim()
      if (!trimmed || !imageUrl) return
      sync([
        ...castLibrary.filter((c) => c.type !== "scene"),
        { id: makeCastRefId(), name: trimmed, type: "character", imageUrl },
      ])
      setNewName("")
    },
    [castLibrary, sync]
  )

  const removeEntry = useCallback(
    (id) => {
      sync(castLibrary.filter((c) => c.id !== id))
    },
    [castLibrary, sync]
  )

  const handleUpload = useCallback(
    async (file) => {
      if (!file || !newName.trim()) return
      try {
        const url = await uploadImageFile(file)
        addEntry(newName, url)
      } catch (err) {
        console.error("设定图上传失败", err)
      }
    },
    [newName, addEntry]
  )

  const handleCanvasPick = useCallback(() => {
    if (!newName.trim()) return
    refSelect?.enter(nodeId, `castNew:character:${encodeURIComponent(newName.trim())}`)
  }, [nodeId, newName, refSelect])

  const handleQuickSelect = useCallback(
    (item) => {
      if (!newName.trim()) return
      addEntry(newName, item.url)
    },
    [newName, addEntry]
  )

  const characterLibrary = castLibrary.filter((c) => c.type !== "scene")
  const displayLibrary = sortLibraryEntries(characterLibrary, sortMode)

  const assetPool = teamId ? (teamAssets || []) : (assets || [])
  const importableAssets = (assetPool || []).filter(
    (a) =>
      a?.name
      && a?.imageUrl
      && isSubjectKind(a.kind)
      && assetKindToCastType(a.kind) !== "scene"
      && !characterLibrary.some((c) => c.name?.toLowerCase() === a.name.toLowerCase())
  )

  const importAsset = useCallback(
    (asset) => {
      if (!asset) return
      sync([
        ...characterLibrary,
        {
          id: makeCastRefId(),
          name: asset.name,
          type: "character",
          imageUrl: asset.imageUrl,
          globalAssetId: asset.id,
        },
      ])
      setNewName("")
    },
    [characterLibrary, sync]
  )

  return (
    <div className="st-cast-lib nodrag" onPointerDown={sp} onDoubleClick={sp}>
      {characterLibrary.length > 1 && (
        <div className="st-lib-sort-row nodrag">
          <select
            className="st-lib-sort-select nodrag"
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value)}
            onPointerDown={sp}
          >
            <option value="default">{t("canvas.script.castSortDefault")}</option>
            <option value="recent">{t("canvas.script.castSortRecent")}</option>
          </select>
        </div>
      )}
      {!readOnly && (
        <div className="st-cast-add-row">
          <input
            className="st-cast-name nodrag"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t("canvas.script.castNamePh")}
            onPointerDown={sp}
          />
          <AddRefHoverPanel
            buttonClassName="st-cast-add-btn nodrag"
            buttonContent={t("canvas.script.addRefImg")}
            trigger="click"
            disabled={!newName.trim()}
            assetEntries={importableAssets}
            onAssetPick={importAsset}
            onQuickSelect={handleQuickSelect}
            onCanvasPick={handleCanvasPick}
            onUpload={(file) => handleUpload(file)}
          />
        </div>
      )}

      {characterLibrary.length > 0 ? (
        <div className="st-cast-chips">
          {displayLibrary.map((item) => (
            <div key={item.id} className="st-cast-chip">
              {item.imageUrl ? (
                <img
                  src={ensureMediaUrl(item.imageUrl)}
                  alt=""
                  draggable={false}
                  className="st-cast-thumb"
                />
              ) : (
                <div className="st-cast-thumb st-cast-thumb--pending" aria-hidden>
                  ?
                </div>
              )}
              <div className="st-cast-chip-meta">
                <span className="st-cast-chip-type">
                  {t("canvas.script.person")}
                </span>
                <span className="st-cast-chip-name">{item.name}</span>
                {isRecentlyUsed(item) ? (
                  <span className="st-cast-chip-recent">{t("canvas.script.castSortRecent")}</span>
                ) : null}
                {!item.imageUrl ? (
                  <span className="st-cast-chip-pending">{t("canvas.script.castPending")}</span>
                ) : null}
              </div>
              {!readOnly && (
                <button
                  type="button"
                  className="st-cast-chip-remove nodrag"
                  onClick={() => removeEntry(item.id)}
                  onPointerDown={sp}
                  aria-label={t("canvas.common.delete")}
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="st-cast-empty">{t("canvas.script.castEmpty")}</p>
      )}
    </div>
  )
}
