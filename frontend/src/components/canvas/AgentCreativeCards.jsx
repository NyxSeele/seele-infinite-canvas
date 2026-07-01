/** TapNow 式创意选项：全展开卡片列表，点击整张卡片即选择（配合 ask_user.options） */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

function formatFocus(focus) {
  const text = (focus || "").trim()
  if (!text) return ""
  if (/^(侧重|优势|基调|风险)[：:]/u.test(text)) return text
  return `侧重：${text}`
}

function CastPickPopover({ anchorEl, open, onClose, children }) {
  const popRef = useRef(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })

  useLayoutEffect(() => {
    if (!open || !anchorEl) return undefined

    const update = () => {
      const rect = anchorEl.getBoundingClientRect()
      const popW = 168
      let left = rect.left
      if (left + popW > window.innerWidth - 8) {
        left = window.innerWidth - popW - 8
      }
      setPos({ top: rect.bottom + 6, left: Math.max(8, left) })
    }

    const scrollParents = []
    let el = anchorEl.parentElement
    while (el) {
      const { overflowY } = window.getComputedStyle(el)
      if (overflowY === "auto" || overflowY === "scroll") {
        scrollParents.push(el)
      }
      el = el.parentElement
    }

    update()
    window.addEventListener("scroll", update, true)
    window.addEventListener("resize", update)
    scrollParents.forEach((node) => node.addEventListener("scroll", update, { passive: true }))
    return () => {
      window.removeEventListener("scroll", update, true)
      window.removeEventListener("resize", update)
      scrollParents.forEach((node) => node.removeEventListener("scroll", update))
    }
  }, [open, anchorEl])

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => {
      if (
        popRef.current?.contains(e.target)
        || anchorEl?.contains(e.target)
      ) return
      onClose?.()
    }
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [open, onClose, anchorEl])

  if (!open) return null

  return createPortal(
    <div
      ref={popRef}
      className="ap-cast-pick-popover"
      style={{ top: pos.top, left: pos.left }}
      role="menu"
    >
      {children}
    </div>,
    document.body
  )
}

function EntityKindIcon({ kind }) {
  if (kind === "scene") {
    return (
      <span className="ap-entity-kind-icon ap-entity-kind-icon--scene" aria-hidden>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M6 1L10.5 4.5V10.5H1.5V4.5L6 1Z" stroke="currentColor" strokeWidth="1.1" />
          <path d="M4.5 10.5V7H7.5V10.5" stroke="currentColor" strokeWidth="1.1" />
        </svg>
      </span>
    )
  }
  return (
    <span className="ap-entity-kind-icon ap-entity-kind-icon--character" aria-hidden>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <circle cx="6" cy="3.5" r="2" stroke="currentColor" strokeWidth="1.1" />
        <path d="M2.5 10.5c0-2.2 1.6-3.5 3.5-3.5s3.5 1.3 3.5 3.5" stroke="currentColor" strokeWidth="1.1" />
      </svg>
    </span>
  )
}

