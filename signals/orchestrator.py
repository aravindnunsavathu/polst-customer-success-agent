"""The non-agent orchestrator (BUILD-PROMPT.md §7): dedupes signals
against whatever's already open, decides whether a new play_run should
open, and refuses a second concurrent one on the same account — "one
account with four signals gets one coordinated intervention." Read as
account-wide exclusivity (at most one open play_run per account,
regardless of type), the stricter and more defensible reading of
"coordinated, not fragmented." Pure decision logic — the nightly job
supplies "what's already open" from the database and acts on the result."""

from dataclasses import dataclass, field

from signals.types import SignalCandidate

PLAY_FOR_TRIGGER = {
    "play1_contract_signed": "onboarding",
    "play3_renewal_window": "renewal",
    "play4_expansion_candidate": "expansion",
}

# If multiple plays could open the same night, decay wins — it's "the
# highest-value agent in the system" per §7, and diagnosing decay early
# matters more than a routine renewal or expansion touch that week.
PLAY_PRIORITY = ["decay", "renewal", "onboarding", "expansion"]

TIER_WEIGHT = {"T1": 3, "T2": 2, "T3": 1, "T4": 0}


def play_for_signal_type(signal_type: str) -> str | None:
    if signal_type.startswith("decay_"):
        return "decay"
    return PLAY_FOR_TRIGGER.get(signal_type)


@dataclass(frozen=True)
class OrchestratorDecision:
    new_signals: list[SignalCandidate] = field(default_factory=list)
    play_to_open: str | None = None


def decide(
    candidates: list[SignalCandidate],
    already_open_signal_types: set[str],
    has_open_play_run: bool,
) -> OrchestratorDecision:
    new_signals = [c for c in candidates if c.type not in already_open_signal_types]

    play_to_open = None
    if new_signals and not has_open_play_run:
        candidate_plays = {play_for_signal_type(c.type) for c in new_signals} - {None}
        for play in PLAY_PRIORITY:
            if play in candidate_plays:
                play_to_open = play
                break

    return OrchestratorDecision(new_signals=new_signals, play_to_open=play_to_open)


def priority_score(tier: str, num_open_signals: int, estimated_monthly_revenue: float) -> float:
    """A rough tier x severity x revenue-at-risk heuristic for sorting
    the portfolio worklist (§7) — not a scientific weighting, just enough
    to put "T1 account with three open decay signals" above "T3 account
    with one." estimated_monthly_revenue is departments_live x $8,000
    (context/polst-company-product.md's flat per-department price), a
    proxy — there's no real billing-tied revenue figure wired in yet."""
    return TIER_WEIGHT.get(tier, 0) * 100 + num_open_signals * 10 + estimated_monthly_revenue / 1000
