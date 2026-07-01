import { useCallback, useEffect, useMemo, useRef } from "react"
import { useStore } from "reactflow"
import { useCanvasStore } from "../../stores"
import { useLocale } from "../../utils/locale"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { getImageNodeImages } from "./videoReferenceHelpers"
import "./CanvasImageQuickPicker.css"

const sp = (e) => e.stopPropagation()

/**
 * 画布 image-gen 节点图片快捷选择栏
 * @param {object} props
 * @param {(item: { url, label, nodeId, imageIndex, imageId }) => void} props.onSelect
 * @param {() => void} props.onBrowseCanvas
 * @param {(file: File) => void} [props.onUpload]
 * @param {boolean} [props.showUpload]
 * @param {string} [props.excludeNodeId] 排除的节点（如正在为该节点选参考图）
 */
export default function CanvasImageQuickPicker({
  onSelect,
  onBrowseCanvas,
  onUpload,
  showUpload = true,
  excludeNodeId = null,
  assetEntries = [],
  onAssetPick,
}) {
  const { t } = useLocale()
  const theme = useCanvasStore((s) => s.theme)
  const imageItems = useStore(
    useCallback(
      (s) => {
        const items = []
        s.nodeInternals.forEach((node) => {
          if (node.type !== "image-gen") return
          if (excludeNodeId && node.id === excludeNodeId) return
          getImageNodeImages(node).forEach((ref) => {
            items.push({
              url: ref.imageUrl,
              label: ref.label,
              nodeId: ref.nodeId,
              imageIndex: ref.imageIndex,
              imageId: ref.imageId,
            })
          })
        })
        return items
      },
      [excludeNodeId]
    )
  )

  const list = useMemo(() => imageItems, [imageItems])
  const assets = useMemo(() => assetEntries || [], [assetEntries])
  const rowRef = useRef(null)
  const assetsRef = useRef(null)
  const fileInputRef = useRef(null)

  const handleUploadClick = useCallback(
    (e) => {
      sp(e)
      fileInputRef.current?.click()
    },
    []
  )

  const handleFileChange = useCallback(
    (e) => {
      const file = e.target.files?.[0]
      e.target.value = ""
      if (file) onUpload?.(file)
    },
    [onUpload]
  )

  useEffect(() => {
    const el = rowRef.current
    if (!el) return undefined
    const onWheel = (e) => {
      e.preventDefault()
      el.scrollLeft += e.deltaY
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [list.length])

  return (
    <div className={`quick-picker rf-page rf-page--${theme} nodrag nopan`} onPointerDown={sp} onClick={sp}>
      <div className="quick-picker-actions">
        {showUpload && onUpload && (
          <>
            <button
              type="button"
              className="nodrag nopan"
              onPointerDown={sp}
              onClick={handleUploadClick}
            >
              {t("canvas.prompt.uploadImage")}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="quick-picker-file-input"
              onChange={handleFileChange}
            />
          </>
        )}
        <button
          type="button"
          className="nodrag nopan"
          onPointerDown={sp}
          onClick={(e) => {
            sp(e)
            onBrowseCanvas?.()
          }}
        >
          {t("canvas.ref.browseCanvas")}
        </button>
      </div>
      {list.length > 0 && (
        <div className="quick-picker-row" ref={rowRef}>
          {list.map((item) => (
            <div
              key={item.imageId || `${item.nodeId}_${item.imageIndex}`}
              className="quick-picker-item nodrag nopan"
              role="button"
              tabIndex={0}
              title={item.label}
              onClick={(e) => {
                sp(e)
                onSelect?.(item)
              }}
            >
              <img
                src={item.url}
                alt=""
                draggable={false}
                onDragStart={(e) => e.preventDefault()}
                style={{ pointerEvents: "none" }}
              />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      )}
      {assets.length > 0 && onAssetPick && (
        <div className="quick-picker-assets">
          <div className="quick-picker-assets-title">
            {t("canvas.script.fromAssetsCount", { n: assets.length })}
          </div>
          <div className="quick-picker-assets-row" ref={assetsRef}>
            {assets.map((asset) => (
              <button
                key={asset.id}
                type="button"
                className="quick-picker-asset-item nodrag nopan"
                onPointerDown={sp}
                onClick={(e) => {
                  sp(e)
                  onAssetPick(asset)
                }}
              >
                <img src={ensureMediaUrl(asset.imageUrl)} alt="" draggable={false} />
                <span>{asset.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      {onAssetPick && assets.length === 0 && (
        <p className="quick-picker-assets-empty">{t("canvas.asset.empty")}</p>
      )}
    </div>
  )
}