function EntityPendingCard({
  entityKind = "character",
  pendingList = [],
  scriptTableId = "",
  getImportableAssets,
  teamLibraryEnabled = false,
  onAssignFromCanvas,
  onAssignFromUpload,
  onAssignFromAsset,
  disabled = false,
}) {
  const isScene = entityKind === "scene"
  const idKey = isScene ? "sceneId" : "castId"
  const pendingPrefix = isScene ? "scene-pending" : "cast-pending"
  const typeLabelDefault = isScene ? "场景" : "角色"
  const title = isScene ? "以下场景还没有参考图" : "以下角色还没有参考图"
  const sub = isScene
    ? "建议从画布选取或上传场景参考图，可保持多镜空间一致性"
    : "建议从画布选取或上传参考图，可提升后续分镜的视觉一致性"
  const saveLabel = isScene
    ? "保存为常用场景，下次项目可复用"
    : "保存为常用角色，下次项目可复用"
  const emptyAssets = isScene
    ? "团队资产库暂无可导入的场景"
    : "团队资产库暂无可导入的角色"
  const ariaLabel = isScene ? "待配图场景" : "待配图角色"

  const [openMenuId, setOpenMenuId] = useState(null)
  const [assetPickerId, setAssetPickerId] = useState(null)
  const [saveToTeam, setSaveToTeam] = useState(false)
  const fileInputRef = useRef(null)
  const pendingUploadRef = useRef(null)
  const pickBtnRefs = useRef({})

  const resetPickState = useCallback(() => {
    setOpenMenuId(null)
    setAssetPickerId(null)
    setSaveToTeam(false)
  }, [])

  const handleFileChange = useCallback(
    async (e) => {
      const file = e.target.files?.[0]
      const pending = pendingUploadRef.current
      e.target.value = ""
      pendingUploadRef.current = null
      if (!file || !pending) return
      await onAssignFromUpload?.({ ...pending, file, saveToTeam })
      resetPickState()
    },
    [onAssignFromUpload, resetPickState, saveToTeam]
  )

  if (!Array.isArray(pendingList) || pendingList.length === 0) return null

  const openItem = pendingList.find((item, i) => {
    const id = item?.id || `${pendingPrefix}-${i}`
    return openMenuId === id || assetPickerId === id
  })
  const openIndex = pendingList.findIndex((item, i) => {
    const id = item?.id || `${pendingPrefix}-${i}`
    return openMenuId === id || assetPickerId === id
  })
  const openId = openItem ? (openItem?.id || `${pendingPrefix}-${openIndex}`) : null
  const openName = openItem?.name || (typeof openItem === "string" ? openItem : "")
  const openType = isScene ? "scene" : "character"
  const openDescription = openItem?.description || ""
  const importableAssets = openItem && getImportableAssets
    ? getImportableAssets(openItem)
    : []

  const makeAssignPayload = (extra = {}) => ({
    [idKey]: openId,
    castId: openId,
    sceneId: openId,
    name: openName,
    type: openType,
    description: openDescription,
    scriptTableId,
    ...extra,
  })

  return (
    <div
      className={`ap-cast-pending ap-entity-pending ap-entity-pending--${entityKind}`}
      role="group"
      aria-label={ariaLabel}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="ap-cast-pending__file"
        onChange={handleFileChange}
      />
      <div className="ap-cast-pending__title">{title}</div>
      <div className="ap-cast-pending__sub">{sub}</div>
      <ul className="ap-cast-pending__list">
        {pendingList.map((item, i) => {
          const name = item?.name || (typeof item === "string" ? item : "")
          const id = item?.id || `${pendingPrefix}-${i}`
          const typeLabel = item?.type === "scene" || isScene ? "场景" : "角色"
          if (!name) return null
          const menuOpen = openMenuId === id
          return (
            <li key={id} className="ap-cast-pending__item ap-entity-card">
              <div className="ap-cast-pending__meta">
                <EntityKindIcon kind={isScene ? "scene" : "character"} />
                <span className="ap-cast-pending__type">{typeLabelDefault}</span>
                <span className="ap-cast-pending__name">{name}</span>
                <span className="ap-cast-pending__badge">待配图</span>
              </div>
              {scriptTableId ? (
                <div className="ap-cast-pending__actions">
                  <button
                    ref={(el) => { pickBtnRefs.current[id] = el }}
                    type="button"
                    className="ap-cast-pick-btn"
                    disabled={disabled}
                    aria-expanded={menuOpen}
                    onClick={() => {
                      setAssetPickerId(null)
                      setSaveToTeam(false)
                      setOpenMenuId((cur) => (cur === id ? null : id))
                    }}
                  >
                    为 TA 选图
                  </button>
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>

      {openId && openMenuId === openId ? (
        <CastPickPopover
          anchorEl={pickBtnRefs.current[openId]}
          open
          onClose={() => setOpenMenuId(null)}
        >
          <button
            type="button"
            className="ap-cast-pick-popover__item"
            disabled={disabled}
            onClick={() => {
              onAssignFromCanvas?.(makeAssignPayload({
                saveToTeam: teamLibraryEnabled && saveToTeam,
              }))
              resetPickState()
            }}
          >
            从画布选择
          </button>
          <button
            type="button"
            className="ap-cast-pick-popover__item"
            disabled={disabled}
            onClick={() => {
              pendingUploadRef.current = makeAssignPayload()
              fileInputRef.current?.click()
            }}
          >
            本地上传
          </button>
          <button
            type="button"
            className="ap-cast-pick-popover__item"
            disabled={disabled}
            onClick={() => {
              setOpenMenuId(null)
              setAssetPickerId(openId)
            }}
          >
            从资产库选择
          </button>
          {teamLibraryEnabled ? (
            <label className="ap-cast-pick-popover__save">
              <input
                type="checkbox"
                checked={saveToTeam}
                disabled={disabled}
                onChange={(e) => setSaveToTeam(e.target.checked)}
              />
              <span>{saveLabel}</span>
            </label>
          ) : null}
        </CastPickPopover>
      ) : null}

      {openId && assetPickerId === openId ? (
        <CastPickPopover
          anchorEl={pickBtnRefs.current[openId]}
          open
          onClose={() => setAssetPickerId(null)}
        >
          {importableAssets.length === 0 ? (
            <p className="ap-cast-pick-popover__empty">{emptyAssets}</p>
          ) : (
            importableAssets.map((asset) => (
              <button
                key={asset.id}
                type="button"
                className="ap-cast-pick-popover__asset"
                disabled={disabled}
                onClick={() => {
                  onAssignFromAsset?.(makeAssignPayload({ asset }))
                  resetPickState()
                }}
              >
                {asset.imageUrl ? (
                  <span className="ap-cast-pick-popover__asset-thumb">
                    <EntityKindIcon kind={asset.kind === "scene" ? "scene" : "character"} />
                    <img src={asset.imageUrl} alt="" draggable={false} />
                  </span>
                ) : null}
                <span>{asset.name}</span>
              </button>
            ))
          )}
        </CastPickPopover>
      ) : null}
    </div>
  )
}

/** 待配图角色（manage_cast / cast_pending） */
export function CastPendingCard(props) {
  return (
    <EntityPendingCard
      entityKind="character"
      pendingList={props.castPending}
      {...props}
    />
  )
}

/** 待配图场景（manage_scene / scene_pending） */
export function ScenePendingCard(props) {
  return (
    <EntityPendingCard
      entityKind="scene"
      pendingList={props.scenePending}
      {...props}
    />
  )
}

export default function AgentCreativeCards({
  options,
  groupTitle = "",
  groupSubtitle = "",
  onSelect,
  disabled = false,
}) {
  if (!Array.isArray(options) || options.length === 0) return null

  return (
    <div className="ap-creative-cards" role="group" aria-label="创意选项">
      {groupTitle ? (
        <div className="ap-creative-group-title">{groupTitle}</div>
      ) : null}
      {groupSubtitle ? (
        <div className="ap-creative-group-sub">{groupSubtitle}</div>
      ) : null}
      <div className="ap-creative-cards__list">
        {options.map((opt, i) => {
          const title = opt?.title || opt?.label || `方案 ${i + 1}`
          const tag = opt?.tag || ""
          const description = opt?.description || opt?.subtitle || ""
          const focus = formatFocus(opt?.focus)
          return (
            <button
              key={opt?.id || `opt-${i}`}
              type="button"
              className="ap-creative-card"
              disabled={disabled}
              onClick={() => onSelect?.(opt)}
            >
              <div className="ap-creative-card__header">
                <span className="ap-creative-card__title">{title}</span>
                {tag ? <span className="ap-creative-card__tag">{tag}</span> : null}
              </div>
              {(description || focus) && (
                <div className="ap-creative-card__body">
                  {description ? (
                    <p className="ap-creative-card__desc">{description}</p>
                  ) : null}
                  {focus ? (
                    <p className="ap-creative-card__focus">{focus}</p>
                  ) : null}
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
