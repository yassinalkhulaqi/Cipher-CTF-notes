import { AlertTriangle, RefreshCw } from "lucide-react";
import { BrandMark } from "./BrandMark";

interface BootScreenProps {
  error?: string | null;
  onRetry?: () => void;
}

export function BootScreen({ error = null, onRetry }: BootScreenProps) {
  if (error) {
    return (
      <div className="boot-screen boot-error">
        <div className="boot-orbit" aria-hidden="true">
          <span />
          <span />
        </div>
        <span className="boot-error-icon">
          <AlertTriangle />
        </span>
        <div className="boot-copy">
          <h1>Could not open the vault</h1>
          <p>{error}</p>
        </div>
        <button
          type="button"
          className="btn primary"
          onClick={onRetry}
          data-ripple
        >
          <RefreshCw /> Try again
        </button>
      </div>
    );
  }

  return (
    <div className="boot-screen boot-loading">
      <div className="boot-orbit" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="boot-mark">
        <BrandMark />
      </div>
      <div className="boot-copy">
        <h1>
          Red<em>Scribe</em>
        </h1>
        <p>
          Opening your vault
          <span className="boot-ellipsis" aria-hidden="true">
            <i>.</i>
            <i>.</i>
            <i>.</i>
          </span>
        </p>
      </div>
      <div className="boot-progress" aria-hidden="true">
        <span />
      </div>
      <span className="boot-hint">Local-first notes for security research</span>
    </div>
  );
}
