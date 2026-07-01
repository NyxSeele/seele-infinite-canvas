import { Image as ImageIcon } from "lucide-react"
import AddRefHoverPanel from "./AddRefHoverPanel"

/**
 * 画布 Prompt Bar 顶栏「添加参考图」统一触发器（click + ImageIcon + 可选计数）
 */
export default function RefPickerTrigger({
  label,
  labelWithCount,
  count = 0,
  max,
  disabled = false,
  showUpload = true,
  excludeNodeId = null,
  onQuickSelect,
  onCanvasPick,
  onUpload,
  assetEntries = [],
  onAssetPick,
}) {
  const text =
    labelWithCount && max != null
      ? labelWithCount.replace("{count}", String(count)).replace("{max}", String(max))
      : label

  return (
    <AddRefHoverPanel
      buttonClassName="add-ref-btn nodrag nopan"
      trigger="click"
      showUpload={showUpload}
      disabled={disabled}
      buttonContent={
        <>
          <ImageIcon size={14} />
          {text}
        </>
      }
      excludeNodeId={excludeNodeId}
      assetEntries={assetEntries}
      onAssetPick={onAssetPick}
      onQuickSelect={onQuickSelect}
      onCanvasPick={onCanvasPick}
      onUpload={onUpload}
    />
  )
}
