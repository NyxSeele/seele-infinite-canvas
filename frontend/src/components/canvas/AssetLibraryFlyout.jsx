import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useStore } from "reactflow"
import { useAuth } from "../../contexts/AuthContext"
import { useAssetStore, useCanvasStore, useTeamStore } from "../../stores"
import { getActiveTeamId } from "../../utils/teamContext"
import { ensureMediaUrl, stripMediaTicket } from "../../utils/mediaTicket"
import {
  ASSET_KIND_LABELS,
  isMaterialKind,
  isSubjectKind,
  normalizeAssetKind,
} from "../../utils/canvas/globalAssets"
import { getImageNodeImages } from "./videoReferenceHelpers"
import { useFlyoutMount } from "../../hooks/useFlyoutMount"
import ScopeSwitchPanel from "../common/ScopeSwitchPanel"
import { useLocale } from "../../utils/locale"
import "./AssetLibraryFlyout.css"

const sp = (e) => e.stopPropagation()

function useMaterialFilters() {
  const { t } = useLocale()
  return useMemo(() => ([
    { id: "all", label: t("canvas.asset.all") },
    { id: "image", label: t("canvas.asset.filterImage") },
    { id: "video", label: t("canvas.asset.filterVideo") },
  ]), [t])
}

function useSubjectFilters() {
  const { t } = useLocale()
  return useMemo(() => ([
    { id: "all", label: t("canvas.asset.all") },
    { id: "character", label: t("canvas.asset.character") },
    { id: "scene", label: t("canvas.asset.scene") },
  ]), [t])
}

