"""Shared fixtures for V3 automation tests."""

from __future__ import annotations

from typing import Any

from redscribe.v3.automation.parsing import parse_playbook
from redscribe.v3.automation.types import (
    PlaybookDefinition,
    StepDefinition,
    VariableDefinition,
    VariableKind,
)


def playbook_payload(**overrides: Any) -> dict[str, Any]:
    """Return a small, valid playbook API payload."""
    payload: dict[str, Any] = {
        "id": "smoke",
        "title": "Smoke playbook",
        "variables": [
            {"key": "target", "kind": "entity_ref", "required": True},
            {"key": "severity", "kind": "choice", "choices": ["low", "high"], "default": "high"},
        ],
        "steps": [
            {
                "id": "note",
                "title": "Capture note",
                "kind": "create_note",
                "inputs": {"title": "Note for {{ vars.target }}", "body": "body"},
            },
            {
                "id": "finding",
                "title": "Capture finding",
                "kind": "create_finding",
                "depends_on": ["note"],
                "inputs": {"title": "Finding {{ severity }}", "severity": "{{ severity }}"},
            },
            {
                "id": "evidence",
                "title": "Attach evidence",
                "kind": "attach_evidence",
                "depends_on": ["finding"],
                "inputs": {
                    "evidence_ref": "evidence:capture-1",
                    "target_ref": "{{ steps.finding.ref }}",
                },
            },
            {
                "id": "event",
                "title": "Emit event",
                "kind": "emit_event",
                "depends_on": ["evidence"],
                "inputs": {"event_kind": "automation.smoke", "message": "complete"},
            },
        ],
    }
    payload.update(overrides)
    return payload


def sample_playbook(**overrides: Any) -> PlaybookDefinition:
    """Parse the shared fixture into a domain object."""
    return parse_playbook(playbook_payload(**overrides))


def linear_steps(count: int) -> tuple[StepDefinition, ...]:
    """Build a linear chain of note steps for scaling tests."""
    result: list[StepDefinition] = []
    for index in range(count):
        dependencies = (f"s{index - 1}",) if index else ()
        result.append(
            StepDefinition(
                id=f"s{index}",
                title=f"Step {index}",
                depends_on=dependencies,
                inputs={"title": f"Note {index}"},
            )
        )
    return tuple(result)


def typed_variables() -> tuple[VariableDefinition, ...]:
    """Build a representative set of typed variable definitions."""
    return (
        VariableDefinition(key="target", required=True),
        VariableDefinition(key="count", kind=VariableKind.NUMBER, default=1),
    )
