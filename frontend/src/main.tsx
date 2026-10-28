import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { MotionProvider } from "./motion/MotionProvider";
import "./styles/index.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("RedScribe root element is missing");
}

createRoot(container).render(
  <StrictMode>
    <ErrorBoundary>
      <MotionProvider>
        <App />
      </MotionProvider>
    </ErrorBoundary>
  </StrictMode>,
);
