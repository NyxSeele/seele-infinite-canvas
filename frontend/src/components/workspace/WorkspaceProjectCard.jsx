import { useCallback, useEffect, useRef, useState } from "react"
import { ProjectThumb, formatProjectDate } from "./workspaceProjectUtils"
import { useLocale } from "../../utils/locale"
import { useTeamStore } from "../../stores"
import MigrateToTeamModal, { getMigratableTeams } from "./MigrateToTeamModal"
import AnimatedModal from "../common/AnimatedModal"

const sp = (e) => e.stopPropagation()

function ConfirmModal({ title, body, confirmLabel, onConfirm, onClose, danger }) {
  const [loading, setLoading] = useState(false)

  const handleConfirm = async () => {
    setLoading(true)
    try {
      await onConfirm()
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatedModal open onClose={onClose}>
        <div className="ws-modal-title">{title}</div>
        <p className="ws-modal-body">{body}</p>
        <div className="ws-modal-footer">
          <button type="button" className="ws-btn-ghost" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className={`ws-btn-primary${danger ? " ws-btn-danger" : ""}`}
            onClick={handleConfirm}
            disabled={loading}
          >
            {loading ? "处理中…" : confirmLabel}
          </button>
        </div>
    </AnimatedModal>
  )
}

export default function WorkspaceProjectCard({
  project,
  onOpen,
  onRename,
  onDelete,
  onMigrateToTeam,
  variant = "grid",
}) {
  const { t } = useLocale()
  const allTeams = useTeamStore((s) => s.allTeams)
  const ensureTeamsLoaded = useTeamStore((s) => s.ensureTeamsLoaded)
  const menuRef = useRef(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState(project.name)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [migrateOpen, setMigrateOpen] = useState(false)
  const renameInputRef = useRef(null)

  const migratableTeams = getMigratableTeams(allTeams)
  const canMigrate = !project.team_id && migratableTeams.length > 0 && onMigrateToTeam

  useEffect(() => {
    if (canMigrate) ensureTeamsLoaded()
  }, [canMigrate, ensureTeamsLoaded])

  useEffect(() => {
    setRenameValue(project.name)
  }, [project.name])

  useEffect(() => {
    if (!menuOpen) return undefined
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener("mousedown", close)
    return () => document.removeEventListener("mousedown", close)
  }, [menuOpen])

  useEffect(() => {
    if (renaming) renameInputRef.current?.focus()
  }, [renaming])

  const submitRename = useCallback(async () => {
    const trimmed = renameValue.trim()
    if (!trimmed || trimmed === project.name) {
      setRenaming(false)
      setRenameValue(project.name)
      return
    }
    try {
      await onRename(trimmed)
      setRenaming(false)
    } catch {
      window.alert(t("ws.project.renameFail"))
    }
  }, [onRename, project.name, renameValue, t])

  const handleDelete = useCallback(async () => {
    try {
      await onDelete()
      setDeleteOpen(false)
    } catch {
      window.alert(t("ws.project.deleteFail"))
    }
  }, [onDelete, t])

  const handleMigrate = useCallback(async (teamId) => {
    try {
      await onMigrateToTeam(teamId)
      setMigrateOpen(false)
    } catch {
      window.alert(t("ws.project.migrateFail"))
    }
  }, [onMigrateToTeam, t])

  const isPreview = variant === "preview"
  const cardClass = isPreview ? "ws-project-card" : "ws-grid-card"
  const thumbClass = isPreview ? "ws-project-thumb" : "ws-grid-thumb"
  const bodyClass = isPreview ? "ws-project-body" : "ws-grid-body"
  const nameClass = isPreview ? "ws-project-name" : "ws-grid-name"
  const timeClass = isPreview ? "ws-project-time" : "ws-grid-time"

  return (
    <>
      <div
        className={cardClass}
        role="button"
        tabIndex={0}
        onClick={() => !renaming && onOpen()}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !renaming) onOpen()
        }}
      >
        <div className={thumbClass}>
          <ProjectThumb previewUrl={project.preview_url} />
        </div>
        <div className={bodyClass}>
          {isPreview ? (
            renaming ? (
              <input
                ref={renameInputRef}
                className="ws-grid-rename-input"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onClick={sp}
                onKeyDown={(e) => {
                  sp(e)
                  if (e.key === "Enter") submitRename()
                  if (e.key === "Escape") {
                    setRenaming(false)
                    setRenameValue(project.name)
                  }
                }}
                onBlur={submitRename}
              />
            ) : (
              <div className={nameClass}>{project.name}</div>
            )
          ) : (
            <div className="ws-grid-top">
              {renaming ? (
                <input
                  ref={renameInputRef}
                  className="ws-grid-rename-input"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onClick={sp}
                  onKeyDown={(e) => {
                    sp(e)
                    if (e.key === "Enter") submitRename()
                    if (e.key === "Escape") {
                      setRenaming(false)
                      setRenameValue(project.name)
                    }
                  }}
                  onBlur={submitRename}
                />
              ) : (
                <div className={nameClass}>{project.name}</div>
              )}
              <span className="ws-grid-episodes">{t("ws.projects.episode")}</span>
            </div>
          )}
          <div className={timeClass}>
            {formatProjectDate(project.updated_at, t("ws.project.neverEdited"))}
          </div>
        </div>

        <div ref={menuRef} className="ws-grid-menu-wrap">
          <button
            type="button"
            className="ws-grid-menu-btn"
            aria-label={t("canvas.common.moreActions")}
            onClick={(e) => {
              sp(e)
              setMenuOpen((v) => !v)
            }}
          >
            ⋯
          </button>
          {menuOpen && (
            <div className="ws-grid-menu" onPointerDown={sp}>
              <button
                type="button"
                onClick={(e) => {
                  sp(e)
                  setMenuOpen(false)
                  setRenaming(true)
                }}
              >
                {t("ws.project.rename")}
              </button>
              {canMigrate && (
                <button
                  type="button"
                  onClick={(e) => {
                    sp(e)
                    setMenuOpen(false)
                    setMigrateOpen(true)
                  }}
                >
                  {t("ws.project.migrate")}
                </button>
              )}
              <button
                type="button"
                className="ws-grid-menu-danger"
                onClick={(e) => {
                  sp(e)
                  setMenuOpen(false)
                  setDeleteOpen(true)
                }}
              >
                {t("ws.project.delete")}
              </button>
            </div>
          )}
        </div>
      </div>

      {deleteOpen && (
        <ConfirmModal
          title={t("ws.project.delete")}
          body={t("ws.project.deleteConfirm", { name: project.name })}
          confirmLabel={t("ws.project.delete")}
          danger
          onConfirm={handleDelete}
          onClose={() => setDeleteOpen(false)}
        />
      )}

      {migrateOpen && (
        <MigrateToTeamModal
          open={migrateOpen}
          onClose={() => setMigrateOpen(false)}
          projectName={project.name}
          teams={migratableTeams}
          onConfirm={handleMigrate}
        />
      )}
    </>
  )
}
