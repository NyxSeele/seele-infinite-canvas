import { createContext, useContext } from "react"

export const CanvasActionsContext = createContext(null)

export function useCanvasActions() {
  return useContext(CanvasActionsContext)
}

// Separate context for reference select mode to avoid re-rendering everything
export const ReferenceSelectContext = createContext(null)

export function useReferenceSelect() {
  return useContext(ReferenceSelectContext)
}
