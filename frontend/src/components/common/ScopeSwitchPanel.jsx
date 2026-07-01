import { useRef } from "react"
import { useScopeSwitchTransition } from "../../hooks/useScopeSwitchTransition"

/**
 * 切换型内容区：出场冻结旧内容，入场播放卡片动画
 */
export default function ScopeSwitchPanel({
  switchKey,
  className = "",
  stagger = false,
  children,
}) {
  const { visualPhase } = useScopeSwitchTransition(switchKey)
  const frozenRef = useRef(children)

  if (visualPhase !== "exiting") {
    frozenRef.current = children
  }

  const content = visualPhase === "exiting" ? frozenRef.current : children

  const classes = [
    "scope-switch-panel",
    visualPhase === "exiting" && "scope-switch-panel--exiting",
    visualPhase === "entering" && "scope-switch-panel--entering",
    stagger && "scope-switch-stagger",
    className,
  ]
    .filter(Boolean)
    .join(" ")

  return <div className={classes}>{content}</div>
}
