"""Progress tracking and reporting for sync operations."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from redscribe.v2.sync.errors import ProgressError
from redscribe.v2.sync.models import ProgressReport

ProgressCallback = Callable[[ProgressReport], None]


@dataclass(slots=True)
class ProgressTracker:
    """Collect and emit progress reports for a multi-stage operation."""

    operation: str
    callback: ProgressCallback | None = None
    reports: list[ProgressReport] = field(default_factory=list)

    def report(
        self,
        stage: str,
        current: int,
        total: int,
        message: str = "",
        *,
        done: bool = False,
    ) -> ProgressReport:
        if total < 0 or current < 0:
            raise ProgressError("Progress values cannot be negative")
        if total and current > total:
            current = total
        percent = 100.0 if done and total == 0 else 0.0
        if total > 0:
            percent = round((current / total) * 100, 2)
        payload = ProgressReport(
            operation=self.operation,
            stage=stage,
            current=current,
            total=total,
            message=message,
            percent=percent,
            done=done,
        )
        self.reports.append(payload)
        if self.callback is not None:
            self.callback(payload)
        return payload

    @contextmanager
    def stage(
        self, stage: str, total: int, message: str = ""
    ) -> Iterator[Callable[[int, str], None]]:
        self.report(stage, 0, total, message)

        def advance(current: int, detail: str = "") -> None:
            self.report(stage, current, total, detail or message)

        try:
            yield advance
        finally:
            final_current = total
            last = self.reports[-1] if self.reports else None
            if last is not None and last.stage == stage:
                final_current = max(last.current, total)
            self.report(stage, final_current, total, message, done=True)

    def complete(self, message: str = "completed") -> ProgressReport:
        return self.report("complete", 1, 1, message, done=True)

    def failed(self, message: str) -> ProgressReport:
        return self.report("failed", 1, 1, message, done=True)

    def as_dicts(self) -> list[dict[str, object]]:
        return [item.as_dict() for item in self.reports]

    def latest(self) -> ProgressReport | None:
        return self.reports[-1] if self.reports else None


def progress_summary(reports: list[ProgressReport]) -> dict[str, object]:
    """Summarize a sequence of progress reports."""
    if not reports:
        return {"stages": 0, "done": False, "percent": 0.0}
    latest = reports[-1]
    stages = []
    for report in reports:
        if report.stage not in stages:
            stages.append(report.stage)
    return {
        "stages": len(stages),
        "stage_names": stages,
        "done": latest.done,
        "percent": latest.percent,
        "latest": latest.as_dict(),
    }
