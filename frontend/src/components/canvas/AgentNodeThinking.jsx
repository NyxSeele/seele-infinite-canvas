import "./AgentNodeThinking.css"

export default function AgentNodeThinking({ text }) {
  if (!text?.trim()) return null
  return (
    <div className="agent-node-thinking nodrag" role="status">
      <span className="agent-node-thinking__icon" aria-hidden>💭</span>
      <span className="agent-node-thinking__text">{text}</span>
    </div>
  )
}
