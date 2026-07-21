import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useAuth } from "../contexts/AuthContext"
import { useCanvasStore, useTeamStore } from "../stores"
import { getActiveTeamId } from "../utils/teamContext"
import { createCanvasProject, deleteCanvasProject, listCanvasProjects, migrateCanvasProjectToTeam, saveCanvasProject } from "../services/canvasApi"
import WorkspaceProjectCard from "../components/workspace/WorkspaceProjectCard"
import { buildScriptCanvasData } from "../utils/canvas/canvasBootstrap"
import CanvasProfileModal from "../components/canvas/CanvasProfileModal"
import WorkspaceTopbar from "../components/workspace/WorkspaceTopbar"
import WorkspaceDropSelect from "../components/workspace/WorkspaceDropSelect"
import ScopeSwitchPanel from "../components/common/ScopeSwitchPanel"
import { LineIcon } from "../components/icons/LineIcons"
import {
  getEpisodeOptions,
  getRatioOptions,
  RatioShape,
} from "../components/workspace/workspaceProjectUtils"
import ImportDocumentModal from "../components/canvas/ImportDocumentModal"
import { showDevNotice } from "../components/common/ProductNoticeModal"
import { useLocale } from "../utils/locale"
import { navigateWithReturn } from "../utils/navReturn"
import OnboardingTour from "../components/Onboarding/OnboardingTour"
import { WORKSPACE_STEPS } from "../components/Onboarding/tourSteps"

const SCRIPT_MAX_CHARS = 100_000
import "./Canvas.css"
import "./Workspace.css"

const PREFS_KEY = "canvas-user-profile-prefs"

function readDisplayName(fallback) {
  try {
    const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")
    return prefs.displayName || fallback || ""
  } catch {
    return fallback || ""
  }
}

function TabUploadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 5v6M5.5 7.5 8 5l2.5 2.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function TabAiIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M8 1.5l1.2 4.3 4.3 1.2-4.3 1.2L8 12.5 6.8 8.2 2.5 7l4.3-1.2L8 1.5Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
    </svg>
  )
}

function TabCanvasIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="2.5" y="2.5" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.2" />
      <path d="M5.5 10.5 7.5 6.5l2 2 2.5-3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function Workspace() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuth()
  const theme = useCanvasStore((s) => s.theme)
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const allTeams = useTeamStore((s) => s.allTeams)
  const activeTeam = activeTeamId ? allTeams.find((t) => t.id === activeTeamId) : null
  const teamSwitchKey = activeTeamId || "personal"
  const { t } = useLocale()

  const [tab, setTab] = useState("upload")
  const [uploadPasteOpen, setUploadPasteOpen] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [scriptText, setScriptText] = useState("")
  const [aiStoryText, setAiStoryText] = useState("")
  const [episodeValue, setEpisodeValue] = useState("10")
  const [customEpisode, setCustomEpisode] = useState("12")
  const [ratioValue, setRatioValue] = useState("default")
  const [importDocumentOpen, setImportDocumentOpen] = useState(false)
  const [importProjectId, setImportProjectId] = useState("")
  const [importInitialFile, setImportInitialFile] = useState(null)
  const [importBusy, setImportBusy] = useState(false)

  const uploadInputRef = useRef(null)
  const importFileInputRef = useRef(null)

  const displayName = useMemo(
    () => readDisplayName(user?.username) || user?.username || t("ws.default.creator"),
    [user?.username, t]
  )

  const toolChipClass = useCallback(
    (path) => `ws-tool-chip${location.pathname === path ? " ws-tool-chip--active" : ""}`,
    [location.pathname],
  )

  const episodeOptions = useMemo(() => getEpisodeOptions(t), [t])
  const ratioOptions = useMemo(() => getRatioOptions(t), [t])

  const refresh = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true)
    try {
      const list = await listCanvasProjects({ teamId: getActiveTeamId(), limit: 48 })
      setProjects(list)
    } catch (err) {
      console.error(err)
      if (!silent) setProjects([])
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh, activeTeamId])

  useEffect(() => {
    const onTeamChange = () => refresh()
    const onProjectSaved = (e) => {
      const {
        projectId,
        updated_at,
        preview_url,
        cover_media_type,
        recent_collaborators,
        collaborator_extra_count,
      } = e.detail || {}
      if (!projectId) return
      setProjects((prev) => prev.map((p) => {
        if (p.id !== projectId) return p
        const next = { ...p }
        if (updated_at) next.updated_at = updated_at
        if (preview_url !== undefined && preview_url !== null) next.preview_url = preview_url
        if (cover_media_type !== undefined) next.cover_media_type = cover_media_type
        if (recent_collaborators) next.recent_collaborators = recent_collaborators
        if (collaborator_extra_count !== undefined) {
          next.collaborator_extra_count = collaborator_extra_count
        }
        return next
      }))
    }
    let lastRefreshAt = 0
    const REFRESH_MIN_GAP_MS = 30_000
    const softRefresh = () => {
      const now = Date.now()
      if (now - lastRefreshAt < REFRESH_MIN_GAP_MS) return
      lastRefreshAt = now
      void refresh({ silent: true })
    }
    const onVisible = () => {
      if (document.visibilityState === "visible") softRefresh()
    }
    const onFocus = () => softRefresh()
    window.addEventListener("team-context-changed", onTeamChange)
    window.addEventListener("canvas-project-saved", onProjectSaved)
    window.addEventListener("focus", onFocus)
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      window.removeEventListener("team-context-changed", onTeamChange)
      window.removeEventListener("canvas-project-saved", onProjectSaved)
      window.removeEventListener("focus", onFocus)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [refresh])

  const openProject = useCallback(
    (id) => {
      if (!id) return
      navigate(`/canvas/${id}`)
    },
    [navigate]
  )

  const handleRenameProject = useCallback(async (projectId, name) => {
    const res = await saveCanvasProject(projectId, { name })
    setProjects((prev) => prev.map((p) => (
      p.id === projectId
        ? {
            ...p,
            name,
            updated_at: res.updated_at ?? p.updated_at,
            preview_url: res.preview_url ?? p.preview_url,
          }
        : p
    )))
  }, [])

  const handleDeleteProject = useCallback(async (projectId) => {
    await deleteCanvasProject(projectId)
    setProjects((prev) => prev.filter((p) => p.id !== projectId))
  }, [])

  const handleMigrateToTeam = useCallback(async (projectId, teamId) => {
    await migrateCanvasProjectToTeam(projectId, teamId)
    setProjects((prev) => prev.filter((p) => p.id !== projectId))
  }, [])

  const createAndOpen = useCallback(
    async ({ name = null, canvas_data = null } = {}) => {
      const projectName = name || t("ws.default.canvasName")
      if (busy) return null
      setBusy(true)
      try {
        const created = await createCanvasProject({
          name: projectName,
          canvas_data,
          team_id: getActiveTeamId(),
        })
        navigate(`/canvas/${created.id}`)
        return created.id
      } catch (err) {
        console.error(err)
        window.alert(t("ws.alert.createFail"))
        return null
      } finally {
        setBusy(false)
      }
    },
    [busy, navigate, t]
  )

  const handleBlank = useCallback(() => {
    createAndOpen()
  }, [createAndOpen])

  const startWithScript = useCallback(
    (text, defaultTitle) => {
      const trimmed = String(text || "").trim()
      if (!trimmed) {
        window.alert(t("ws.alert.noScript"))
        return
      }
      const titleDefault = defaultTitle || t("ws.default.scriptTitle")
      const title =
        trimmed.split(/\r?\n/).find((l) => l.trim())?.slice(0, 32) || titleDefault
      const canvas_data = buildScriptCanvasData(trimmed, title)
      createAndOpen({
        name: canvas_data.project_name || title,
        canvas_data: { nodes: canvas_data.nodes, edges: canvas_data.edges },
      })
    },
    [createAndOpen, t]
  )

  const applyScriptText = useCallback((text) => {
    const trimmed = String(text || "").trim()
    if (!trimmed) return
    if (trimmed.length > SCRIPT_MAX_CHARS) {
      window.alert(t("ws.alert.scriptTooLong"))
      return
    }
    setScriptText(trimmed)
    setUploadPasteOpen(true)
  }, [t])

  const readScriptFile = useCallback(async (file) => {
    if (!file) return
    if (!/\.(txt|docx)$/i.test(file.name)) {
      window.alert(t("ws.alert.fileFormat"))
      return
    }
    if (/\.docx$/i.test(file.name)) {
      try {
        const buf = await file.arrayBuffer()
        const mammoth = await import("mammoth")
        const result = await mammoth.default.extractRawText({ arrayBuffer: buf })
        applyScriptText(result.value)
      } catch (err) {
        console.error(err)
        window.alert(t("ws.alert.docxParseFail"))
      }
      return
    }
    const reader = new FileReader()
    reader.onload = () => applyScriptText(reader.result)
    reader.readAsText(file, "UTF-8")
  }, [t, applyScriptText])

  const handleUploadFile = useCallback((e) => {
    readScriptFile(e.target.files?.[0])
    e.target.value = ""
  }, [readScriptFile])

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files?.[0]
      if (file) readScriptFile(file)
    },
    [readScriptFile]
  )

  const handleOpenImportDocument = useCallback(() => {
    if (busy || importBusy) return
    importFileInputRef.current?.click()
  }, [busy, importBusy])

  const handleImportFileChange = useCallback(
    async (e) => {
      const file = e.target.files?.[0]
      e.target.value = ""
      if (!file) return

      const ext = (file.name.split(".").pop() || "").toLowerCase()
      if (ext === "xls") {
        window.alert(t("ws.alert.xlsUnsupported"))
        return
      }
      if (ext === "doc") {
        window.alert(t("ws.alert.docUnsupported"))
        return
      }
      if (!["xlsx", "docx"].includes(ext)) {
        window.alert(t("ws.alert.importFileFormat"))
        return
      }

      setImportBusy(true)
      setBusy(true)
      try {
        const created = await createCanvasProject({
          name: t("ws.default.canvasName"),
          team_id: getActiveTeamId(),
        })
        setImportProjectId(created.id)
        setImportInitialFile(file)
        setImportDocumentOpen(true)
      } catch (err) {
        console.error(err)
        window.alert(t("ws.alert.createFail"))
      } finally {
        setImportBusy(false)
        setBusy(false)
      }
    },
    [t]
  )

  const handleCloseImportDocument = useCallback(() => {
    setImportDocumentOpen(false)
    setImportProjectId("")
    setImportInitialFile(null)
  }, [])

  const handleFreeCanvasTab = useCallback(() => {
    if (!busy) handleBlank()
  }, [busy, handleBlank])

  const selectedRatio = ratioOptions.find((o) => o.value === ratioValue)
  const tabIndex = tab === "ai" ? 1 : 0

  return (
    <div className={`ws-page ws-page--workspace ws-page--scroll rf-page--${theme}`}>
      <WorkspaceTopbar />

      <div className="ws-shell">
        <section className="ws-hero">
          <h1 className="ws-hero-title">
            {t("ws.greeting.prefix")}
            <span className="ws-hero-username">{displayName}</span>
          </h1>
          <p className="ws-hero-sub">
            {t("ws.hero.sub")}
          </p>
        </section>

        <section className="ws-entry">
          <div
            className={`ws-tab-strip ws-tab-strip--${tab}`}
            role="tablist"
            style={{ "--tab-index": tabIndex }}
          >
            <div className="ws-tab-indicator" aria-hidden />
            <button
                type="button"
                role="tab"
                aria-selected={tab === "upload"}
                className={`ws-tab${tab === "upload" ? " ws-tab--active" : ""}`}
                onClick={() => setTab("upload")}
              >
                <TabUploadIcon />
                {t("ws.tab.upload")}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "ai"}
                className={`ws-tab${tab === "ai" ? " ws-tab--active" : ""}`}
                onClick={() => setTab("ai")}
              >
                <TabAiIcon />
                {t("ws.tab.ai")}
                <span className="ws-tab-badge">{t("ws.tab.aiBadge")}</span>
              </button>
              <button
                type="button"
                className="ws-tab ws-tab--canvas"
                onClick={handleFreeCanvasTab}
                disabled={busy}
              >
                <span className="ws-tab-hash" aria-hidden>
                  <TabCanvasIcon />
                </span>
                {t("ws.tab.canvas")}
            </button>
          </div>

          <div className={`ws-entry-body ws-entry-body--${tab}`}>
            <ScopeSwitchPanel switchKey={tab} className="ws-entry-body-switch">
            {tab === "upload" && (
              <div className="ws-upload-panel">
                <div
                  className={`ws-dropzone${dragOver ? " ws-dropzone--over" : ""}`}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                >
                  <ScopeSwitchPanel
                    switchKey={uploadPasteOpen ? "paste" : "actions"}
                    className="ws-dropzone-switch"
                  >
                  {!uploadPasteOpen ? (
                    <>
                      <div className="ws-dropzone-icon" aria-hidden>
                        <LineIcon name="doc" size={28} />
                      </div>
                      <div className="ws-dropzone-actions">
                        <button
                          type="button"
                          className="ws-btn-dark"
                          disabled={busy}
                          onClick={() => uploadInputRef.current?.click()}
                        >
                          {t("ws.upload.btn")}
                        </button>
                        <button
                          type="button"
                          className="ws-btn-outline"
                          disabled={busy}
                          onClick={() => setUploadPasteOpen(true)}
                        >
                          {t("ws.upload.paste")}
                        </button>
                        <button
                          type="button"
                          className="ws-btn-outline"
                          disabled={busy}
                          onClick={handleOpenImportDocument}
                        >
                          {importBusy ? t("ws.upload.importCreating") : t("canvas.menu.importDocument")}
                        </button>
                      </div>
                      <p className="ws-dropzone-hint">{t("ws.upload.hint")}</p>
                    </>
                  ) : (
                    <>
                      <textarea
                        className="ws-paste-area"
                        placeholder={t("ws.upload.pastePh")}
                        value={scriptText}
                        onChange={(e) => setScriptText(e.target.value)}
                      />
                      <div className="ws-paste-actions">
                        <button
                          type="button"
                          className="ws-btn-dark"
                          disabled={busy}
                          onClick={() => startWithScript(scriptText)}
                        >
                          {t("ws.upload.start")}
                        </button>
                        <button
                          type="button"
                          className="ws-btn-ghost"
                          onClick={() => { setUploadPasteOpen(false); setScriptText("") }}
                        >
                          {t("ws.upload.back")}
                        </button>
                      </div>
                    </>
                  )}
                  </ScopeSwitchPanel>
                  <input
                    ref={uploadInputRef}
                    type="file"
                    accept=".txt,.docx,text/plain"
                    hidden
                    onChange={handleUploadFile}
                  />
                  <input
                    ref={importFileInputRef}
                    type="file"
                    accept=".xlsx,.xls,.docx,.doc"
                    hidden
                    onChange={handleImportFileChange}
                  />
                </div>
              </div>
            )}

            {tab === "ai" && (
              <>
                <div className="ws-ai-panel">
                  <div className="ws-ai-input-inner">
                    <textarea
                      className="ws-ai-textarea"
                      placeholder={t("ws.ai.placeholder")}
                      value={aiStoryText}
                      onChange={(e) => setAiStoryText(e.target.value)}
                    />
                  </div>
                </div>
                <div className="ws-ai-toolbar">
                  <div className="ws-ai-options">
                    <button
                      type="button"
                      className="ws-plain-opt"
                      onClick={() => showDevNotice(t("ws.ai.styleLib"))}
                    >
                      <LineIcon name="style" size={16} />
                      <span>{t("ws.ai.styleLib")}</span>
                    </button>
                    <span className="ws-ai-opt-sep" />
                    <WorkspaceDropSelect
                      value={ratioValue}
                      options={ratioOptions}
                      onChange={setRatioValue}
                      prefixIcon={selectedRatio?.icon ?? <RatioShape w={0} h={0} />}
                      placement="bottom"
                    />
                    <WorkspaceDropSelect
                      value={episodeValue}
                      options={episodeOptions}
                      onChange={setEpisodeValue}
                      customOption={{ suffix: t("ws.episodeUnit") }}
                      customValue={customEpisode}
                      onCustomChange={setCustomEpisode}
                      placement="bottom"
                    />
                  </div>
                  <button
                    type="button"
                    className={`ws-ai-generate${aiStoryText.trim() ? " ws-ai-generate--ready" : " ws-ai-generate--disabled"}`}
                    disabled={busy || !aiStoryText.trim()}
                    onClick={() => startWithScript(aiStoryText, t("ws.default.aiScriptTitle"))}
                  >
                    {t("ws.ai.generate")}
                  </button>
                </div>
              </>
            )}
            </ScopeSwitchPanel>
          </div>
        </section>

        <footer className="ws-entry-foot">
          <div className="ws-foot-row">
            <span className="ws-foot-hint">
              <span className="ws-foot-info"><LineIcon name="info" size={14} /></span>
              {tab === "ai"
                ? t("ws.foot.aiHint")
                : t("ws.foot.uploadHint")}
            </span>
            <span className="ws-foot-divider" aria-hidden />
            <button type="button" className="ws-foot-skip" disabled={busy} onClick={handleBlank}>
              {t("ws.foot.skip")}
            </button>
          </div>
        </footer>
      </div>

      <ScopeSwitchPanel switchKey={teamSwitchKey} className="ws-team-switch-panel">
        {activeTeam && !loading && projects.length === 0 && (
          <section className="ws-team-guide">
            <h3 className="ws-team-guide-title">{t("ws.team.guide.title")}</h3>
            <p className="ws-team-guide-desc">{t("ws.team.guide.desc")}</p>
            <div className="ws-team-guide-actions">
              <button type="button" className="ws-btn-dark" disabled={busy} onClick={() => setTab("upload")}>
                {t("ws.team.guide.upload")}
              </button>
              <button type="button" className="ws-btn-outline" disabled={busy} onClick={handleBlank}>
                {t("ws.team.guide.blank")}
              </button>
            </div>
          </section>
        )}

        <section className="ws-projects ws-projects--wide">
          <div className="ws-section-head">
            <h2 className="ws-section-title">
              {activeTeam ? `${activeTeam.name} · ${t("ws.projects")}` : t("ws.projects")}
            </h2>
            <div className="ws-section-actions">
              <div className="ws-tool-chips" aria-label="快捷入口">
                <button
                  type="button"
                  className={toolChipClass("/team-files")}
                  data-tour="ws-team-files"
                  onClick={() => navigateWithReturn(navigate, location, "/team-files")}
                >
                  <LineIcon name="doc" size={15} />
                  <span>团队文件</span>
                </button>
                <button
                  type="button"
                  className={toolChipClass("/review-publish")}
                  data-tour="ws-review"
                  onClick={() => navigateWithReturn(navigate, location, "/review-publish")}
                >
                  <LineIcon name="video" size={15} />
                  <span>视频审阅</span>
                </button>
                <button
                  type="button"
                  className={toolChipClass("/review")}
                  data-tour="ws-review-public"
                  onClick={() => navigateWithReturn(navigate, location, "/review")}
                >
                  <LineIcon name="book" size={15} />
                  <span>审阅公开页</span>
                </button>
                <button
                  type="button"
                  className={toolChipClass("/workspace/projects")}
                  onClick={() => navigate("/workspace/projects")}
                >
                  <LineIcon name="folder" size={15} />
                  <span>{t("ws.projects.all")}</span>
                </button>
              </div>
            </div>
          </div>
          {loading ? (
            <div className="ws-empty">{t("ws.loading")}</div>
          ) : (
            <div className="ws-project-grid scope-switch-stagger">
              <button
                type="button"
                className="ws-project-card ws-project-new"
                style={{ "--i": 0 }}
                disabled={busy}
                onClick={handleBlank}
              >
                <div className="ws-project-thumb ws-project-thumb--new">
                  <span className="ws-project-new-plus" aria-hidden>+</span>
                </div>
                <div className="ws-project-body">
                  <div className="ws-project-name">{t("ws.project.new")}</div>
                  <div className="ws-project-time ws-project-time--new">{t("ws.project.blank")}</div>
                </div>
              </button>
              {projects.slice(0, 9).map((p, i) => (
                <div key={p.id} style={{ "--i": i + 1 }}>
                  <WorkspaceProjectCard
                    variant="preview"
                    project={p}
                    isRecentEdited={i === 0}
                    onOpen={() => openProject(p.id)}
                    onRename={(name) => handleRenameProject(p.id, name)}
                    onDelete={() => handleDeleteProject(p.id)}
                    onMigrateToTeam={(teamId) => handleMigrateToTeam(p.id, teamId)}
                  />
                </div>
              ))}
            </div>
          )}
        </section>
      </ScopeSwitchPanel>

      <CanvasProfileModal />

      <ImportDocumentModal
        open={importDocumentOpen}
        onClose={handleCloseImportDocument}
        projectId={importProjectId}
        initialFile={importInitialFile}
        theme={theme}
        onApplied={(result) => {
          handleCloseImportDocument()
          if (result?.projectId) navigate(`/canvas/${result.projectId}`)
        }}
      />

      <OnboardingTour tourId="ws" steps={WORKSPACE_STEPS} />
    </div>
  )
}
