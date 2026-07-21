import { useCallback, useEffect, useRef, useState } from "react"
import { useReactFlow } from "reactflow"
import { useAssetStore } from "../../stores/assetStore"
import { createUserAsset, updateUserAsset, uploadUserAsset } from "../../services/assetsApi"
import { slugIdentityId } from "../../utils/canvas/castLibrary"
import { syncCastLibraryOnScriptTables } from "../../utils/canvas/castLibrarySync"
import { useLocale } from "../../utils/locale"
import NodeCardDotsMenu from "./NodeCardDotsMenu"
import TextWorkflowEdgePlugs from "./TextWorkflowEdgePlugs"
import { useCanvasNodeWheel } from "./canvasScrollHelpers"
import "./CanvasShared.css"
import "./canvasNodeLayout.css"
import "./canvasTypography.css"
import "./CharacterCardNode.css"

export default function CharacterCardNode({ id, data, selected }) {
  const { t } = useLocale()
  const readOnly = data.readOnly === true
  const { setNodes } = useReactFlow()
  const loadAssets = useAssetStore((s) => s.loadAssets)
  const [name, setName] = useState(data.name || "")
  const [appearance, setAppearance] = useState(data.appearance || "")
  const [images, setImages] = useState(() => (Array.isArray(data.referenceImages) ? data.referenceImages : []))
  const [saving, setSaving] = useState(false)
  const wrapperRef = useRef(null)
  useCanvasNodeWheel(wrapperRef)

  const patchData = useCallback(
    (patch) => {
      setNodes((ns) =>
        ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))
      )
    },
    [id, setNodes]
  )

  useEffect(() => {
    setName(data.name || "")
    setAppearance(data.appearance || "")
    setImages(Array.isArray(data.referenceImages) ? data.referenceImages : [])
  }, [data.name, data.appearance, data.referenceImages])

  const persistAsset = useCallback(async () => {
    if (readOnly) return
    const trimmedName = name.trim()
    if (!trimmedName) return
    setSaving(true)
    try {
      const teamId = getCanvasTeamId()
      const payload = {
        name: trimmedName,
        kind: "character",
        note: appearance.trim(),
        image_url: images[0] || "",
        team_id: teamId || undefined,
      }
      let assetId = data.assetId
      if (assetId) {
        await updateUserAsset(assetId, payload)
      } else {
        const created = await createUserAsset({
          ...payload,
          source_node_id: id,
        })
        assetId = created.id
        patchData({ assetId })
      }
      patchData({
        name: trimmedName,
        appearance: appearance.trim(),
        referenceImages: images,
        faceUrl: images[0] || null,
        identityId: data.identityId || slugIdentityId(trimmedName),
        assetId,
      })
      syncCastLibraryOnScriptTables(setNodes, {
        name: trimmedName,
        appearance: appearance.trim(),
        referenceImages: images,
        faceUrl: images[0] || null,
        identityId: data.identityId || slugIdentityId(trimmedName),
        assetId,
        globalAssetId: data.globalAssetId,
      })
      await loadAssets({ teamId })
    } finally {
      setSaving(false)
    }
  }, [appearance, data.assetId, data.globalAssetId, data.identityId, id, images, loadAssets, name, patchData, readOnly, setNodes])

  const onUpload = useCallback(
    async (e) => {
      const file = e.target.files?.[0]
      if (!file || readOnly) return
      const teamId = getCanvasTeamId()
      const uploaded = await uploadUserAsset({
        file,
        name: name.trim() || file.name,
        kind: "character",
        note: appearance.trim(),
        source_node_id: id,
        team_id: teamId || undefined,
      })
      const url = uploaded.image_url || ""
      const next = url ? [...images.filter(Boolean), url].slice(0, 4) : images
      setImages(next)
      patchData({ referenceImages: next, faceUrl: url || null, assetId: uploaded.id || data.assetId })
      syncCastLibraryOnScriptTables(setNodes, {
        name: name.trim() || uploaded.name,
        appearance: appearance.trim(),
        referenceImages: next,
        faceUrl: url || null,
        identityId: data.identityId || slugIdentityId(name.trim() || uploaded.name),
        assetId: uploaded.id || data.assetId,
        globalAssetId: data.globalAssetId,
      })
      await loadAssets({ teamId })
      e.target.value = ""
    },
    [appearance, data.assetId, data.globalAssetId, data.identityId, id, images, loadAssets, name, patchData, readOnly, setNodes]
  )

  return (
    <div ref={wrapperRef} className={`ccn-root canvas-node-card${selected ? " selected" : ""}`}>
      <TextWorkflowEdgePlugs nodeId={id} nodeType="character-card" disabled={readOnly} selected={selected} />
      <div className="ccn-header">
        <span className="ccn-title">{t("canvas.characterCard.title")}</span>
        <NodeCardDotsMenu nodeId={id} readOnly={readOnly} />
      </div>
      <label className="ccn-label">{t("canvas.characterCard.name")}</label>
      <input
        className="ccn-input"
        value={name}
        disabled={readOnly}
        onChange={(e) => setName(e.target.value)}
        onBlur={persistAsset}
        placeholder={t("canvas.characterCard.namePh")}
      />
      <label className="ccn-label">{t("canvas.characterCard.appearance")}</label>
      <textarea
        className="ccn-textarea"
        value={appearance}
        disabled={readOnly}
        onChange={(e) => setAppearance(e.target.value)}
        onBlur={persistAsset}
        rows={3}
        placeholder={t("canvas.characterCard.appearancePh")}
      />
      <div className="ccn-images">
        {images.map((url) => (
          <img key={url} src={url} alt="" className="ccn-thumb" />
        ))}
        {!readOnly && (
          <label className="ccn-upload">
            +
            <input type="file" accept="image/*" hidden onChange={onUpload} />
          </label>
        )}
      </div>
      {saving && <div className="ccn-saving">{t("canvas.characterCard.saving")}</div>}
    </div>
  )
}