export default function AssetLibraryFlyout({ open, onClose, getCardPointerHandlers }) {
  const { t } = useLocale()
  const MATERIAL_FILTERS = useMaterialFilters()
  const SUBJECT_FILTERS = useSubjectFilters()
  const { mounted, closing } = useFlyoutMount(open)
  const { user } = useAuth()
  const canvasId = useCanvasStore((s) => s.canvasId)
  const projectName = useCanvasStore((s) => s.projectName)
  const assets = useAssetStore((s) => s.assets)
  const teamAssets = useAssetStore((s) => s.teamAssets)
  const loading = useAssetStore((s) => s.loading)
  const teamLoading = useAssetStore((s) => s.teamLoading)
  const error = useAssetStore((s) => s.error)
  const fetchAssets = useAssetStore((s) => s.fetchAssets)
  const fetchTeamAssets = useAssetStore((s) => s.fetchTeamAssets)
  const addAssetFromUpload = useAssetStore((s) => s.addAssetFromUpload)
  const addAssetFromUrl = useAssetStore((s) => s.addAssetFromUrl)
  const removeAsset = useAssetStore((s) => s.removeAsset)
  const publishToTeam = useAssetStore((s) => s.publishToTeam)
  const unpublishFromTeam = useAssetStore((s) => s.unpublishFromTeam)
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const assetLibraryPref = useCanvasStore((s) => s.assetLibraryPref)
  const setAssetLibraryPref = useCanvasStore((s) => s.setAssetLibraryPref)

  const [scopeTab, setScopeTab] = useState("mine")
  const [contentTab, setContentTab] = useState("materials")
  const [filter, setFilter] = useState("all")
  const [canvasFilter, setCanvasFilter] = useState("all")
  const [newName, setNewName] = useState("")
  const [uploading, setUploading] = useState(false)
  const [toast, setToast] = useState(null)
  const [pickOpen, setPickOpen] = useState(false)
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef({ x: 0, y: 0, top: 0 })
  const panelRef = useRef(null)
  const fileRef = useRef(null)

  useEffect(() => {
    if (!open || !assetLibraryPref) return
    if (assetLibraryPref.contentTab) setContentTab(assetLibraryPref.contentTab)
    if (assetLibraryPref.filter) setFilter(assetLibraryPref.filter)
    if (assetLibraryPref.scopeTab) setScopeTab(assetLibraryPref.scopeTab)
    setAssetLibraryPref(null)
  }, [open, assetLibraryPref, setAssetLibraryPref])

  const canvasImages = useStore(
    useCallback((s) => {
      const items = []
      s.nodeInternals.forEach((node) => {
        if (node.type !== "image-gen" && node.type !== "video-gen") return
        if (node.type === "image-gen") {
          getImageNodeImages(node).forEach((ref) => {
            items.push({
              url: ref.imageUrl,
              label: ref.label,
              nodeId: ref.nodeId,
              type: "image-gen",
            })
          })
        } else if (node.data?.videoUrl) {
          items.push({
            url: node.data.videoUrl,
            label: node.data.prompt || t("canvas.asset.videoLabel"),
            nodeId: node.id,
            type: "video-gen",
          })
        }
      })
      return items
    }, [])
  )

  useEffect(() => {
    if (!open) return
    fetchAssets(true)
    if (activeTeamId) fetchTeamAssets(true, activeTeamId)
  }, [open, fetchAssets, fetchTeamAssets, activeTeamId])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  useEffect(() => {
    setFilter("all")
  }, [contentTab])

  const uploadKind = contentTab === "subjects" ? "character" : "image"
  const isTeamScope = scopeTab === "team"
  const activeList = isTeamScope ? teamAssets : assets
  const listLoading = isTeamScope ? teamLoading : loading

  const showToast = useCallback((msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2000)
  }, [])

  const canvasOptions = useMemo(() => {
    const map = new Map()
    for (const a of activeList) {
      if (!a.sourceCanvasId) continue
      map.set(a.sourceCanvasId, a.sourceCanvasName || a.sourceCanvasId)
    }
    map.set(canvasId, projectName || t("canvas.image.currentCanvas"))
    return [
      { id: "all", display_name: t("canvas.asset.allCanvases") },
      ...[...map.entries()].map(([id, name]) => ({
        id,
        display_name: name,
      })),
    ]
  }, [activeList, canvasId, projectName, t])

  const scopedAssets = useMemo(() => {
    return activeList.filter((a) =>
      contentTab === "subjects" ? isSubjectKind(a.kind) : isMaterialKind(a.kind)
    )
  }, [activeList, contentTab])

  const filtered = useMemo(() => {
    let list = scopedAssets
    if (filter !== "all") {
      list = list.filter((a) => normalizeAssetKind(a.kind) === filter)
    }
    if (contentTab === "subjects" && canvasFilter !== "all") {
      list = list.filter((a) => a.sourceCanvasId === canvasFilter)
    }
    return list
  }, [scopedAssets, filter, contentTab, canvasFilter])

  const counts = useMemo(() => {
    const list = isTeamScope ? teamAssets : assets
    const chars = list.filter((a) => normalizeAssetKind(a.kind) === "character").length
    const scenes = list.filter((a) => normalizeAssetKind(a.kind) === "scene").length
    const mats = list.filter((a) => isMaterialKind(a.kind)).length
    return { chars, scenes, mats }
  }, [assets, teamAssets, isTeamScope])

  const sourceMeta = useCallback(
    () => ({
      sourceCanvasId: canvasId,
      sourceCanvasName: projectName || t("canvas.image.currentCanvas"),
    }),
    [canvasId, projectName, t]
  )

  const handleUpload = useCallback(
    async (file) => {
      if (!file || !newName.trim()) return
      setUploading(true)
      try {
        await addAssetFromUpload({
          file,
          name: newName.trim(),
          kind: uploadKind,
          teamId: isTeamScope ? getActiveTeamId() : null,
          ...sourceMeta(),
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
    [newName, uploadKind, addAssetFromUpload, sourceMeta, showToast, isTeamScope, t]
  )

  const handlePickCanvas = useCallback(
    async (item) => {
      if (!item?.url) return
      const name =
        newName.trim()
        || item.label?.trim()
        || t("canvas.image.assetName", {
          time: new Date().toLocaleTimeString("zh", { hour: "2-digit", minute: "2-digit" }),
        })
      try {
        await addAssetFromUrl({
          name,
          kind: item.type === "video-gen" ? "video" : uploadKind,
          imageUrl: stripMediaTicket(item.url),
          teamId: isTeamScope ? getActiveTeamId() : null,
          ...sourceMeta(),
          sourceNodeId: item.nodeId,
        })
        setPickOpen(false)
        setNewName("")
        showToast(t("canvas.asset.addedFromCanvas"))
      } catch (err) {
        console.error(err)
        showToast(t("canvas.asset.addFail"))
      }
    },
    [newName, uploadKind, addAssetFromUrl, sourceMeta, showToast, isTeamScope, t]
  )

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

  const onDragStart = useCallback((e) => {
    if (e.button !== 0 || e.target.closest(".alf-no-drag")) return
    const panel = panelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    dragRef.current = { x: e.clientX, y: e.clientY, top: rect.top }
    setDragging(true)
    e.preventDefault()
  }, [])

  useEffect(() => {
    if (!dragging) return undefined
    const onMove = (e) => {
      const panel = panelRef.current
      if (!panel) return
      const dy = e.clientY - dragRef.current.y
      const h = panel.offsetHeight
      const top = Math.min(
        Math.max(48, dragRef.current.top + dy),
        window.innerHeight - h - 24
      )
      panel.style.top = `${top}px`
      panel.style.transform = "translateY(0)"
    }
    const onUp = () => setDragging(false)
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
    return () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
    }
  }, [dragging])

  if (!mounted) return null

  const filters = contentTab === "subjects" ? SUBJECT_FILTERS : MATERIAL_FILTERS

  return (
    <aside
      ref={panelRef}
      className={`alf-flyout nodrag nopan${open && !closing ? " alf-flyout--open" : ""}${closing ? " alf-flyout--closing" : ""}${dragging ? " alf-flyout--dragging" : ""}`}
      onPointerDown={sp}
      onDoubleClick={sp}
      role="dialog"
      aria-label={t("canvas.asset.libTitle")}
    >
      <header className="alf-head" onPointerDown={onDragStart}>
        <div className="alf-head-title">
          <span className="alf-grip">⋮⋮</span>
          <span className="alf-head-name">
            {scopeTab === "team" ? t("canvas.asset.teamLib") : t("canvas.asset.libTitle")}
          </span>
          <button
            type="button"
            className="alf-scope-switch alf-no-drag"
            title={scopeTab === "mine" ? t("canvas.asset.switchToTeam") : t("canvas.asset.switchToMine")}
            onClick={() => setScopeTab((s) => (s === "mine" ? "team" : "mine"))}
          >
            ⇄
          </button>
          <span className="alf-scope-hint">
            {scopeTab === "mine" ? t("canvas.asset.switchToTeam") : t("canvas.asset.switchToMine")}
          </span>
        </div>
        <button
          type="button"
          className="alf-close alf-no-drag"
          aria-label={t("canvas.common.close")}
          onClick={onClose}
        >
          ×
        </button>
      </header>

      <ScopeSwitchPanel switchKey={scopeTab} className="alf-scope-body">
      {scopeTab === "team" ? (
        <>
          <div className="alf-tabs alf-no-drag">
            <button
              type="button"
              className={`alf-tab${contentTab === "materials" ? " alf-tab--active" : ""}`}
              onClick={() => setContentTab("materials")}
            >
              {t("canvas.asset.materialsTab")}
              <span className="alf-tab-count">{counts.mats}</span>
            </button>
            <button
              type="button"
              className={`alf-tab${contentTab === "subjects" ? " alf-tab--active" : ""}`}
              onClick={() => setContentTab("subjects")}
            >
              {t("canvas.asset.subjectsTab")}
              <span className="alf-tab-count">{counts.chars + counts.scenes}</span>
            </button>
          </div>

          <div className="alf-filters alf-no-drag" role="tablist">
            {filters.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`alf-filter${filter === f.id ? " alf-filter--active" : ""}`}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="alf-grid alf-scroll-hide alf-no-drag">
            {listLoading && teamAssets.length === 0 && (
              <div className="alf-empty-inline">{t("canvas.common.loading")}</div>
            )}
            {error && <div className="alf-error">{error}</div>}
            {!listLoading && filtered.length === 0 && (
              <div className="alf-empty">
                <p className="alf-empty-title">
                  {contentTab === "subjects" ? t("canvas.asset.noTeamSubjects") : t("canvas.asset.noTeamMaterials")}
                </p>
                <p className="alf-empty-desc">
                  {t("canvas.asset.teamEmptyHint")}
                </p>
              </div>
            )}
            {filtered.map((asset) => {
              const isOwn = asset.ownerId === user?.id
              return (
                <div
                  key={asset.id}
                  className={`alf-card${asset.kind === "character" ? " alf-card--character" : asset.kind === "scene" ? " alf-card--scene" : ""}`}
                  title={t("canvas.history.dragHint")}
                  {...getCardPointerHandlers({
                    kind: "image",
                    mediaUrl: stripMediaTicket(asset.imageUrl),
                    name: asset.name,
                    prompt: asset.name,
                    previewUrl: asset.imageUrl,
                    source: "asset",
                  })}
                >
                  <button
                    type="button"
                    className="alf-card-main"
                    title={
                      contentTab === "subjects"
                        ? t("canvas.asset.clickCopy")
                        : asset.name
                    }
                    onClick={() => {
                      if (contentTab === "subjects") copyMention(asset.name)
                    }}
                  >
                    <img
                      src={ensureMediaUrl(asset.imageUrl)}
                      alt=""
                      className="alf-thumb"
                      draggable={false}
                    />
                    <span className="alf-name">{asset.name}</span>
                    <span className="alf-kind">
                      {ASSET_KIND_LABELS[asset.kind] || t("canvas.asset.other")}
                    </span>
                    {asset.ownerName && (
                      <span className="alf-source">{asset.ownerName}</span>
                    )}
                    {asset.sourceCanvasName && (
                      <span className="alf-source">{asset.sourceCanvasName}</span>
                    )}
                  </button>
                  {isOwn && (
                    <button
                      type="button"
                      className="alf-del"
                      title={t("canvas.asset.removeFromTeam")}
                      onClick={async () => {
                        if (!window.confirm(t("canvas.asset.removeFromTeamConfirm", { name: asset.name }))) return
                        try {
                          await unpublishFromTeam(asset.id)
                          showToast(t("canvas.asset.removedFromTeam"))
                        } catch {
                          showToast(t("canvas.asset.opFail"))
                        }
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
              )
            })}
          </div>

          <footer className="alf-foot alf-no-drag">
            <input
              className="alf-input"
              placeholder={
                contentTab === "subjects" ? t("canvas.asset.teamSubjectPh") : t("canvas.asset.teamMaterialPh")
              }
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <div className="alf-foot-actions">
              <button
                type="button"
                className="alf-btn alf-btn--ghost"
                onClick={() => setPickOpen((v) => !v)}
              >
                {t("canvas.asset.pickFromCanvas")}
              </button>
              <button
                type="button"
                className="alf-btn alf-btn--primary"
                disabled={uploading || !newName.trim()}
                onClick={() => fileRef.current?.click()}
              >
                {uploading ? t("canvas.upload.uploading") : t("canvas.asset.uploadToTeam")}
              </button>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="alf-file"
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ""
                if (f) handleUpload(f)
              }}
            />
          </footer>

          {pickOpen && (
            <div className="alf-pick-panel alf-no-drag">
              <div className="alf-pick-head">{t("canvas.asset.pickHead")}</div>
              {canvasImages.length === 0 ? (
                <p className="alf-pick-empty">{t("canvas.asset.pickEmpty")}</p>
              ) : (
                <div className="alf-pick-grid">
                  {canvasImages.map((item, i) => (
                    <button
                      key={`${item.nodeId}-${i}`}
                      type="button"
                      className="alf-pick-item"
                      onClick={() => handlePickCanvas(item)}
                    >
                      <img src={ensureMediaUrl(item.url)} alt="" draggable={false} />
                      <span>{item.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <>
          <div className="alf-tabs alf-no-drag">
            <button
              type="button"
              className={`alf-tab${contentTab === "materials" ? " alf-tab--active" : ""}`}
              onClick={() => setContentTab("materials")}
            >
              {t("canvas.asset.materialsTab")}
              <span className="alf-tab-count">{counts.mats}</span>
            </button>
            <button
              type="button"
              className={`alf-tab${contentTab === "subjects" ? " alf-tab--active" : ""}`}
              onClick={() => setContentTab("subjects")}
            >
              {t("canvas.asset.subjectsTab")}
              <span className="alf-tab-count">{counts.chars + counts.scenes}</span>
            </button>
          </div>

          {contentTab === "subjects" && canvasOptions.length > 2 && (
            <div className="alf-canvas-filter alf-no-drag">
              <span className="alf-filter-label">{t("canvas.asset.sourceCanvas")}</span>
              <div className="alf-filters alf-filters--scroll">
                {canvasOptions.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={`alf-filter${canvasFilter === opt.id ? " alf-filter--active" : ""}`}
                    onClick={() => setCanvasFilter(opt.id)}
                  >
                    {opt.display_name}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="alf-filters alf-no-drag" role="tablist">
            {filters.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`alf-filter${filter === f.id ? " alf-filter--active" : ""}`}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="alf-grid alf-scroll-hide alf-no-drag">
            {loading && assets.length === 0 && (
              <div className="alf-empty-inline">{t("canvas.common.loading")}</div>
            )}
            {error && <div className="alf-error">{error}</div>}
            {!loading && filtered.length === 0 && (
              <div className="alf-empty">
                <p className="alf-empty-title">
                  {contentTab === "subjects" ? t("canvas.asset.noSubjects") : t("canvas.asset.noMaterials")}
                </p>
                <p className="alf-empty-desc">
                  {contentTab === "subjects"
                    ? t("canvas.asset.subjectsEmptyHint")
                    : t("canvas.asset.materialsEmptyHint")}
                </p>
              </div>
            )}
            {filtered.map((asset) => (
              <div
                key={asset.id}
                className={`alf-card${asset.kind === "character" ? " alf-card--character" : asset.kind === "scene" ? " alf-card--scene" : ""}`}
                title={t("canvas.history.dragHint")}
                {...getCardPointerHandlers({
                  kind: "image",
                  mediaUrl: stripMediaTicket(asset.imageUrl),
                  name: asset.name,
                  prompt: asset.name,
                  previewUrl: asset.imageUrl,
                  source: "asset",
                })}
              >
                <button
                  type="button"
                  className="alf-card-main"
                  title={
                    contentTab === "subjects"
                      ? t("canvas.asset.clickCopy")
                      : asset.name
                  }
                  onClick={() => {
                    if (contentTab === "subjects") copyMention(asset.name)
                  }}
                >
                  <img
                    src={ensureMediaUrl(asset.imageUrl)}
                    alt=""
                    className="alf-thumb"
                    draggable={false}
                  />
                  <span className="alf-name">{asset.name}</span>
                  <span className="alf-kind">
                    {ASSET_KIND_LABELS[asset.kind] || t("canvas.asset.other")}
                  </span>
                  {asset.sourceCanvasName && (
                    <span className="alf-source">{asset.sourceCanvasName}</span>
                  )}
                </button>
                <div className="alf-card-actions alf-no-drag">
                  {!asset.teamId && activeTeamId && (
                    <button
                      type="button"
                      className="alf-share-team"
                      title={t("canvas.asset.shareToTeam")}
                      onClick={async () => {
                        try {
                          await publishToTeam(asset.id, activeTeamId)
                          showToast(t("canvas.asset.sharedToTeam"))
                        } catch {
                          showToast(t("canvas.asset.shareFail"))
                        }
                      }}
                    >
                      ⇄
                    </button>
                  )}
                  <button
                    type="button"
                    className="alf-del"
                    title={t("canvas.common.delete")}
                    onClick={async () => {
                      if (!window.confirm(t("canvas.asset.deleteNamedConfirm", { name: asset.name }))) return
                      try {
                        await removeAsset(asset.id)
                        showToast(t("canvas.asset.deleted"))
                      } catch {
                        showToast(t("canvas.asset.deleteFail"))
                      }
                    }}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>

          <footer className="alf-foot alf-no-drag">
            <input
              className="alf-input"
              placeholder={
                contentTab === "subjects" ? t("canvas.asset.subjectPh") : t("canvas.asset.materialPh")
              }
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <div className="alf-foot-actions">
              <button
                type="button"
                className="alf-btn alf-btn--ghost"
                onClick={() => setPickOpen((v) => !v)}
              >
                {t("canvas.asset.pickFromCanvas")}
              </button>
              <button
                type="button"
                className="alf-btn alf-btn--primary"
                disabled={uploading || !newName.trim()}
                onClick={() => fileRef.current?.click()}
              >
                {uploading ? t("canvas.upload.uploading") : t("canvas.asset.uploadImage")}
              </button>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="alf-file"
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ""
                if (f) handleUpload(f)
              }}
            />
          </footer>

          {pickOpen && (
            <div className="alf-pick-panel alf-no-drag">
              <div className="alf-pick-head">{t("canvas.asset.pickHead")}</div>
              {canvasImages.length === 0 ? (
                <p className="alf-pick-empty">{t("canvas.asset.pickEmpty")}</p>
              ) : (
                <div className="alf-pick-grid">
                  {canvasImages.map((item, i) => (
                    <button
                      key={`${item.nodeId}-${i}`}
                      type="button"
                      className="alf-pick-item"
                      onClick={() => handlePickCanvas(item)}
                    >
                      <img src={ensureMediaUrl(item.url)} alt="" draggable={false} />
                      <span>{item.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
      </ScopeSwitchPanel>

      {toast && <div className="alf-toast">{toast}</div>}
    </aside>
  )
}
