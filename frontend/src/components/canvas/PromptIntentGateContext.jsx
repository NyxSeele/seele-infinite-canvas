import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react"
import { TEXT_MODES } from "../../utils/canvas/nodeHelpers"
import {
  classifyPromptIntent,
  shouldConfirmIntent,
} from "../../services/promptIntentApi"
import { TEXT_CLASSIFY_MIN } from "../../utils/canvas/promptIntentConfig"
import { useLocale } from "../../utils/locale"
import PromptIntentConfirm from "./PromptIntentConfirm"

const PromptIntentGateContext = createContext(null)

/**
 * @typedef {{ text: string, context?: 'text', textMode?: string, contextLabel?: string, forceClassify?: boolean }} GateRequest
 */

export function PromptIntentGateProvider({ children, onSwitchTextScreenplay }) {
  const { t } = useLocale()
  const [modal, setModal] = useState({
    open: false,
    loading: false,
    result: null,
    editedPrompt: "",
    contextLabel: "",
  })
  const resolverRef = useRef(null)

  const closeModal = useCallback(() => {
    setModal({
      open: false,
      loading: false,
      result: null,
      editedPrompt: "",
      contextLabel: "",
    })
  }, [])

  const cancelGate = useCallback(() => {
    resolverRef.current?.(null)
    resolverRef.current = null
    closeModal()
  }, [closeModal])

  const requestIntentGate = useCallback(
    (request) => {
      const text = (request?.text || "").trim()
      if (!text) return Promise.resolve(null)

      const textMode = request?.textMode || null
      const promptLength = text.length

      const shouldClassify =
        request?.forceClassify || promptLength >= TEXT_CLASSIFY_MIN

      if (!shouldClassify) {
        return Promise.resolve(text)
      }

      return new Promise((resolve) => {
        resolverRef.current = resolve
        setModal({
          open: true,
          loading: true,
          result: null,
          editedPrompt: text,
          contextLabel: request?.contextLabel || t("canvas.intent.currentCard"),
        })

        classifyPromptIntent(text, {
          context: "text",
          currentTextMode: textMode,
        })
          .then((result) => {
            const needModal = shouldConfirmIntent(result, {
              textMode,
              promptLength,
            })
            if (!needModal) {
              const fp = (result.generation_prompt || "").trim() || text
              resolverRef.current?.(fp)
              resolverRef.current = null
              closeModal()
              return
            }
            const gen = (result.generation_prompt || "").trim() || text
            setModal({
              open: true,
              loading: false,
              result,
              editedPrompt: gen,
              contextLabel: request?.contextLabel || t("canvas.intent.currentCard"),
            })
          })
          .catch((err) => {
            console.warn("classify-intent failed, proceed with raw text", err)
            resolverRef.current?.(text)
            resolverRef.current = null
            closeModal()
          })
      })
    },
    [closeModal, t]
  )

  const handleConfirm = useCallback(
    (editedPrompt) => {
      const fp = (editedPrompt || modal.editedPrompt || "").trim()
      resolverRef.current?.(fp || null)
      resolverRef.current = null
      closeModal()
    },
    [modal, closeModal]
  )

  const handleSwitchScreenplay = useCallback(() => {
    onSwitchTextScreenplay?.()
    resolverRef.current?.(null)
    resolverRef.current = null
    closeModal()
  }, [onSwitchTextScreenplay, closeModal])

  const value = useMemo(
    () => ({ requestIntentGate }),
    [requestIntentGate]
  )

  const isScreenplay = modal.result?.intent === "screenplay"

  return (
    <PromptIntentGateContext.Provider value={value}>
      {children}
      <PromptIntentConfirm
        open={modal.open}
        loading={modal.loading}
        result={modal.result}
        editedPrompt={modal.editedPrompt}
        onEditedPromptChange={(v) =>
          setModal((m) => ({ ...m, editedPrompt: v }))
        }
        contextLabel={modal.contextLabel}
        onCancel={cancelGate}
        onConfirm={handleConfirm}
        onSwitchScreenplay={
          isScreenplay ? handleSwitchScreenplay : undefined
        }
      />
    </PromptIntentGateContext.Provider>
  )
}

export function usePromptIntentGate() {
  const ctx = useContext(PromptIntentGateContext)
  if (!ctx) {
    throw new Error("usePromptIntentGate must be used within PromptIntentGateProvider")
  }
  return ctx
}

/** 节点未包 Provider 时不抛错（兼容测试） */
export function usePromptIntentGateOptional() {
  return useContext(PromptIntentGateContext)
}

export { TEXT_MODES }
