"""Sales handoff validation (BUILD-PROMPT.md §7 / doc 06 Play 1):
"validate the Sales handoff against the checklist and refuse an
incomplete one back to Sales — build this as a real workflow state, not
a warning." Pure, deterministic — this is a data-completeness check, not
a judgment call.

Doc 06 lists six handoff criteria. Four are derivable from our data;
"commercial terms" is checked as far as our schema can tell (mostly
trivial, since contract_start/term/commercial_model are NOT NULL
columns already); "anything promised during the sale that is not yet
true" has no data source at all — nothing in the schema records verbal
or contractual promises made pre-signing, so it cannot be automatically
verified and is not included in `missing`. This is a real, named gap,
not a silent pass: it's exposed as `unverifiable` on the result so a
human reviewing a handoff still sees it was never checked."""

from dataclasses import dataclass, field

from core.enums import CommercialModel
from signals.types import AccountContext, DepartmentFact, StakeholderFact, UserFact


@dataclass(frozen=True)
class HandoffReview:
    accepted: bool
    missing: list[str] = field(default_factory=list)
    unverifiable: list[str] = field(default_factory=list)


def review_handoff(
    *,
    stated_objective: str | None,
    stakeholders: list[StakeholderFact],
    departments: list[DepartmentFact],
    users: list[UserFact],
    account: AccountContext,
) -> HandoffReview:
    missing = []

    if not stated_objective:
        missing.append("stated_business_objective")
    if not any(s.type == "economic_buyer" and s.departed_at is None for s in stakeholders):
        missing.append("named_economic_buyer")
    if not users:
        missing.append("named_creators")
    if not departments:
        missing.append("departments_in_scope")
    if account.commercial_model == CommercialModel.COMMITTED.value and not account.committed_volume:
        missing.append("commercial_terms")

    return HandoffReview(
        accepted=not missing,
        missing=missing,
        unverifiable=["nothing_overpromised_during_sale"],
    )
