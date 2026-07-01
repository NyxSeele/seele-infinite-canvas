import "./ScriptUiSelect.css"

const sp = (e) => e.stopPropagation()

export default function ScriptUiSelect({ className = "", wrapperClassName = "", ...props }) {
  return (
    <div className={`st-ui-select-wrap ${wrapperClassName}`.trim()}>
      <select
        className={`st-ui-select nodrag ${className}`.trim()}
        onPointerDown={sp}
        onClick={sp}
        {...props}
      />
    </div>
  )
}
