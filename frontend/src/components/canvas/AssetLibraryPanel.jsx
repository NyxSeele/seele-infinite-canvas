import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useAssetStore } from "../../stores"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { ASSET_KIND_LABELS } from "../../utils/canvas/globalAssets"
import { useLocale } from "../../utils/locale"
import CanvasModelDropup from "./CanvasModelDropup"
import "./AssetLibraryPanel.css"
import "./NodeBanner.css"

const sp = (e) => e.stopPropagation()

function useAssetFilters() {
  const { t } = useLocale()
  return useMemo(() => ([
    { id: "all", label: t("canvas.asset.all") },
    { id: "character", label: t("canvas.asset.character") },
    { id: "scene", label: t("canvas.asset.scene") },
    { id: "prop", label: t("canvas.asset.prop") },
    { id: "other", label: t("canvas.asset.other") },
  ]), [t])
}

function useKindOptions() {
  const { t } = useLocale()
  return useMemo(() => ([
    { id: "character", display_name: t("canvas.asset.character") },
    { id: "scene", display_name: t("canvas.asset.scene") },
    { id: "prop", display_name: t("canvas.asset.prop") },
    { id: "other", display_name: t("canvas.asset.other") },
  ]), [t])
}

export default function AssetLibraryPanel({ variant = "overlay", onClose }) {
  const { t } = useLocale()
  const FILTERS = useAssetFilters()
  const KIND_OPTIONS = useKindOptions()
  const assets = useAssetStore((s) => s.assets)
  const loading = useAssetStore((s) => s.loading)
  const error = useAssetStore((s) => s.error)
  const fetchAssets = useAssetStore((s) => s.fetchAssets)
  const addAssetFromUpload = useAssetStore((s) => s.addAssetFromUpload)
  const removeAsset = useAssetStore((s) => s.removeAsset)

  const [filter, setFilter] = useState("all")
  const [newName, setNewName] = useState("")
  const [newKind, setNewKind] = useState("character")
  const [uploading, setUploading] = useState(false)
  const [toast, setToast] = useState(null)
  const fileRef = useRef(null)

  useEffect(() => {
    fetchAssets()
  }, [fetchAssets])

  useEffect(() => {
    if (variant !== "overlay") return undefined
    const handler = () => fetchAssets(true)
    window.addEventListener("asset-lib-refresh", handler)
    return () => window.removeEventListener("asset-lib-refresh", handler)
  }, [variant, fetchAssets])

  const filtered = useMemo(() => {
    if (filter === "all") return assets
    return assets.filter((a) => a.kind === filter)
  }, [assets, filter])

  const showToast = useCallback((msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 1800)
  }, [])

  const copyMention = useCallback(
    (name) => {
      const token = `@${name}`
      navigator.clipboard.writeText(token).then(
        () => showToast(t("canvas.asset.copiedToken", { token })),
        () => showToast(token)
      )
    },
    [showToast, t]
  )

  const handleUploadPick = useCallback(() => {
    if (!newName.trim()) {
      showToast(t("canvas.asset.needName"))
      return
    }
    fileRef.current?.click()
  }, [newName, showToast])

  const handleFile = useCallback(
    async (e) => {
      const file = e.target.files?.[0]
      e.target.value = ""
      if (!file || !newName.trim()) return
      setUploading(true)
      try {
        await addAssetFromUpload({
          file,
          name: newName.trim(),
          kind: newKind,
        })
        setNewName("")
        showToast(t("canvas.asset.added"))
      } catch (err) {
        console.error(err)
        showToast(t("canvas.asset.uploadFail"))
      } finally {
        setUploading(false)
      }
    },
    [newName, newKind, addAssetFromUpload, showToast, t]
  )

  const handleDelete = useCallback(
    async (id, name) => {
      if (!window.confirm(t("canvas.asset.deleteNamed", { name }))) return
      try {
        await removeAsset(id)
        showToast(t("canvas.asset.deleted"))
      } catch (err) {
        console.error(err)
        showToast(t("canvas.asset.deleteFail"))
      }
    },
    [removeAsset, showToast, t]
  )

  const rootClass =
    variant === "overlay"
      ? "asset-lib-panel asset-lib-panel--overlay"
      : "clt-panel clt-asset-panel"

  return (
    <div className={`${rootClass} nodrag`} onPointerDown={sp}>
      <div className="clt-asset-head">
        <p className="clt-asset-desc">
          {t("canvas.asset.desc")}
        </p>
      </div>

      <div className="clt-asset-filters nodrag" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            className={`clt-asset-filter${filter === f.id ? " clt-asset-filter--active" : ""}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="clt-asset-grid">
        {loading && assets.length === 0 && (
          <div className="clt-panel-empty">{t("canvas.common.loading")}</div>
        )}
        {error && (
          <div className="clt-asset-error">{error}</div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="clt-asset-empty">
            {t("canvas.asset.emptyGrid")}
          </div>
        )}
        {filtered.map((asset) => (
          <div key={asset.id} className="clt-asset-card">
            <button
              type="button"
              className="clt-asset-card-main"
              title={t("canvas.asset.clickCopy")}
              onClick={() => copyMention(asset.name)}
            >
              <img
                src={ensureMediaUrl(asset.imageUrl)}
                alt=""
                className="clt-asset-thumb"
                draggable={false}
              />
              <span className="clt-asset-name">{asset.name}</span>
              <span className="clt-asset-kind">
                {ASSET_KIND_LABELS[asset.kind] || t("canvas.asset.other")}
              </span>
            </button>
            <button
              type="button"
              className="clt-asset-del"
              title={t("canvas.common.delete")}
              onClick={() => handleDelete(asset.id, asset.name)}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <div className="clt-asset-add nodrag">
        <input
          className="clt-asset-input nodrag"
          placeholder={t("canvas.asset.namePh")}
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onPointerDown={sp}
        />
        <CanvasModelDropup
          tag={t("canvas.asset.type")}
          models={KIND_OPTIONS}
          value={newKind}
          direction="down"
          onChange={setNewKind}
          title={t("canvas.asset.assetType")}
        />
        <button
          type="button"
          className="clt-asset-upload-btn"
          disabled={uploading}
          onClick={handleUploadPick}
        >
          {uploading ? t("canvas.upload.uploading") : t("canvas.asset.uploadImage")}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="clt-asset-file"
          onChange={handleFile}
        />
      </div>

      {toast && <div className="clt-asset-toast">{toast}</div>}
    </div>
  )
}
