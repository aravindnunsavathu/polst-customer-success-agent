"""The Voice-of-Customer Router (BUILD-PROMPT.md §7): "tags every logged
friction point, decay cause, and feature request; deduplicates across
accounts; produces a ranked, evidence-backed list for Product with
account and revenue attached. No side channels: everything routes
through this one path." Non-customer-facing, same as the Portfolio
Analyst — this reads FeedbackItems the Decay/Renewal Agents already
created (cause, oversold_commitment) plus anything logged with no tag
yet (raw support-sourced feedback), classifies the untagged ones, groups
by tag across every account, and ranks by accounts-affected x revenue."""

import json
from collections import defaultdict
from dataclasses import dataclass

from agents.llm.base import LLMProvider
from agents.prompts import load_prompt

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "tag": {
            "type": "string",
            "enum": ["product_friction", "feature_request", "pricing_concern", "onboarding_gap", "positive_feedback", "other"],
        },
        "confidence": {"type": "string"},
    },
    "required": ["tag", "confidence"],
}


@dataclass(frozen=True)
class FeedbackItemFact:
    id: str
    account_id: str
    verbatim: str
    tag: str | None


@dataclass(frozen=True)
class VoCTheme:
    tag: str
    accounts_affected: int
    total_revenue_at_risk: float
    account_ids: list[str]
    sample_verbatims: list[str]


def classify_tag(verbatim: str, classifier: LLMProvider) -> str:
    response = classifier.complete(
        system="You tag customer feedback into a fixed set of Voice-of-Customer categories.",
        prompt=load_prompt("voc_tag_classification", evidence_json=json.dumps({"verbatim": verbatim}, indent=2)),
        response_schema=TAG_SCHEMA,
    )
    return response.parsed["tag"]


def dedupe_and_rank(
    items: list[FeedbackItemFact],
    revenue_by_account: dict[str, float],
    classifier: LLMProvider,
    top_n: int = 10,
) -> tuple[list[VoCTheme], dict[str, str]]:
    """Returns the ranked themes plus a {item_id: tag} map for items that
    had no tag yet — the caller persists those back onto the FeedbackItem
    rows so tagging is a one-time cost, not repeated every run."""
    newly_tagged: dict[str, str] = {}
    tag_by_item_id: dict[str, str] = {}
    for item in items:
        if item.tag:
            tag_by_item_id[item.id] = item.tag
        else:
            tag = classify_tag(item.verbatim, classifier)
            tag_by_item_id[item.id] = tag
            newly_tagged[item.id] = tag

    groups: dict[str, list[FeedbackItemFact]] = defaultdict(list)
    for item in items:
        groups[tag_by_item_id[item.id]].append(item)

    themes = []
    for tag, group_items in groups.items():
        account_ids = sorted({i.account_id for i in group_items})
        themes.append(VoCTheme(
            tag=tag,
            accounts_affected=len(account_ids),
            total_revenue_at_risk=sum(revenue_by_account.get(a, 0.0) for a in account_ids),
            account_ids=account_ids,
            sample_verbatims=[i.verbatim for i in group_items[:3]],
        ))
    themes.sort(key=lambda t: (t.accounts_affected, t.total_revenue_at_risk), reverse=True)
    return themes[:top_n], newly_tagged
