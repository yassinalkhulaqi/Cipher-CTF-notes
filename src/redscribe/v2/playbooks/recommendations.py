"""Local recommendation scoring for playbooks, snippets, and templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v2.playbooks.snippets import SnippetLibrary
from redscribe.v2.playbooks.templates import TemplateEngine
from redscribe.v2.playbooks.types import (
    Playbook,
    Recommendation,
    TemplateRecord,
)

DEFAULT_LIMIT = 5


@dataclass(frozen=True, slots=True)
class RecommendationContext:
    """Signals used to rank recommendations."""

    query: str = ""
    tags: tuple[str, ...] = ()
    target: str = ""
    category: str = ""
    recent_keys: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "tags": list(self.tags),
            "target": self.target,
            "category": self.category,
            "recent_keys": list(self.recent_keys),
        }


class RecommendationEngine:
    """Deterministic, explainable ranking over local catalogs."""

    def __init__(
        self,
        playbooks: tuple[Playbook, ...] = (),
        snippets: SnippetLibrary | None = None,
        templates: TemplateEngine | None = None,
    ) -> None:
        self.playbooks = playbooks
        self.snippets = snippets if snippets is not None else SnippetLibrary()
        self.templates = templates if templates is not None else TemplateEngine()

    def recommend_playbooks(
        self, context: RecommendationContext, *, limit: int = DEFAULT_LIMIT
    ) -> list[Recommendation]:
        """Rank playbooks for the supplied context."""
        results = [
            Recommendation(
                kind="playbook",
                key=playbook.key,
                score=self.score_playbook(playbook, context),
                reason=self.explain_playbook(playbook, context),
                title=playbook.title,
                meta={
                    "category": playbook.category,
                    "steps": len(playbook.steps),
                    "status": playbook.status.value,
                    "version": playbook.version,
                },
            )
            for playbook in self.playbooks
        ]
        return self._rank(results, limit)

    def recommend_snippets(
        self, context: RecommendationContext, *, limit: int = DEFAULT_LIMIT
    ) -> list[Recommendation]:
        """Rank snippets for the supplied context."""
        results: list[Recommendation] = []
        for record in self.snippets.records:
            score = self._score_terms(
                query=context.query,
                tags=context.tags,
                terms=(
                    f"{record.title} {record.description} {' '.join(record.tags)} {record.command}"
                ),
                record_tags=record.tags,
                usage=record.usage_count,
                category="",
                wanted_category=context.category,
                recent=record.key in context.recent_keys,
            )
            if score <= 0:
                continue
            results.append(
                Recommendation(
                    kind="snippet",
                    key=record.key,
                    score=score,
                    reason=self._reason(record.tags, context, usage=record.usage_count),
                    title=record.title,
                    meta={"library": record.library, "usage_count": record.usage_count},
                )
            )
        return self._rank(results, limit)

    def recommend_templates(
        self, context: RecommendationContext, *, limit: int = DEFAULT_LIMIT
    ) -> list[Recommendation]:
        """Rank templates for the supplied context."""
        results: list[Recommendation] = []
        records: list[TemplateRecord] = list(self.templates.records)
        for record in records:
            score = self._score_terms(
                query=context.query,
                tags=context.tags,
                terms=f"{record.key} {record.name} {record.description} {' '.join(record.tags)}",
                record_tags=record.tags,
                usage=0,
                category=record.category,
                wanted_category=context.category,
                recent=record.key in context.recent_keys,
            )
            if score <= 0:
                continue
            results.append(
                Recommendation(
                    kind="template",
                    key=record.key,
                    score=score,
                    reason=self._reason(record.tags, context),
                    title=record.name,
                    meta={"category": record.category, "version": record.version},
                )
            )
        return self._rank(results, limit)

    def score_playbook(self, playbook: Playbook, context: RecommendationContext) -> float:
        """Return a numeric relevance score for one playbook."""
        terms = " ".join(
            (
                playbook.key,
                playbook.title,
                playbook.description,
                playbook.category,
                " ".join(playbook.tags),
                " ".join(step.title for step in playbook.steps),
            )
        )
        return self._score_terms(
            query=context.query,
            tags=context.tags,
            terms=terms,
            record_tags=tuple(playbook.tags),
            usage=0,
            category=playbook.category,
            wanted_category=context.category,
            recent=playbook.key in context.recent_keys,
            status=playbook.status.value,
        )

    def explain_playbook(self, playbook: Playbook, context: RecommendationContext) -> str:
        """Explain why a playbook was recommended."""
        reasons: list[str] = []
        tags = {tag.casefold() for tag in playbook.tags}
        overlap = tags.intersection({tag.casefold() for tag in context.tags})
        if overlap:
            reasons.append(f"matching tags: {', '.join(sorted(overlap))}")
        if context.category and playbook.category.casefold() == context.category.casefold():
            reasons.append("matching category")
        if context.query and context.query.casefold() in playbook.title.casefold():
            reasons.append("title matches query")
        if playbook.key in context.recent_keys:
            reasons.append("recently used")
        if not reasons and playbook.status.value == "active":
            reasons.append("active playbook")
        return "; ".join(reasons) or "general relevance"

    def context_for_target(self, target: str = "", **extra: Any) -> RecommendationContext:
        """Derive a recommendation context from a target string."""
        tags: list[str] = []
        lowered = target.casefold()
        if "://" in lowered or any(host in lowered for host in (".com", ".net", ".org", ".io")):
            tags.append("web")
        if lowered.startswith(("10.", "192.168.", "172.")):
            tags.append("host")
        if "ctf" in lowered:
            tags.append("ctf")
        query = str(extra.get("query", ""))
        category = str(extra.get("category", ""))
        return RecommendationContext(
            query=query,
            tags=tuple(dict.fromkeys(tags)),
            target=target,
            category=category,
            recent_keys=tuple(str(key) for key in extra.get("recent_keys", ())),
        )

    def mixed(
        self, context: RecommendationContext, *, limit: int = DEFAULT_LIMIT
    ) -> list[Recommendation]:
        """Return a blended, deduplicated recommendation list."""
        combined = [
            *self.recommend_playbooks(context, limit=limit),
            *self.recommend_snippets(context, limit=limit),
            *self.recommend_templates(context, limit=limit),
        ]
        return self._rank(combined, limit)

    def _rank(self, results: list[Recommendation], limit: int) -> list[Recommendation]:
        results.sort(key=lambda item: (-item.score, item.kind, item.key))
        deduped: list[Recommendation] = []
        seen: set[tuple[str, str]] = set()
        for item in results:
            identity = (item.kind, item.key)
            if identity in seen:
                continue
            seen.add(identity)
            deduped.append(item)
        return [item for item in deduped if item.score > 0][:limit]

    def _score_terms(
        self,
        *,
        query: str,
        tags: tuple[str, ...],
        terms: str,
        record_tags: tuple[str, ...],
        usage: int,
        category: str,
        wanted_category: str,
        recent: bool,
        status: str = "",
    ) -> float:
        haystack = terms.casefold()
        needle = query.strip().casefold()
        score = 0.0
        if needle:
            if needle in haystack:
                score += 4.0
            score += 1.5 * sum(
                1 for token in needle.split() if len(token) > 2 and token in haystack
            )
        wanted = {tag.casefold() for tag in tags}
        actual = {tag.casefold() for tag in record_tags}
        if wanted:
            score += 3.0 * len(wanted.intersection(actual))
        if wanted_category and category.casefold() == wanted_category.casefold():
            score += 3.0
        if recent:
            score += 2.0
        score += min(usage, 20) / 20.0
        if status == "active":
            score += 1.0
        return round(score, 3)

    def _reason(
        self,
        record_tags: tuple[str, ...],
        context: RecommendationContext,
        *,
        usage: int = 0,
    ) -> str:
        tags = {tag.casefold() for tag in record_tags}
        overlap = tags.intersection({tag.casefold() for tag in context.tags})
        if overlap:
            return f"matching tags: {', '.join(sorted(overlap))}"
        if usage:
            return f"used {usage} times"
        if context.query:
            return "matches query"
        return "general relevance"


def build_context(query: str = "", **extra: Any) -> RecommendationContext:
    """Convenience builder for API callers."""
    return RecommendationContext(
        query=query,
        tags=tuple(str(tag) for tag in extra.get("tags", ())),
        target=str(extra.get("target", "")),
        category=str(extra.get("category", "")),
        recent_keys=tuple(str(key) for key in extra.get("recent_keys", ())),
    )


def recommendation_payload(results: list[Recommendation]) -> list[dict[str, Any]]:
    """Serialize recommendations for an API response."""
    return [item.as_dict() for item in results]
