from __future__ import annotations

import pytest

from redscribe.v2.playbooks.services import PlaybookService
from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Condition,
    ConditionOperator,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    StepKind,
    VariableDefinition,
    VariableKind,
)


@pytest.fixture
def service() -> PlaybookService:
    return PlaybookService()


@pytest.fixture
def empty_service() -> PlaybookService:
    return PlaybookService(seed=False)


@pytest.fixture
def variables() -> tuple[VariableDefinition, ...]:
    return (
        VariableDefinition(key="target", label="Target", required=True),
        VariableDefinition(key="ports", label="Ports", kind=VariableKind.LIST, default="80,443"),
        VariableDefinition(key="token", label="Token", kind=VariableKind.SECRET, required=True),
    )


@pytest.fixture
def checklist_items() -> tuple[ChecklistItem, ...]:
    return (
        ChecklistItem(id="c1", label="Confirm scope"),
        ChecklistItem(id="c2", label="Record findings", required=False),
    )


@pytest.fixture
def conditions() -> tuple[Condition, ...]:
    return (
        Condition(field="target", operator=ConditionOperator.EXISTS),
        Condition(field="ports", operator=ConditionOperator.CONTAINS, value="443"),
    )


@pytest.fixture
def steps(checklist_items: tuple[ChecklistItem, ...]) -> tuple[PlaybookStep, ...]:
    return (
        PlaybookStep(
            id="a",
            title="Enumerate",
            summary="Initial enumeration",
            command_template="nmap -sV {{ target }} -p {{ ports | join(',') }}",
            checklist=checklist_items,
            tags=("recon",),
            estimated_minutes=10,
        ),
        PlaybookStep(
            id="b",
            title="Verify",
            summary="Verify exposure",
            command_template="curl -I https://{{ target }}/",
            depends_on=("a",),
            estimated_minutes=5,
        ),
        PlaybookStep(
            id="c",
            title="Document",
            kind=StepKind.CHECKLIST,
            summary="Write the report",
            command_template="echo {{ target }} > report.txt",
            depends_on=("b",),
            optional=True,
            estimated_minutes=3,
        ),
    )


@pytest.fixture
def playbook(
    steps: tuple[PlaybookStep, ...], variables: tuple[VariableDefinition, ...]
) -> Playbook:
    return Playbook(
        id=42,
        key="fixture-playbook",
        title="Fixture Playbook",
        description="A test workflow",
        status=PlaybookStatus.ACTIVE,
        category="recon",
        tags=("network", "web"),
        version="2.3.4",
        steps=steps,
        variables=variables,
        owner="tester",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-02T00:00:00+00:00",
        references=("fixture",),
    )


@pytest.fixture
def catalog_playbook(service: PlaybookService) -> Playbook:
    return service.get_playbook(service.list_playbooks(limit=100)[0].key)
