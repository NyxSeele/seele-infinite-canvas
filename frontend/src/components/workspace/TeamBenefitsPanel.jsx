import { useMemo } from "react"
import { useAuth } from "../../contexts/AuthContext"
import { useTeamStore } from "../../stores/teamStore"
import { showDevNotice } from "../common/ProductNoticeModal"
import "./TeamPanels.css"

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <rect x="5" y="5" width="7" height="7" rx="1.2" stroke="currentColor" strokeWidth="1.2" />
      <path d="M3 9V3.8A.8.8 0 0 1 3.8 3H9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

export default function TeamBenefitsPanel() {
  const { user } = useAuth()
  const activeTeamId = useTeamStore((s) => s.activeTeamId)
  const allTeams = useTeamStore((s) => s.allTeams)

  const team = useMemo(
    () => (activeTeamId ? allTeams.find((t) => t.id === activeTeamId) : null),
    [activeTeamId, allTeams]
  )

  const q = user?.quota
  const balance = q
    ? (q.image_limit < 0 ? "∞" : String(Math.max(0, (q.image_limit ?? 0) - (q.image_used ?? 0))))
    : "0"
  const isUnlimited = q?.image_limit < 0

  const handleCopyId = async () => {
    if (!team?.id) return
    try {
      await navigator.clipboard.writeText(team.id)
    } catch {
      window.prompt("团队 ID", team.id)
    }
  }

  if (!activeTeamId || !team) {
    return (
      <div className="tp-empty">
        <p>当前为个人空间，切换到团队后可查看团队权益。</p>
      </div>
    )
  }

  return (
    <div className="tp-benefits">
      <section className="tp-card">
        <div className="tp-card-main">
          <h3>积分余额：{balance}</h3>
          <p>汇率 $1 = 100 积分 · 升级套餐可获得更优汇率</p>
        </div>
        <button type="button" className="tp-card-action" onClick={() => showDevNotice("充值")}>
          充值
        </button>
      </section>

      <section className="tp-card">
        <div className="tp-card-main">
          <h3>免费版</h3>
          <p>升级以解锁完整功能与更高并发</p>
        </div>
        <button type="button" className="tp-card-action" onClick={() => showDevNotice("升级套餐")}>
          升级
        </button>
      </section>

      <section className="tp-card">
        <div className="tp-card-main">
          <h3>你的团队：{team.name}</h3>
          <p className="tp-mono">团队 ID：{team.id}</p>
        </div>
        <button type="button" className="tp-card-action tp-card-action--icon" onClick={handleCopyId} title="复制团队 ID">
          <CopyIcon />
          复制团队 ID
        </button>
      </section>

      <section className="tp-quota-block">
        <h3>配额信息</h3>
        <div className="tp-quota-inner">
          {isUnlimited ? (
            <>
              <div className="tp-quota-head">
                <span>无额度限制</span>
                <span className="tp-infinity">∞</span>
              </div>
              <div className="tp-quota-bar">
                <div className="tp-quota-fill" style={{ width: "100%" }} />
              </div>
            </>
          ) : (
            <>
              <div className="tp-quota-head">
                <span>图片生成</span>
                <span>{q?.image_used ?? 0} / {q?.image_limit ?? 0}</span>
              </div>
              <div className="tp-quota-bar">
                <div
                  className="tp-quota-fill"
                  style={{
                    width: `${Math.min(100, ((q?.image_used ?? 0) / Math.max(1, q?.image_limit ?? 1)) * 100)}%`,
                  }}
                />
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  )
}
