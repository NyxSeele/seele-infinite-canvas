import { Component } from "react"
import "./CanvasErrorBoundary.css"

export default class CanvasErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, resetKey: 0 }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error("[Canvas] error boundary caught:", error, info)
  }

  handleRetry = () => {
    this.setState((prev) => ({
      error: null,
      resetKey: prev.resetKey + 1,
    }))
  }

  render() {
    const { error, resetKey } = this.state
    if (error) {
      return (
        <div className="canvas-error-boundary" role="alert">
          <p className="canvas-error-boundary__title">画布加载出错</p>
          <p className="canvas-error-boundary__detail">
            {error?.message || "未知错误"}
          </p>
          <button
            type="button"
            className="canvas-error-boundary__retry"
            onClick={this.handleRetry}
          >
            点击重试
          </button>
        </div>
      )
    }

    return (
      <div key={resetKey} className="canvas-error-boundary__content">
        {this.props.children}
      </div>
    )
  }
}
