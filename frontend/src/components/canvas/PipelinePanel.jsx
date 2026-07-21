import { useCallback, useEffect, useMemo, useState } from "react"
import { useStore } from "reactflow"
import { getPipelineManifest } from "../../services/agentApi"
import {
  getPipelinePanelState,
  isPipelineStepComplete,
  mapInferStageToManifestStep,
} from "../../utils/canvas/pipelinePanelState"
import "./PipelinePanel.css"

export default function PipelinePanel({
  projectId,
  readOnly = false,
  agentSendRef,
}) {
  const [open, setOpen] = useState(false)
  const [stages, setStages] = useState([])
  const [manifestError, setManifestError] = useState("")

  const nodes = useStore((s) => Array.from(s.nodeInternals.values()))
  const edges = useStore((s) => s.edges)

  useEffect(() => {
    if (!projectId) return undefined
    let cancelled = false
    ;(async () => {
      try {
        const data = await getPipelineManifest("velora_canvas")
        const list = Array.isArray(data?.stages) ? data.stages : []
        if (!cancelled) {
          setStages(list)
          if (import.meta.env.DEV) {
            console.assert(list.length === 9, "velora_canvas manifest should have 9 stages", list.length)
          }
        }
      } catch (e) {
        if (!cancelled) setManifestError(e?.message || "加载 pipeline 失败")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  const { currentStep } = useMemo(
    () => getPipelinePanelState(nodes, edges),
    [nodes, edges]
  )

  const runStep = useCallback(
    (stepName) => {
      if (readOnly || !agentSendRef?.current) return
      agentSendRef.current(`请执行 pipeline 步骤：${stepName}`)
    },
    [readOnly, agentSendRef]
  )

  const continuePipeline = useCallback(() => {
    if (readOnly || !agentSendRef?.current) return
    agentSendRef.current("继续")
  }, [readOnly, agentSendRef])

  if (!projectId) return null

  return (
    <aside className={`pipeline-panel${open ? " pipeline-panel--open" : ""}`}>
      <button
        type="button"
        className="pipeline-panel__tab"
        onClick={() => setOpen(true)}
        aria-label="展开 Pipeline"
      >
        Pipeline
      </button>

      <header className="pipeline-panel__header">
        <h2 className="pipeline-panel__title">主链 Pipeline</h2>
        <button
          type="button"
          className="pipeline-panel__close"
          onClick={() => setOpen(false)}
          aria-label="收起"
        >
          ×
        </button>
      </header>

      <div className="pipeline-panel__actions">
        <button
          type="button"
          className="pipeline-panel__btn pipeline-panel__btn--primary"
          disabled={readOnly || !agentSendRef?.current}
          onClick={continuePipeline}
        >
          继续
        </button>
      </div>

      {manifestError ? (
        <p className="pipeline-panel__hint" style={{ padding: "0 14px" }}>
          {manifestError}
        </p>
      ) : null}

      <ol className="pipeline-panel__list">
        {stages.map((stage) => {
          const name = stage.name
          const done = isPipelineStepComplete(name, nodes, edges)
          const mapped = mapInferStageToManifestStep(currentStep)
          const isCurrent =
            name === mapped
            || (mapped === "pipeline_complete" && name === "generate_video" && !done)
          return (
            <li
              key={name}
              className={`pipeline-panel__step${done ? " pipeline-panel__step--done" : ""}${isCurrent ? " pipeline-panel__step--current" : ""}`}
            >
              <div className="pipeline-panel__step-row">
                <span className="pipeline-panel__check" aria-hidden="true">
                  {done ? "✓" : stage.order}
                </span>
                <span className="pipeline-panel__label">
                  {stage.ui_label || stage.name}
                  {stage.optional ? (
                    <span className="pipeline-panel__optional">可选</span>
                  ) : null}
                </span>
              </div>
              <button
                type="button"
                className="pipeline-panel__run"
                disabled={readOnly}
                onClick={() => runStep(name)}
              >
                运行此步
              </button>
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
