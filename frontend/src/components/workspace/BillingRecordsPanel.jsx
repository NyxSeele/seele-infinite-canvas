import { useMemo, useState } from "react"
import { useAuth } from "../../contexts/AuthContext"
import { showDevNotice } from "../common/ProductNoticeModal"
import { useLocale } from "../../utils/locale"
import "./BillingRecordsPanel.css"

function DocIcon() {
  return (
    <svg className="brp-tab-icon" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <rect x="3" y="2" width="8" height="10" rx="1.2" stroke="currentColor" strokeWidth="1.2" />
      <path d="M5 5.5h4M5 7.5h4M5 9.5h2.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  )
}

function ListIcon() {
  return (
    <svg className="brp-tab-icon" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M4 4.5h7M4 7h7M4 9.5h5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="2.5" cy="4.5" r="0.7" fill="currentColor" />
      <circle cx="2.5" cy="7" r="0.7" fill="currentColor" />
      <circle cx="2.5" cy="9.5" r="0.7" fill="currentColor" />
    </svg>
  )
}

function FeedbackIcon() {
  return (
    <svg className="brp-tab-icon" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path
        d="M3 3.8A1.2 1.2 0 0 1 4.2 2.6h5.6A1.2 1.2 0 0 1 11 3.8v3.4a1.2 1.2 0 0 1-1.2 1.2H7.2L4.5 11.4V8.4H4.2A1.2 1.2 0 0 1 3 7.2V3.8Z"
        stroke="currentColor"
        strokeWidth="1.15"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function EmptyTable({ icon = "doc", title, subtitle }) {
  return (
    <div className="brp-empty">
      <div className="brp-empty-icon" aria-hidden>
        {icon === "doc" ? (
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect x="12" y="8" width="24" height="32" rx="3" stroke="currentColor" strokeWidth="2" />
            <path d="M18 18h12M18 24h12M18 30h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="16" stroke="currentColor" strokeWidth="2" />
            <path d="M24 16v16M16 24h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        )}
      </div>
      <p className="brp-empty-title">{title}</p>
      <p className="brp-empty-sub">{subtitle}</p>
    </div>
  )
}

export default function BillingRecordsPanel() {
  const { user } = useAuth()
  const { t, locale } = useLocale()
  const [subTab, setSubTab] = useState("purchases")

  const purchaseColumns = useMemo(() => [
    t("billing.col.billId"),
    t("billing.col.time"),
    t("billing.col.content"),
    t("billing.col.amount"),
    t("billing.col.status"),
  ], [t])

  const pointsColumns = useMemo(() => [
    t("billing.col.txId"),
    t("billing.col.time"),
    t("billing.col.type"),
    t("billing.col.desc"),
    t("billing.col.operator"),
    t("billing.col.amount"),
    t("billing.col.status"),
    t("billing.col.balance"),
  ], [t])

  const pointsRows = useMemo(() => {
    const q = user?.quota
    if (!q) return []
    const balance = q.image_limit < 0
      ? "∞"
      : String(Math.max(0, (q.image_limit ?? 0) - (q.image_used ?? 0)))
    if (q.image_used > 0) {
      return [{
        id: `usage-${user?.id}`,
        time: new Date().toLocaleString(locale === "en" ? "en-US" : "zh-CN"),
        type: t("billing.usage.type"),
        desc: t("billing.usage.desc"),
        operator: user?.username || "—",
        amount: `-${q.image_used}`,
        status: t("billing.status.done"),
        balance,
      }]
    }
    return []
  }, [user, t, locale])

  const purchaseRows = []
  const columns = subTab === "purchases" ? purchaseColumns : pointsColumns

  return (
    <div className="brp-panel">
      <div className="brp-toolbar">
        <div className="brp-tabs">
          <button
            type="button"
            className={`brp-tab${subTab === "purchases" ? " brp-tab--active" : ""}`}
            onClick={() => setSubTab("purchases")}
          >
            <DocIcon />
            {t("billing.purchases")}
          </button>
          <button
            type="button"
            className={`brp-tab${subTab === "points" ? " brp-tab--active" : ""}`}
            onClick={() => setSubTab("points")}
          >
            <ListIcon />
            {t("billing.points")}
          </button>
        </div>
        <button type="button" className="brp-feedback" onClick={() => showDevNotice(t("billing.feedback"))}>
          <FeedbackIcon />
          {t("billing.feedback")}
        </button>
      </div>

      {subTab === "purchases" && (
        <div className="brp-headline">
          <div className="brp-headline-left">
            <h3>{t("billing.detailTitle")}</h3>
            <button type="button" className="brp-link" onClick={() => showDevNotice(t("billing.invoiceBtn"))}>
              {t("billing.invoiceHelp")}
            </button>
          </div>
          <button type="button" className="brp-invoice-btn" onClick={() => showDevNotice(t("billing.invoiceBtn"))}>
            {t("billing.invoiceBtn")}
          </button>
        </div>
      )}

      <div className="brp-table-wrap">
        <table className="brp-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {subTab === "purchases" && purchaseRows.length === 0 && (
              <tr>
                <td colSpan={columns.length}>
                  <EmptyTable
                    title={t("billing.emptyPurchaseTitle")}
                    subtitle={t("billing.emptyPurchaseSub")}
                  />
                </td>
              </tr>
            )}
            {subTab === "points" && pointsRows.length === 0 && (
              <tr>
                <td colSpan={columns.length}>
                  <EmptyTable
                    icon="points"
                    title={t("billing.emptyPointsTitle")}
                    subtitle={t("billing.emptyPointsSub")}
                  />
                </td>
              </tr>
            )}
            {subTab === "points" && pointsRows.map((row) => (
              <tr key={row.id}>
                <td className="brp-mono">{row.id}</td>
                <td>{row.time}</td>
                <td>{row.type}</td>
                <td>{row.desc}</td>
                <td>{row.operator}</td>
                <td className={row.amount.startsWith("+") ? "brp-amount--plus" : "brp-amount--minus"}>
                  {row.amount}
                </td>
                <td><span className="brp-status brp-status--done">{row.status}</span></td>
                <td>{row.balance}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
