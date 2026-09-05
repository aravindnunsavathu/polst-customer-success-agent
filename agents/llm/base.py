"""The mandatory LLMProvider abstraction (BUILD-PROMPT.md §11a). Swapping
a provider, or the model behind one agent, is a config change — nothing
in /agents ever imports a provider SDK directly.

Scoped to what an agent actually needs today: one structured completion
call per step (classify, then separately draft). Tool use and streaming
are explicitly the Orchestrator's problem ("most demanding, least suited
to a small model... migrate last, if at all" — §11a's task-class table),
and nothing in this codebase orchestrates multi-step tool use yet, so
those aren't built until something actually calls them."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMUsage:
    """Logged onto every Action record per §11a — "we cannot make an
    evidence-based model decision without that telemetry.\""""

    provider: str
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class LLMResponse:
    text: str
    parsed: dict | None  # populated when response_schema was provided and parsing succeeded
    usage: LLMUsage


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        prompt: str,
        response_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """response_schema, when given, is a JSON Schema the provider
        should constrain output to (classification tasks use this;
        free-text drafting tasks omit it). Providers that can't natively
        constrain output should still return best-effort parsed JSON in
        `.parsed` and raise if it doesn't validate — never a silent
        best-guess default (CLAUDE.md's fail-loud rule applies here too)."""
        ...
