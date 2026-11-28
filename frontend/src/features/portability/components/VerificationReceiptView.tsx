import type { ReceiptView } from "../types";
import {
  failedChecks,
  formatTimestamp,
  receiptVerdict,
  shortDigest,
} from "../pure";

interface Props {
  receipt: ReceiptView | null;
  onArchive: () => void;
}

export function VerificationReceiptView({ receipt, onArchive }: Props) {
  return (
    <section
      className="portability-card portability-receipt"
      aria-label="Verification receipt"
    >
      <header className="portability-card__header">
        <div>
          <h3>Verification receipt</h3>
          <p className="portability-card__subtitle">
            {receiptVerdict(receipt)}
          </p>
        </div>
        <span
          className="portability-badge"
          data-tone={receipt?.ok ? "good" : "bad"}
        >
          {receipt?.status ?? "pending"}
        </span>
      </header>

      {receipt ? (
        <>
          <dl className="portability-receipt__meta">
            <div>
              <dt>Receipt</dt>
              <dd>{receipt.receiptId}</dd>
            </div>
            <div>
              <dt>Bundle</dt>
              <dd>{receipt.bundleId}</dd>
            </div>
            <div>
              <dt>Device</dt>
              <dd>{receipt.device}</dd>
            </div>
            <div>
              <dt>Verified</dt>
              <dd>{formatTimestamp(receipt.verifiedAt)}</dd>
            </div>
          </dl>

          <ul className="portability-checks">
            {receipt.checks.map((check) => (
              <li key={check.name} data-passed={check.passed}>
                <span className="portability-check__mark" aria-hidden="true">
                  {check.passed ? "PASS" : "FAIL"}
                </span>
                <span className="portability-check__name">{check.name}</span>
                <span className="portability-check__detail">
                  {check.detail}
                </span>
                <code className="portability-check__code">{check.code}</code>
              </li>
            ))}
          </ul>

          <div className="portability-receipt__digest">
            <span>Digest</span>
            <code>{shortDigest(receipt.digest, 32)}</code>
          </div>

          {failedChecks(receipt).length > 0 && (
            <p className="portability-alert" role="alert">
              Do not import this bundle until the failed checks are resolved.
            </p>
          )}

          {receipt.rendered && (
            <details className="portability-receipt__raw">
              <summary>Archived receipt text</summary>
              <pre>{receipt.rendered}</pre>
            </details>
          )}
        </>
      ) : (
        <p className="portability-empty">
          Verify a bundle to generate its receipt.
        </p>
      )}

      <footer className="portability-card__footer">
        <button
          type="button"
          className="portability-button"
          onClick={onArchive}
          disabled={!receipt?.ok}
        >
          Archive receipt
        </button>
      </footer>
    </section>
  );
}
