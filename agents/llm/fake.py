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
        # VoC tagging evidence is keyed by "verbatim" — a completely
        # different classification task (fixed friction/request labels,
        # not a decay cause) sharing the same complete(response_schema=)
        # call shape, dispatched the same way _draft dispatches on shape.
        if "verbatim" in evidence:
            return HeuristicLLMProvider._classify_voc_tag(evidence["verbatim"])

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
    def _classify_voc_tag(verbatim: str) -> dict:
        lowered = verbatim.lower()
        if any(w in lowered for w in ("bug", "error", "broken", "crash", "fail")):
            return {"tag": "product_friction", "confidence": "medium"}
        if any(w in lowered for w in ("wish", "would be great", "feature", "could you add", "support for")):
            return {"tag": "feature_request", "confidence": "medium"}
        if any(w in lowered for w in ("expensive", "price", "cost", "discount", "budget")):
            return {"tag": "pricing_concern", "confidence": "medium"}
        if any(w in lowered for w in ("confusing", "hard to", "didn't understand", "onboarding", "setup")):
            return {"tag": "onboarding_gap", "confidence": "medium"}
        if any(w in lowered for w in ("love", "great", "thanks", "works well")):
            return {"tag": "positive_feedback", "confidence": "medium"}
        return {"tag": "other", "confidence": "low"}

    @staticmethod
    def _draft(prompt: str, evidence: dict) -> str:
        # second_creator_seeding evidence has no "stated_objective" key at
        # all (unlike decay/onboarding, which always include it, even as
        # None) — that absence is the signal this is a seeding message,
        # not a check-in on the customer's objective.
        if "department_id" in evidence and "stated_objective" not in evidence:
            return (
                "Hi — you've been running campaigns for your team solo and it's going well. "
                "Worth bringing in a colleague so someone else can help carry the load? "
                "Happy to help get them set up."
            )
        # Portfolio Analyst internal reports have their own recognizable
        # evidence shapes — none of them are a customer check-in, so each
        # gets its own data-grounded summary rather than falling through
        # to the objective-check-in template below.
        if "total_revenue_at_risk" in evidence:
            return (
                f"{evidence['count']} accounts are At-risk or Critical this week, "
                f"representing an estimated ${evidence['total_revenue_at_risk']:,.0f}/mo at risk. "
                + (
                    f"Top exposure: {evidence['accounts'][0]['name']}."
                    if evidence.get("accounts") else "No accounts currently flagged."
                )
            )
        if "accounts" in evidence and "count" in evidence:
            return (
                f"{evidence['count']} accounts are in Watch this period. "
                + (
                    f"Closest to slipping: {evidence['accounts'][0]['name']}."
                    if evidence.get("accounts") else "No accounts currently in Watch."
                )
            )
        if "nrr" in evidence:
            nrr_value = evidence.get("nrr")
            nrr_text = f"{nrr_value:.0%}" if nrr_value is not None else f"unavailable ({evidence.get('nrr_null_reason')})"
            return (
                f"NRR this period: {nrr_text}, across a cohort of {evidence.get('cohort_size', 0)} accounts. "
                f"{evidence.get('total_accounts', 0)} accounts total, {evidence.get('new_logos_count', 0)} new logos. "
                f"Band mix: {evidence.get('band_counts', {})}."
            )
        if "hit_rate" in evidence or "false_alarm_rate" in evidence:
            return (
                f"Hit rate: {evidence.get('hit_rate')}, false alarm rate: {evidence.get('false_alarm_rate')}, "
                f"median lead time: {evidence.get('lead_time_days')} days, "
                f"over {evidence.get('event_count', 0)} events this quarter."
            )
        if "themes" in evidence:
            top = evidence["themes"][0] if evidence.get("themes") else None
            return (
                f"{len(evidence.get('themes', []))} distinct friction themes this period. "
                + (f"Top: {top['tag']} across {top['accounts_affected']} accounts." if top else "No themes logged.")
            )
        objective = evidence.get("stated_objective") or "the result you were working toward"
        return (
            f"Hi — checking in on {objective}. Are you still on track with that? "
            f"Happy to help if anything's changed on your end."
        )
