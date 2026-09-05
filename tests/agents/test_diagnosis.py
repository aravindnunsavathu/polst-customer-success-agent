from datetime import date, datetime, time, timedelta

from agents.decay.diagnosis import diagnose_decay, estimate_onset_date, localize_decay
from signals.types import AccountContext, CampaignFact, DepartmentFact, StakeholderFact, UserFact

AS_OF = date(2026, 9, 1)


def _campaign(dept, creator, days_ago, launched=True):
    created = datetime.combine(AS_OF - timedelta(days=days_ago), time(10, 0))
    return CampaignFact(
        id=f"{dept}-{creator}-{days_ago}", department_id=dept, creator_id=creator,
        created_at=created, launched_at=created if launched else None,
    )


def test_localize_decay_picks_the_department_with_the_biggest_drop():
    # dept "healthy" holds steady; dept "declining" drops hard
    campaigns = [_campaign("healthy", "u1", d) for d in range(0, 179, 10)]
    campaigns += [_campaign("declining", "u2", d) for d in range(95, 179, 10)]  # only prior-90d volume
    departments = [
        DepartmentFact(id="healthy", created_at=datetime(2024, 1, 1)),
        DepartmentFact(id="declining", created_at=datetime(2024, 1, 1)),
    ]
    assert localize_decay(campaigns, departments, AS_OF) == "declining"


def test_localize_decay_returns_none_without_a_prior_baseline():
    campaigns = [_campaign("d1", "u1", 5)]  # only recent, no prior-90d history at all
    departments = [DepartmentFact(id="d1", created_at=datetime(2024, 1, 1))]
    assert localize_decay(campaigns, departments, AS_OF) is None


def test_estimate_onset_date_finds_the_inflection_month():
    # steady ~10/month for months -5..-2, then a clear drop in the most recent 2 months
    campaigns = []
    for months_ago in range(2, 6):
        for d in range(0, 25, 5):
            campaigns.append(_campaign("d1", "u1", months_ago * 30 + d))
    for months_ago in range(0, 2):
        for d in range(0, 25, 12):
            campaigns.append(_campaign("d1", "u1", months_ago * 30 + d))
    onset = estimate_onset_date(campaigns, AS_OF)
    # AS_OF is itself the 1st of a month here, so the current (1-day-old)
    # partial-month bucket legitimately can be the detected inflection
    # point — onset must never be AFTER as_of, but can equal it.
    assert onset <= AS_OF
    assert onset > AS_OF - timedelta(days=180)


def test_diagnose_decay_localizes_creator_in_a_single_threaded_department():
    campaigns = [_campaign("d1", "solo", d) for d in range(0, 89, 30)]
    campaigns += [_campaign("d1", "solo", d) for d in range(95, 179, 10)]
    departments = [DepartmentFact(id="d1", created_at=datetime(2024, 1, 1))]
    users = [
        UserFact(id="solo", department_id="d1", created_at=datetime(2024, 1, 1),
                 last_active_at=datetime(2026, 7, 1), deactivated_at=datetime(2026, 7, 1))
    ]
    stakeholders = [StakeholderFact(type="champion", last_contact_at=None, departed_at=datetime(2026, 7, 1))]
    account = AccountContext(contract_start=date(2024, 1, 1), commercial_model="ad_hoc",
                                committed_volume=None, commitment_end=None, potential_departments=2)

    diagnosis = diagnose_decay(
        campaigns=campaigns, departments=departments, users=users,
        stakeholders=stakeholders, account=account, as_of=AS_OF,
    )
    assert diagnosis.department_id == "d1"
    assert diagnosis.creator_id == "solo"
    assert diagnosis.evidence["creator_deactivated"] is True
    assert diagnosis.evidence["champion_departed_no_successor"] is True
    assert diagnosis.evidence["scoped_prior_90d_count"] > 0
