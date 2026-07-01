import { useCallback, useRef } from "react"

export function useCanvasZIndex(setNodes) {
  const zIndexCounterRef = useRef(0)

  const bumpZIndex = useCallback(() => {
    zIndexCounterRef.current += 1
    return zIndexCounterRef.current
  }, [])

  const applyNodeZIndex = useCallback((node, z) => ({
    ...node,
    zIndex: z,
    data: { ...node.data, zIndex: z },
    style: { ...node.style, zIndex: z },
  }), [])

  const raiseNodeToFront = useCallback(
    (nodeId) => {
      const z = bumpZIndex()
      setNodes((ns) => ns.map((n) => (n.id === nodeId ? applyNodeZIndex(n, z) : n)))
    },
    [bumpZIndex, applyNodeZIndex, setNodes]
  )

  return { zIndexCounterRef, bumpZIndex, applyNodeZIndex, raiseNodeToFront }
}
