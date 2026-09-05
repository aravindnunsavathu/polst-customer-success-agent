"""Doc 06 Play 3's three T-20 checks, run "before any commercial
conversation — under-utilisation is the customer's strongest argument
for reducing commitment, and it must be solved before the conversation,
not during it." Deterministic — these are readiness facts, not
judgment calls, matching the diagnose-before-contact discipline the
Decay Agent already applies.

Unlike the Onboarding Agent's handoff review, none of these three checks
block progression — doc 06 says an unmet evidence check "is the whole
job for the next 30 days," not a reason to refuse the play. They inform
what the internal readiness brief flags, and the utilization check's
cause classification feeds the growth-proposal drafting stage."""

from dataclasses import dataclass, field
from datetime import date

from metrics.derived import commitment_pace, volume_ratio_90d
from signals.types import AccountContext, CampaignFact, StakeholderFact, ValueDocFact


@dataclass(frozen=True)
class RenewalReadiness:
    value_doc_current: bool
    value_doc_reason: str | None
    utilization_pace: float | None
    utilization_status: str | None  # "on_pace" | "oversold_at_signing" | "decay_related" | None (not committed)
    economic_buyer_identified: bool
    exec_sponsor_engaged_this_quarter: bool
    gaps: list[str] = field(default_factory=list)


def evidence_check(value_docs: list[ValueDocFact], as_of: date, recency_days: int = 180) -> tuple[bool, str | None]:
    confirmed = [d for d in value_docs if d.confirmed_at is not None]
    if not confirmed:
        return False, "no_confirmed_value_doc"
    most_recent = max(d.confirmed_at for d in confirmed)
    if (as_of - most_recent.date()).days > recency_days:
        return False, "confirmed_value_doc_is_stale"
    return True, None


def utilization_check(
    consumed: int, campaigns: list[CampaignFact], account: AccountContext, as_of: date, oversold_threshold: float = 0.70,
) -> tuple[float | None, str | None]:
    pace = commitment_pace(consumed, account.committed_volume, account.contract_start, account.commitment_end, as_of)
    if pace.value is None:
        return None, None  # not a committed account — nothing to diagnose
    if pace.value >= oversold_threshold:
        return pace.value, "on_pace"
    # Under-paced: is the shortfall a recent decline (decay — route to
    # Play 2), or has utilization been low the whole term (oversold at
    # signing — a Sales-handoff finding, not a CS failure, per doc 06)?
    recent = volume_ratio_90d(campaigns, as_of)
    if recent.value is not None and recent.value < 0.85:
        return pace.value, "decay_related"
    return pace.value, "oversold_at_signing"


def stakeholder_check(stakeholders: list[StakeholderFact], as_of: date, engaged_within_days: int = 90) -> tuple[bool, bool]:
    economic_buyer_identified = any(
        s.type == "economic_buyer" and s.departed_at is None for s in stakeholders
    )
    exec_sponsor_engaged = any(
        s.type == "exec_sponsor" and s.departed_at is None and s.last_contact_at is not None
        and (as_of - s.last_contact_at.date()).days <= engaged_within_days
        for s in stakeholders
    )
    return economic_buyer_identified, exec_sponsor_engaged


def assess_renewal_readiness(
    *,
    value_docs: list[ValueDocFact],
    consumed: int,
    campaigns: list[CampaignFact],
    stakeholders: list[StakeholderFact],
    account: AccountContext,
    as_of: date,
) -> RenewalReadiness:
    value_doc_current, value_doc_reason = evidence_check(value_docs, as_of)
    utilization_pace, utilization_status = utilization_check(consumed, campaigns, account, as_of)
    economic_buyer_identified, exec_sponsor_engaged = stakeholder_check(stakeholders, as_of)

    gaps = []
    if not value_doc_current:
        gaps.append(f"value_doc: {value_doc_reason}")
    if utilization_status in ("oversold_at_signing", "decay_related"):
        gaps.append(f"utilization: {utilization_status} ({utilization_pace:.0%})")
    if not economic_buyer_identified:
        gaps.append("no_economic_buyer_identified")
    if not exec_sponsor_engaged:
        gaps.append("exec_sponsor_not_engaged_this_quarter")

    return RenewalReadiness(
        value_doc_current=value_doc_current,
        value_doc_reason=value_doc_reason,
        utilization_pace=utilization_pace,
        utilization_status=utilization_status,
        economic_buyer_identified=economic_buyer_identified,
        exec_sponsor_engaged_this_quarter=exec_sponsor_engaged,
        gaps=gaps,
    )
