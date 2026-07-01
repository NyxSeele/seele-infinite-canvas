import { useCallback, useEffect, useState } from "react"

import { useNavigate } from "react-router-dom"

import { useCanvasStore, useTeamStore } from "../stores"

import { getActiveTeamId } from "../utils/teamContext"

import {

  createCanvasProject,

  deleteCanvasProject,

  listCanvasProjects,

  migrateCanvasProjectToTeam,

  saveCanvasProject,

} from "../services/canvasApi"

import CanvasProfileModal from "../components/canvas/CanvasProfileModal"

import WorkspaceTopbar from "../components/workspace/WorkspaceTopbar"

import WorkspaceProjectCard from "../components/workspace/WorkspaceProjectCard"
import ScopeSwitchPanel from "../components/common/ScopeSwitchPanel"
import { ProjectThumb } from "../components/workspace/workspaceProjectUtils"

import { useLocale } from "../utils/locale"

import "./Canvas.css"

import "./Workspace.css"



export default function WorkspaceProjects() {

  const navigate = useNavigate()

  const theme = useCanvasStore((s) => s.theme)

  const activeTeamId = useTeamStore((s) => s.activeTeamId)

  const { t } = useLocale()



  const [projects, setProjects] = useState([])

  const [loading, setLoading] = useState(true)

  const [creating, setCreating] = useState(false)



  const refresh = useCallback(async () => {

    setLoading(true)

    try {

      const list = await listCanvasProjects({ teamId: getActiveTeamId() })

      setProjects(list)

    } catch (err) {

      console.error(err)

      setProjects([])

    } finally {

      setLoading(false)

    }

  }, [])



  useEffect(() => {

    refresh()

  }, [refresh, activeTeamId])



  useEffect(() => {

    const onTeamChange = () => refresh()

    const onProjectSaved = (e) => {

      const { projectId, updated_at } = e.detail || {}

      if (!projectId || !updated_at) return

      setProjects((prev) => prev.map((p) => (

        p.id === projectId ? { ...p, updated_at } : p

      )))

    }

    window.addEventListener("team-context-changed", onTeamChange)

    window.addEventListener("canvas-project-saved", onProjectSaved)

    window.addEventListener("focus", refresh)

    return () => {

      window.removeEventListener("team-context-changed", onTeamChange)

      window.removeEventListener("canvas-project-saved", onProjectSaved)

      window.removeEventListener("focus", refresh)

    }

  }, [refresh])



  const handleCreate = useCallback(async () => {

    if (creating) return

    setCreating(true)

    try {

      const created = await createCanvasProject({

        name: t("ws.default.canvasName"),

        team_id: getActiveTeamId(),

      })

      navigate(`/canvas/${created.id}`)

    } catch (err) {

      console.error(err)

      window.alert(t("ws.alert.createFail"))

    } finally {

      setCreating(false)

    }

  }, [creating, navigate, t])



  const handleRename = useCallback(async (projectId, name) => {

    await saveCanvasProject(projectId, { name })

    setProjects((prev) => prev.map((p) => (

      p.id === projectId ? { ...p, name, updated_at: new Date().toISOString() } : p

    )))

  }, [])



  const handleDelete = useCallback(async (projectId) => {

    await deleteCanvasProject(projectId)

    setProjects((prev) => prev.filter((p) => p.id !== projectId))

  }, [])



  const handleMigrateToTeam = useCallback(async (projectId, teamId) => {

    await migrateCanvasProjectToTeam(projectId, teamId)

    setProjects((prev) => prev.filter((p) => p.id !== projectId))

  }, [])



  const emptyMsg = activeTeamId
    ? t("ws.projects.emptyTeam")
    : t("ws.projects.emptyPersonal")

  const teamSwitchKey = activeTeamId || "personal"

  return (
    <div className={`ws-page ws-page--scroll rf-page--${theme}`}>
      <WorkspaceTopbar
        onBack={() => navigate("/workspace")}
        title={activeTeamId ? t("ws.projects.teamTitle") : t("ws.projects.personalTitle")}
      />

      <ScopeSwitchPanel switchKey={teamSwitchKey} className="ws-projects-page">
        {loading ? (
          <div className="ws-empty">{t("ws.loading")}</div>
        ) : projects.length === 0 ? (
          <div className="ws-empty">
            <p>{emptyMsg}</p>
            <div className="ws-empty-actions">
              <button
                type="button"
                className="ws-btn-primary"
                disabled={creating}
                onClick={handleCreate}
              >
                {creating ? t("ws.loading") : t("ws.project.new")}
              </button>
              <button type="button" className="ws-link-btn" onClick={() => navigate("/workspace")}>
                {t("canvas.project.backWorkspace")}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="ws-projects-grid scope-switch-stagger">
              {projects.map((p, i) => (
                <div key={p.id} style={{ "--i": i }}>
                  <WorkspaceProjectCard
                    project={p}
                    onOpen={() => navigate(`/canvas/${p.id}`)}
                    onRename={(name) => handleRename(p.id, name)}
                    onDelete={() => handleDelete(p.id)}
                    onMigrateToTeam={(teamId) => handleMigrateToTeam(p.id, teamId)}
                  />
                </div>
              ))}
              <button
                type="button"
                className="ws-grid-card ws-grid-card--new"
                style={{ "--i": projects.length }}
                disabled={creating}
                onClick={handleCreate}
              >
                <div className="ws-grid-thumb ws-grid-thumb--new">
                  <ProjectThumb previewUrl={null} empty />
                  <span className="ws-grid-new-plus">+</span>
                </div>
                <div className="ws-grid-body">
                  <div className="ws-grid-name">{t("ws.project.new")}</div>
                  <div className="ws-grid-time">{t("ws.project.blank")}</div>
                </div>
              </button>
            </div>
            <p className="ws-projects-end">{t("ws.projects.allLoaded")}</p>
          </>
        )}
      </ScopeSwitchPanel>

      <CanvasProfileModal />
    </div>
  )
}


