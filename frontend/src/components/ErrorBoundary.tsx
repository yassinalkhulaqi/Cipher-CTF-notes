import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { BrandMark } from "./BrandMark";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[redscribe] render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="boot-screen error">
          <BrandMark />
          <span className="boot-error-icon">
            <AlertTriangle />
          </span>
          <div className="boot-copy">
            <h1>Something went wrong</h1>
            <p>{this.state.error.message}</p>
          </div>
          <button
            type="button"
            className="btn primary"
            onClick={() => window.location.reload()}
          >
            <RefreshCw /> Reload RedScribe
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
