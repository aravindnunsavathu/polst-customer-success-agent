"""Two deterministic, network-free providers — there are no Bedrock
credentials in this environment (same situation as Terraform in
/infra: authored, not applied/tested against a live API).

FakeLLMProvider: exact queued responses for unit tests that need precise
control over what the "model" says.

HeuristicLLMProvider: a plain-Python stand-in that reads the same
evidence JSON block every decay prompt embeds (see /prompts) and applies
simple rules — good enough to run the real pipeline end-to-end against
the seeded portfolio and see plausible behavior, clearly not a real
classifier. This is what /agents/jobs/run_decay_agent.py uses by default
until real Bedrock access exists (see agents/llm/config.py)."""

import json
import re
import time

from agents.llm.base import LLMProvider, LLMResponse, LLMUsage

_EVIDENCE_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


class FakeLLMProvider(LLMProvider):
    def __init__(self, responses: list[LLMResponse] | None = None):
        self._responses = list(responses or [])
        self.calls: list[dict] = []

    def complete(self, *, system: str, prompt: str, response_schema=None, max_tokens: int = 1024) -> LLMResponse:
        self.calls.append({"system": system, "prompt": prompt, "response_schema": response_schema})
        if not self._responses:
            raise RuntimeError("FakeLLMProvider has no queued responses left")
        return self._responses.pop(0)


class HeuristicLLMProvider(LLMProvider):
    """Not a real model — see module docstring."""

    def complete(self, *, system: str, prompt: str, response_schema=None, max_tokens: int = 1024) -> LLMResponse:
        start = time.monotonic()
        match = _EVIDENCE_BLOCK.search(prompt)
        evidence = json.loads(match.group(1)) if match else {}

        if response_schema is not None:
            text = json.dumps(self._classify(evidence))
        else:
            text = self._draft(prompt, evidence)

        latency_ms = (time.monotonic() - start) * 1000
        parsed = json.loads(text) if response_schema is not None else None
        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=LLMUsage(
                provider="heuristic",
                model="heuristic-v1",
                latency_ms=latency_ms,
                input_tokens=len(prompt.split()),
                output_tokens=len(text.split()),
                cost_usd=0.0,
            ),
        )

    @staticmethod
    def _classify(evidence: dict) -> dict:
        seasonality = evidence.get("seasonality")
        if seasonality and seasonality.get("diverges") and (seasonality.get("yoy_ratio") or 0) >= 0.85:
            return {"cause": "seasonal", "confidence": "high"}
        if evidence.get("creator_deactivated"):
            return {"cause": "person_left", "confidence": "high"}
        if evidence.get("commitment_pace") is not None and evidence["commitment_pace"] < 0.5:
            return {"cause": "budget_priority_shift", "confidence": "medium"}
        if evidence.get("abandonment_rate") is not None and evidence["abandonment_rate"] > 0.3:
            return {"cause": "product_friction", "confidence": "medium"}
        if evidence.get("creator_repeat_rate") is not None and evidence["creator_repeat_rate"] < 0.2:
            return {"cause": "never_got_value", "confidence": "medium"}
        return {"cause": "never_got_value", "confidence": "low"}

    @staticmethod
    def _draft(prompt: str, evidence: dict) -> str:
        objective = evidence.get("stated_objective") or "the result you were working toward"
        return (
            f"Hi — checking in on {objective}. Are you still on track with that? "
            f"Happy to help if anything's changed on your end."
        )
