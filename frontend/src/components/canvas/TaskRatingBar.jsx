import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { submitTaskRating } from "../../services/tasksApi"
import { RATING_TAG_OTHER, ratingTagsForTaskType } from "../../constants/ratingTags"
import "./TaskRatingBar.css"

export { RATING_TAG_OTHER, IMAGE_RATING_TAGS, VIDEO_RATING_TAGS } from "../../constants/ratingTags"

export default function TaskRatingBar({
  taskId,
  taskType = "image",
  userRating = null,
  ratingTags = [],
  ratingComment = "",
  onRated,
}) {
  const [satisfaction, setSatisfaction] = useState(null)
  const [selectedTags, setSelectedTags] = useState([])
  const [comment, setComment] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const otherInputRef = useRef(null)

  const tagOptions = useMemo(() => ratingTagsForTaskType(taskType), [taskType])
  const regularTags = useMemo(
    () => tagOptions.filter((tag) => tag !== RATING_TAG_OTHER),
    [tagOptions]
  )
  const hasRated = userRating === 0 || userRating === 1
  const storedTags = Array.isArray(ratingTags) ? ratingTags : []
  const needsComment = selectedTags.includes(RATING_TAG_OTHER)
  const canSubmitNegative = selectedTags.length > 0 && (!needsComment || comment.trim().length > 0)
  const canSubmit =
    satisfaction === 1 || (satisfaction === 0 && canSubmitNegative)

  const resetForm = useCallback(() => {
    setSatisfaction(null)
    setSelectedTags([])
    setComment("")
    setError("")
  }, [])

  const finishRating = useCallback(
    async (rating, tags, ratingCommentText = "") => {
      if (!taskId || submitting || hasRated) return
      setSubmitting(true)
      setError("")
      try {
        await submitTaskRating(taskId, {
          rating,
          tags,
          comment: ratingCommentText.trim() || undefined,
        })
        onRated?.({
          userRating: rating,
          ratingTags: tags,
          ratingComment: ratingCommentText.trim() || "",
        })
        resetForm()
      } catch (err) {
        setError(err?.response?.data?.detail || err?.message || "提交失败")
      } finally {
        setSubmitting(false)
      }
    },
    [taskId, submitting, hasRated, onRated, resetForm]
  )

  const selectSatisfaction = useCallback((rating) => {
    if (submitting || hasRated) return
    setSatisfaction((prev) => {
      if (prev === rating) return prev
      setSelectedTags([])
      setComment("")
      setError("")
      return rating
    })
  }, [submitting, hasRated])

  const toggleTag = useCallback((tag) => {
    setSelectedTags((prev) => {
      if (prev.includes(tag)) {
        if (tag === RATING_TAG_OTHER) setComment("")
        return prev.filter((t) => t !== tag)
      }
      return [...prev, tag]
    })
  }, [])

  useEffect(() => {
    if (needsComment) {
      otherInputRef.current?.focus()
    }
  }, [needsComment])

  const handleConfirm = useCallback(() => {
    if (!canSubmit || satisfaction == null) return
    if (satisfaction === 1) {
      finishRating(1, [])
      return
    }
    finishRating(0, selectedTags, comment)
  }, [canSubmit, satisfaction, finishRating, selectedTags, comment])

  if (!taskId) return null

  if (hasRated) {
    const label =
      userRating === 1
        ? "已反馈：满意"
        : storedTags.length
          ? `已反馈：不满意（${storedTags.join("、")}${ratingComment ? `：${ratingComment}` : ""}）`
          : ratingComment
            ? `已反馈：不满意（${ratingComment}）`
            : "已反馈：不满意"
    return (
      <div className="gn2-rating nodrag nopan" onPointerDown={(e) => e.stopPropagation()}>
        <span className="gn2-rating-done">{label}</span>
      </div>
    )
  }

  return (
    <div className="gn2-rating nodrag nopan" onPointerDown={(e) => e.stopPropagation()}>
      <div className="gn2-rating-section">
        <div className="gn2-rating-actions">
          <button
            type="button"
            className={`gn2-rating-btn${satisfaction === 1 ? " gn2-rating-btn--active" : ""}`}
            disabled={submitting}
            onClick={() => selectSatisfaction(1)}
          >
            👍 满意
          </button>
          <button
            type="button"
            className={`gn2-rating-btn${satisfaction === 0 ? " gn2-rating-btn--active" : ""}`}
            disabled={submitting}
            onClick={() => selectSatisfaction(0)}
          >
            👎 不满意
          </button>
        </div>
      </div>

      {satisfaction === 0 && (
        <div className="gn2-rating-section gn2-rating-section--reasons">
          <div className="gn2-rating-tags">
            {regularTags.map((tag) => (
              <button
                key={tag}
                type="button"
                className={`gn2-rating-tag${selectedTags.includes(tag) ? " gn2-rating-tag--active" : ""}`}
                disabled={submitting}
                onClick={() => toggleTag(tag)}
              >
                {tag}
              </button>
            ))}
            <div
              className={`gn2-rating-tag-other${needsComment ? " gn2-rating-tag-other--active" : ""}`}
            >
              <button
                type="button"
                className={`gn2-rating-tag${needsComment ? " gn2-rating-tag--active" : ""}`}
                disabled={submitting}
                onClick={() => toggleTag(RATING_TAG_OTHER)}
              >
                {RATING_TAG_OTHER}
              </button>
              {needsComment ? (
                <input
                  ref={otherInputRef}
                  type="text"
                  className="gn2-rating-other-input nodrag"
                  maxLength={200}
                  placeholder="请输入"
                  value={comment}
                  disabled={submitting}
                  onChange={(e) => setComment(e.target.value)}
                  onPointerDown={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                />
              ) : null}
            </div>
          </div>
        </div>
      )}

      {satisfaction != null && (
        <div className="gn2-rating-panel-actions">
          <button
            type="button"
            className="gn2-rating-confirm"
            disabled={submitting || !canSubmit}
            onClick={handleConfirm}
          >
            确认
          </button>
          <button
            type="button"
            className="gn2-rating-cancel"
            disabled={submitting}
            onClick={resetForm}
          >
            取消
          </button>
        </div>
      )}

      {error ? <span className="gn2-rating-error">{error}</span> : null}
    </div>
  )
}
