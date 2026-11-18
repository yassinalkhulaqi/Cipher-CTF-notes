import { Banner } from "../../ui/Banner";
import { EmptyState } from "../../ui/EmptyState";
import { cx } from "../../lib/ux";
import {
  coverageGaps,
  coverageProgress,
  coverageTone,
  engagementRisk,
  formatScore,
  humanize,
  sortedCoverage,
} from "./logic";
import type { DashboardPayload, Tone } from "./types";

function bannerTone(tone: Tone): "info" | "success" | "warning" | "danger" {
  if (tone === "success") return "success";
  if (tone === "warning" || tone === "accent") return "warning";
  if (tone === "danger") return "danger";
  return "info";
}

export function DashboardWidgets({
  dashboard,
}: {
  dashboard: DashboardPayload;
}) {
  const { rollup, coverage, duplicates, recent_activity } = dashboard;
  const gaps = coverageGaps(coverage);

  return (
    <section className="eng-dashboard" aria-label="Engagement dashboard">
      <div className="eng-dashboard__head">
        <div>
          <h2 className="eng-panel__title">{dashboard.engagement.name}</h2>
          <p className="eng-panel__subtitle">
            {humanize(dashboard.engagement.kind)} ·{" "}
            {humanize(dashboard.engagement.status)} · risk {rollup.risk_band}
          </p>
        </div>
        <Banner
          tone={bannerTone(engagementRisk(rollup))}
          title={`Risk ${formatScore(rollup.risk_score)}`}
        >
          Coverage {coverageProgress(coverage)}% · {duplicates.total} duplicate
          candidates
        </Banner>
      </div>
      <div className="eng-card-grid">
        {dashboard.cards.map((card) => (
          <article
            key={card.label}
            className={cx("eng-card", `eng-card--${card.tone}`)}
          >
            <span className="eng-card__label">{card.label}</span>
            <strong className="eng-card__value">{card.value}</strong>
          </article>
        ))}
      </div>
      <div className="eng-dashboard__columns">
        <article className="eng-panel eng-subpanel">
          <h3 className="eng-panel__title">Severity matrix</h3>
          <div className="eng-matrix">
            {rollup.severity.map((row) => (
              <div key={row.severity} className="eng-matrix__row">
                <span
                  className={cx(
                    "eng-pill",
                    `eng-pill--${row.severity === "info" ? "info" : row.severity === "low" ? "neutral" : row.severity === "medium" ? "warning" : "danger"}`,
                  )}
                >
                  {humanize(row.severity)}
                </span>
                <strong>{row.total}</strong>
                <span>{row.open} open</span>
                <span>{row.verified} verified</span>
                <span>{row.closed} closed</span>
              </div>
            ))}
          </div>
        </article>
        <article className="eng-panel eng-subpanel">
          <h3 className="eng-panel__title">Coverage</h3>
          <div className="eng-coverage-list">
            {sortedCoverage(coverage).map((item) => (
              <div key={item.target_id} className="eng-coverage-row">
                <span>{item.target_name}</span>
                <div
                  className="eng-progress"
                  aria-label={`Coverage ${Math.round(item.score * 100)}%`}
                >
                  <span
                    className={cx(
                      "eng-progress__bar",
                      `eng-progress__bar--${coverageTone(item.level)}`,
                    )}
                    style={{
                      width: `${Math.max(0, Math.min(100, item.score * 100))}%`,
                    }}
                  />
                </div>
                <strong>{Math.round(item.score * 100)}%</strong>
              </div>
            ))}
          </div>
          {gaps.length ? (
            <ul className="eng-gap-list">
              {gaps.map((gap) => (
                <li key={gap.gap}>
                  {humanize(gap.gap)} <span>×{gap.count}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </article>
      </div>
      <div className="eng-dashboard__columns">
        <article className="eng-panel eng-subpanel">
          <h3 className="eng-panel__title">Duplicate clusters</h3>
          {duplicates.groups.length === 0 ? (
            <EmptyState
              title="No duplicate groups"
              description="Findings are currently distinct."
            />
          ) : (
            <ul className="eng-cluster-list">
              {duplicates.groups.map((group, index) => (
                <li key={`${group.ids.join("-")}-${index}`}>
                  <strong>{group.titles[0]}</strong>
                  <span>
                    {group.ids.length} findings · {humanize(group.severity)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </article>
        <article className="eng-panel eng-subpanel">
          <h3 className="eng-panel__title">Recent activity</h3>
          {recent_activity.length === 0 ? (
            <EmptyState
              title="No activity yet"
              description="Lifecycle changes will appear here."
            />
          ) : (
            <ul className="eng-activity-list">
              {recent_activity.map((activity) => (
                <li key={activity.id}>
                  <span className="eng-activity-list__meta">
                    {activity.created_at.slice(0, 16)}
                  </span>
                  <strong>{activity.summary || activity.action}</strong>
                  <span>{activity.actor || "system"}</span>
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>
    </section>
  );
}
