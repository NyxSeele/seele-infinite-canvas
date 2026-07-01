import { useState, useCallback, useRef } from "react"
import { Handle, Position } from "reactflow"
import { uploadImageFile } from "../../services/uploadImage"
import { ensureMediaUrl } from "../../utils/mediaTicket"
import { useLocale } from "../../utils/locale"
import { LineIcon } from "../icons/LineIcons"
import { useCanvasNodeWheel } from "./canvasScrollHelpers"
import "./CanvasShared.css"
import "./ImageUploadNode.css"

export default function ImageUploadNode({ id, data, selected }) {
  const { t } = useLocale()
  const [imageUrl, setImageUrl] = useState(data.imageUrl || null)
  const [filename, setFilename] = useState(data.filename || null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef(null)
  const wrapperRef = useRef(null)
  useCanvasNodeWheel(wrapperRef)

  const uploadFile = useCallback(
    async (file) => {
      if (!file || !file.type.startsWith("image/")) return
      setUploading(true)
      try {
        const url = await uploadImageFile(file)
        const fname = file.name
        setImageUrl(url)
        setFilename(fname)
        if (data.onUpdate) data.onUpdate(id, { imageUrl: url, filename: fname })
      } catch (err) {
        console.error("图片上传失败", err)
      } finally {
        setUploading(false)
      }
    },
    [id, data]
  )

  const handleFileChange = useCallback(
    (e) => {
      const file = e.target.files?.[0]
      if (file) uploadFile(file)
    },
    [uploadFile]
  )

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault()
      e.stopPropagation()
      setDragging(false)
      const file = e.dataTransfer.files?.[0]
      if (file) uploadFile(file)
    },
    [uploadFile]
  )

  const handleClear = useCallback(() => {
    setImageUrl(null)
    setFilename(null)
    if (data.onUpdate) data.onUpdate(id, { imageUrl: null, filename: null })
  }, [id, data])

  const handleDelete = useCallback(() => {
    if (data.onDelete) data.onDelete(id)
  }, [id, data])

  return (
    <div className="iu-wrapper" ref={wrapperRef}>
      {/* 标签行 */}
      <div className="gn2-label-row">
        <span className="gn2-label-text">{t("canvas.upload.title")}</span>
        <button type="button" className="iu-close-btn nodrag" onClick={handleDelete} aria-label={t("canvas.common.delete")}>×</button>
      </div>

      <div className={`iu-card${selected ? " iu-card--selected" : ""}`}>
        <Handle type="target" position={Position.Left} className="node-handle" />
        <Handle type="source" position={Position.Right} className="node-handle" />

        {!imageUrl ? (
          <div
            className={`iu-drop-zone nodrag nowheel${dragging ? " iu-drop-zone--dragging" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
          >
            <input ref={fileInputRef} type="file" accept="image/*" hidden onChange={handleFileChange} />
            {uploading ? (
              <div className="iu-uploading"><span className="upload-spinner" />{t("canvas.upload.uploading")}</div>
            ) : (
              <>
                <div className="iu-upload-icon"><LineIcon name="image" size={28} /></div>
                <div className="iu-upload-hint">{t("canvas.upload.clickOrDrop")}</div>
                <div className="iu-upload-sub">{t("canvas.upload.formats")}</div>
              </>
            )}
          </div>
        ) : (
          <>
            {/* 预览区：与 image-gen 完全一致 */}
            <div className="gn2-preview iu-preview nodrag" onClick={() => window.open(imageUrl, "_blank")}>
              <img className="gn2-result-img" src={ensureMediaUrl(imageUrl)} alt="Uploaded" />
              {filename && <span className="iu-filename">{filename}</span>}
            </div>
            {/* 重新上传 */}
            <button type="button" className="iu-reupload-btn nodrag"
              onClick={() => fileInputRef.current?.click()}>
              {t("canvas.upload.reupload")}
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" hidden onChange={handleFileChange} />
          </>
        )}
      </div>
    </div>
  )
}
