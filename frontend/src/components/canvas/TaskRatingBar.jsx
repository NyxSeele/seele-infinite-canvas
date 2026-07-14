import { useCallback, useEffect, useMemo, useState } from "react"
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
  defaultExpanded = false,
  onRated,
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [selectedTags, setSelectedTags] = useState([])
  const [comment, setComment] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  const tagOptions = useMemo(() => ratingTagsForTaskType(taskType), [taskType])
  const hasRated = userRating === 0 || userRating === 1
  const storedTags = Array.isArray(ratingTags) ? ratingTags : []
  const needsComment = selectedTags.includes(RATING_TAG_OTHER)
  const canSubmitNegative = selectedTags.length > 0 && (!needsComment || comment.trim().length > 0)

  useEffect(() => {
    if (defaultExpanded && !hasRated) {
      setExpanded(true)
    }
  }, [defaultExpanded, hasRated])

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
        setExpanded(false)
        setSelectedTags([])
        setComment("")
      } catch (err) {
        setError(err?.response?.data?.detail || err?.message || "提交失败")
      } finally {
        setSubmitting(false)
      }
    },
    [taskId, submitting, hasRated, onRated]
  )

  const handlePositive = useCallback(() => {
    finishRating(1, [])
  }, [finishRating])

  const handleNegativeOpen = useCallback(() => {
    if (submitting || hasRated) return
    setExpanded(true)
    setSelectedTags([])
    setComment("")
    setError("")
  }, [submitting, hasRated])

  const toggleTag = useCallback((tag) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    )
  }, [])

  const handleNegativeConfirm = useCallback(() => {
    if (!canSubmitNegative) return
    finishRating(0, selectedTags, comment)
  }, [finishRating, selectedTags, comment, canSubmitNegative])

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
      <div className="gn2-rating-actions">
        <button
          type="button"
          className="gn2-rating-btn"
          disabled={submitting}
          onClick={handlePositive}
        >
          👍 满意
        </button>
        <button
          type="button"
          className="gn2-rating-btn"
          disabled={submitting}
          onClick={handleNegativeOpen}
        >
          👎 不满意
        </button>
      </div>

      {expanded && (
        <div className="gn2-rating-panel">
          <div className="gn2-rating-tags">
            {tagOptions.map((tag) => (
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
          </div>
          {needsComment ? (
            <textarea
              className="gn2-rating-comment"
              rows={2}
              maxLength={200}
              placeholder="请简要说明问题（必填，最多200字）"
              value={comment}
              disabled={submitting}
              onChange={(e) => setComment(e.target.value)}
            />
          ) : null}
          <div className="gn2-rating-panel-actions">
            <button
              type="button"
              className="gn2-rating-confirm"
              disabled={submitting || !canSubmitNegative}
              onClick={handleNegativeConfirm}
            >
              确认
            </button>
            <button
              type="button"
              className="gn2-rating-cancel"
              disabled={submitting}
              onClick={() => {
                setExpanded(false)
                setSelectedTags([])
                setComment("")
              }}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {error ? <span className="gn2-rating-error">{error}</span> : null}
    </div>
  )
}
