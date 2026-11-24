"""Release-polish content catalogue shared by docs and API routes.

These records describe the onboarding flow, first-run copy, design-system
showcase, icon/label conventions, animation audit, and responsive checklist
rendered by the React feature. Keeping them as data in one place makes the
documentation and the API manifest agree with the UI.
"""

from __future__ import annotations

from redscribe.v3.release.models import (
    AnimationAudit,
    EmptyStateSpec,
    OnboardingSpec,
    PolishCheck,
    ShowcaseEntry,
)

ONBOARDING_SPECS: tuple[OnboardingSpec, ...] = (
    OnboardingSpec(
        "welcome",
        "Welcome to RedScribe",
        "A local-first notebook for captures, findings, evidence, and reports.",
        "welcome-card",
        "Nothing leaves this device.",
    ),
    OnboardingSpec(
        "first-capture",
        "Record your first capture",
        "Create a note to anchor the engagement timeline.",
        "quick-capture-button",
        "Press N from anywhere to open quick capture.",
    ),
    OnboardingSpec(
        "confirm-local",
        "Confirm local storage",
        "Your vault is stored on disk and never sent to a remote service.",
        "storage-status-badge",
        "Offline-only is enabled by default.",
    ),
    OnboardingSpec(
        "review-basics",
        "Review the design system",
        "See panels, metrics, kind colors, density, and motion tokens.",
        "showcase-panel",
        "Keyboard focus use is visible on every control.",
    ),
    OnboardingSpec(
        "start-engagement",
        "Start your engagement",
        "Add a target and move your first note into a finding.",
        "engagement-launch-button",
        "You can revisit these steps from Help.",
        required=False,
    ),
)

EMPTY_STATE_SPECS: tuple[EmptyStateSpec, ...] = (
    EmptyStateSpec(
        "notes",
        "No captures yet",
        "Quick capture creates the first note in this vault.",
        "Create a note",
        "capture.create",
        "file-text",
    ),
    EmptyStateSpec(
        "findings",
        "No findings yet",
        "Promote a note into a finding to start the report.",
        "New finding",
        "findings.create",
        "alert",
    ),
    EmptyStateSpec(
        "evidence",
        "No evidence attached",
        "Attach a file or hash to preserve the chain of custody.",
        "Attach evidence",
        "evidence.ingest",
        "paperclip",
    ),
    EmptyStateSpec(
        "report",
        "Report is empty",
        "Findings you compose are collected here automatically.",
        "Compose report",
        "reports.compose",
        "book",
    ),
    EmptyStateSpec(
        "activity",
        "No activity recorded",
        "Actions appear here as correlated local events.",
        "Open capture",
        "capture.create",
        "activity",
    ),
)

SHOWCASE_ENTRIES: tuple[ShowcaseEntry, ...] = (
    ShowcaseEntry("--v3-surface", "Surface", "note", "panel"),
    ShowcaseEntry("--v3-surface-raised", "Raised surface", "folder", "stat"),
    ShowcaseEntry("--v3-text", "Primary text", "section", "Aa"),
    ShowcaseEntry("--v3-text-muted", "Muted text", "section", "Aa"),
    ShowcaseEntry("--v3-focus", "Focus ring", "target", "ring"),
    ShowcaseEntry("--v3-good", "Positive tone", "evidence", "good"),
    ShowcaseEntry("--v3-warn", "Warning tone", "run", "warn"),
    ShowcaseEntry("--v3-bad", "Negative tone", "finding", "bad"),
    ShowcaseEntry("--v3-kind-target", "Target color", "target", "crosshair"),
    ShowcaseEntry("--v3-kind-evidence", "Evidence color", "evidence", "paperclip"),
    ShowcaseEntry("--v3-kind-finding", "Finding color", "finding", "alert"),
    ShowcaseEntry("--v3-kind-report", "Report color", "report", "book"),
)

ICON_LABELS: tuple[tuple[str, str, str], ...] = (
    ("file-text", "Note", "note"),
    ("folder", "Folder", "folder"),
    ("crosshair", "Target", "target"),
    ("alert", "Finding", "finding"),
    ("paperclip", "Evidence", "evidence"),
    ("list", "Playbook", "playbook"),
    ("play", "Run", "run"),
    ("book", "Report", "report"),
    ("layout", "Section", "section"),
    ("activity", "Activity", "activity"),
    ("puzzle", "Extension", "extension"),
    ("terminal", "Snippet", "snippet"),
)

