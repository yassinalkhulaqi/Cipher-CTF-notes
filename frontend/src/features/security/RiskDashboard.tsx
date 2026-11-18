import type { SecurityDashboard } from "./types";
import {
  dashboardAlerts,
  dashboardStatus,
  formatCount,
  formatScore,
  riskGaugePercent,
  riskHeadline,
  safetyReasonsText,
  severityLabel,
  topRiskFactors,
} from "./helpers";

interface Props {
  dashboard: SecurityDashboard | null;
  loading?: boolean;
  onRefresh?: () => void;
}

export function RiskDashboard({
  dashboard,
  loading = false,
  onRefresh,
}: Props) {
  const alerts = dashboardAlerts(dashboard);
  const status = dashboardStatus(dashboard);
  const factors = topRiskFactors(dashboard?.risk, 5);

  return (
    <section
      className="security-panel risk-dashboard"
      aria-label="Security risk dashboard"
    >
      <header className="security-panel__header">
        <div>
          <h2>Risk Dashboard</h2>
          <p className="security-panel__subtitle">
            {riskHeadline(dashboard?.risk)}
          </p>
        </div>
        <div className="button-group">
          <span className={`badge badge--${status.tone}`}>{status.label}</span>
          <button
            type="button"
            className="button"
            onClick={onRefresh}
            disabled={loading || !onRefresh}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {!dashboard ? (
        <p className="empty-state">No dashboard data available.</p>
      ) : (
        <>
          <div className="security-stats" aria-label="Risk metrics">
            <div className="stat-card">
              <span className="stat-card__label">Risk score</span>
              <strong>{formatScore(dashboard.risk.score.score)}/10</strong>
            </div>
            <div className="stat-card">
              <span className="stat-card__label">Confidence</span>
              <strong>
                {Math.round(dashboard.risk.score.confidence * 100)}%
              </strong>
            </div>
            <div className="stat-card">
              <span className="stat-card__label">Secret findings</span>
              <strong>{dashboard.secrets.count}</strong>
            </div>
            <div className="stat-card">
              <span className="stat-card__label">Audit findings</span>
              <strong>{dashboard.audit.findings.length}</strong>
            </div>
          </div>

          <div className="risk-meter" aria-label="Risk meter">
            <div className="risk-meter__bar">
              <div
                className="risk-meter__fill"
                style={{
                  width: `${riskGaugePercent(dashboard.risk.score.score)}%`,
                }}
              />
            </div>
            <div className="risk-meter__labels">
              <span>Low</span>
              <span>Medium</span>
              <span>High</span>
              <span>Critical</span>
            </div>
          </div>

          <div className="security-columns">
            <div className="security-column">
              <h3>Alerts</h3>
              {alerts.length === 0 ? (
                <p className="empty-state">No active alerts.</p>
              ) : (
                <ul className="alert-list">
                  {alerts.map((alert) => (
                    <li key={alert} className="alert-item">
                      {alert}
                    </li>
                  ))}
                </ul>
              )}

              <h3>Top risk factors</h3>
              {factors.length === 0 ? (
                <p className="empty-state">No contributing factors.</p>
              ) : (
                <ul className="factor-list">
                  {factors.map((factor) => (
                    <li key={factor.name} className="factor-item">
                      <div className="factor-item__header">
                        <strong>{factor.name}</strong>
                        <span className={`badge badge--${factor.severity}`}>
                          {severityLabel(factor.severity)}
                        </span>
                      </div>
                      <div className="factor-item__meta">
                        <span>Weighted {factor.weighted_score.toFixed(2)}</span>
                        <span>Weight {factor.weight.toFixed(2)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="security-column">
              <h3>Safe action checks</h3>
              <div className="safety-section">
                <h4>
                  URLs ({formatCount(dashboard.urls.length, "checked URL")})
                </h4>
                {dashboard.urls.length === 0 ? (
                  <p className="empty-state">No URLs analyzed.</p>
                ) : (
                  <ul className="safety-list">
                    {dashboard.urls.map((item) => (
                      <li
                        key={item.url}
                        className={`safety-item safety-item--${item.safe ? "safe" : "unsafe"}`}
                      >
                        <strong>{item.safe ? "Safe" : "Unsafe"}</strong>
                        <code>{item.url}</code>
                        <small>{safetyReasonsText(item.reasons)}</small>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="safety-section">
                <h4>
                  Commands (
                  {formatCount(dashboard.commands.length, "checked command")})
                </h4>
                {dashboard.commands.length === 0 ? (
                  <p className="empty-state">No commands analyzed.</p>
                ) : (
                  <ul className="safety-list">
                    {dashboard.commands.map((item) => (
                      <li
                        key={item.command}
                        className={`safety-item safety-item--${item.safe ? "safe" : "unsafe"}`}
                      >
                        <strong>{item.safe ? "Safe" : "Risky"}</strong>
                        <code>{item.command}</code>
                        <small>{safetyReasonsText(item.reasons)}</small>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>

          <div className="recommendations">
            <h3>Recommendations</h3>
            {dashboard.risk.recommendations.length === 0 ? (
              <p className="empty-state">No recommendations.</p>
            ) : (
              <ul>
                {dashboard.risk.recommendations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}
