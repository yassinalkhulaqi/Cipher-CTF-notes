import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";
import { persist } from "../../store/useAppStore";

export function OnboardingTour() {
  const toast = useUiStore((state) => state.toast);
  const boot = useAppStore((state) => state.boot);

  const [show, setShow] = useState(true);

  useEffect(() => {
    if (boot?.onboarding_seen === "1") {
      setShow(false);
    }
  }, [boot?.onboarding_seen]);

  const markCompleted = () => {
    persist({ onboarding_seen: "1" });
    setShow(false);
    toast("Onboarding tour dismissed", "default");
  };

  if (!show || !boot) return null;

  const steps = [
    {
      title: "Welcome to RedScribe",
      body:
        "Your local-first notebook for CTFs, pentests, and security research. No accounts. No telemetry. Just one SQLite vault.",
    },
    {
      title: "Tree & Notes",
      body:
        "Use Ctrl+Shift+N for new folder, Ctrl+Shift+P to pin, F2 to edit properties. Drag to reorder.",
    },
    {
      title: "Editor & Preview",
      body:
        "Ctrl+E cycles editor/split/preview. Ctrl+Shift+F searches, Ctrl+Shift+S snippets. Live Markdown preview with syntax highlighting.",
    },
    {
      title: "Search & Flags",
      body:
        "Ctrl+P fuzzy jump. Flags with format validation. Tags, targets, difficulty, and status chips on every note.",
    },
  ];

  return (
    <Modal
      title="RedScribe Onboarding"
      subtitle="Getting started with your vault"
      icon={<X />}
      className="onboarding-modal"
      bodyClassName="onboarding-body"
      label="Onboarding"
    >
      <div className="onboarding-container">
        <div className="onboarding-step">
          <h2>{steps[0].title}</h2>
          <p>{steps[0].body}</p>
          <div className="onboarding-focus-indicator" />
        </div>
        <button
          type="button"
          className="onboarding-skip"
          onClick={markCompleted}
          aria-label="Skip onboarding"
        >
          <X /> Skip
        </button>
      </div>
    </Modal>
  );
}