ANIMATION_AUDITS: tuple[AnimationAudit, ...] = (
    AnimationAudit(
        "panel-enter",
        "opacity",
        "--v3-motion-normal",
        True,
        "Fades content without shifting layout.",
    ),
    AnimationAudit(
        "stat-count",
        "font-variant-numeric",
        "--v3-motion-fast",
        True,
        "Tabular values avoid jitter under reduced motion.",
    ),
    AnimationAudit(
        "toast-stack",
        "transform",
        "--v3-motion-normal",
        True,
        "Slides are disabled with prefers-reduced-motion.",
    ),
    AnimationAudit(
        "aurora-background",
        "filter",
        "--v3-motion-slow",
        True,
        "Static gradient is used when motion is reduced.",
    ),
    AnimationAudit(
        "skeleton-shimmer",
        "background-position",
        "--v3-motion-slow",
        False,
        "Fallback to a solid placeholder is required.",
    ),
)

POLISH_CHECKS: tuple[PolishCheck, ...] = (
    PolishCheck(
        "onboarding.steps",
        "Onboarding",
        "Ordered first-run steps",
        "Five guided steps with a skippable final action.",
    ),
    PolishCheck(
        "onboarding.progress",
        "Onboarding",
        "Progress is visible",
        "Completed and required counts are shown.",
    ),
    PolishCheck(
        "empty.notes",
        "Empty states",
        "Notes empty state",
        "Named surface, action label, and route are defined.",
    ),
    PolishCheck(
        "empty.findings", "Empty states", "Findings empty state", "Promotes a note into a finding."
    ),
    PolishCheck(
        "empty.evidence", "Empty states", "Evidence empty state", "Explains hashing and custody."
    ),
    PolishCheck(
        "showcase.density",
        "Design system",
        "Density modes",
        "Compact and comfortable are both demonstrated.",
    ),
    PolishCheck(
        "showcase.kinds",
        "Design system",
        "Kind colors",
        "All entity kinds resolve to a semantic token.",
    ),
    PolishCheck(
        "icons.labels",
        "Iconography",
        "Icons carry labels",
        "Every icon is paired with a stable kind label.",
    ),
    PolishCheck(
        "labels.consistency",
        "Iconography",
        "Labels are consistent",
        "Singular and plural labels match the registry.",
    ),
    PolishCheck(
        "motion.reduced",
        "Animation",
        "Reduced-motion path",
        "Content stays usable with transitions removed.",
    ),
    PolishCheck(
        "motion.tokens", "Animation", "Token usage", "Durations use v3 motion tokens only."
    ),
    PolishCheck(
        "responsive.breakpoints",
        "Responsive",
        "Breakpoint coverage",
        "Narrow, medium, and wide layouts are checked.",
    ),
    PolishCheck(
        "responsive.focus",
        "Responsive",
        "Focus order",
        "Keyboard order follows visual order at each size.",
    ),
    PolishCheck(
        "responsive.touch",
        "Responsive",
        "Touch targets",
        "Controls remain reachable at compact density.",
    ),
)

BREAKPOINTS: tuple[tuple[str, int], ...] = (
    ("narrow", 480),
    ("medium", 768),
    ("wide", 1280),
)


def onboarding_payload() -> tuple[dict[str, object], ...]:
    """Return onboarding steps as JSON-safe dictionaries."""
    return tuple(step.as_dict() for step in ONBOARDING_SPECS)


def empty_state_payload() -> tuple[dict[str, object], ...]:
    """Return empty-state specs as JSON-safe dictionaries."""
    return tuple(spec.as_dict() for spec in EMPTY_STATE_SPECS)


def showcase_payload() -> tuple[dict[str, object], ...]:
    """Return showcase rows as JSON-safe dictionaries."""
    return tuple(entry.as_dict() for entry in SHOWCASE_ENTRIES)


def polish_payload() -> dict[str, object]:
    """Return polish, animation, icon, and breakpoint data."""
    return {
        "checks": [check.as_dict() for check in POLISH_CHECKS],
        "animations": [audit.as_dict() for audit in ANIMATION_AUDITS],
        "icons": [
            {"icon": icon, "label": label, "kind": kind} for icon, label, kind in ICON_LABELS
        ],
        "breakpoints": [{"name": name, "width": width} for name, width in BREAKPOINTS],
    }
