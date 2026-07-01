import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { useLocale } from "../../utils/locale"

const EDIT_ROLES = new Set(["owner", "admin", "editor"])

export function getMigratableTeams(allTeams) {
  return (allTeams || []).filter((t) => t?.id && EDIT_ROLES.has(t.my_role))
}

export default function MigrateToTeamModal({
  open,
  onClose,
  projectName,
  teams,
  onConfirm,
}) {
  const { t } = useLocale()
  const [selectedId, setSelectedId] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setSelectedId(teams[0]?.id || "")
  }, [open, teams])

  if (!open) return null

  const handleConfirm = async () => {
    if (!selectedId || loading) return
    setLoading(true)
    try {
      await onConfirm(selectedId)
    } finally {
      setLoading(false)
    }
  }

  return createPortal(
    <div className="ws-modal-overlay" onClick={onClose}>
      <div className="ws-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ws-modal-title">{t("ws.project.migrateTitle")}</div>
        <p className="ws-modal-body">
          {t("ws.project.migrateBody", { name: projectName })}
        </p>
        {teams.length > 1 ? (
          <div className="ws-migrate-team-list">
            {teams.map((team) => (
              <label key={team.id} className="ws-migrate-team-item">
                <input
                  type="radio"
                  name="migrate-team"
                  value={team.id}
                  checked={selectedId === team.id}
                  onChange={() => setSelectedId(team.id)}
                />
                <span>{team.name}</span>
              </label>
            ))}
          </div>
        ) : teams.length === 1 ? (
          <p className="ws-migrate-team-single">
            {t("ws.project.migrateTarget", { team: teams[0].name })}
          </p>
        ) : null}
        <div className="ws-modal-footer">
          <button type="button" className="ws-btn-ghost" onClick={onClose}>
            {t("canvas.common.cancel")}
          </button>
          <button
            type="button"
            className="ws-btn-primary"
            onClick={handleConfirm}
            disabled={loading || !selectedId}
          >
            {loading ? t("ws.project.migrateLoading") : t("ws.project.migrateConfirm")}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}
