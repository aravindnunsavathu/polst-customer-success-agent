"""The golden scenario eval suite (BUILD-PROMPT.md §10): "seasonal dip
misread as decay, champion departure, oversold commitment, single-creator
department going quiet, expansion gate near-miss... runs against the
agents on every prompt change." Unlike the other pytest suites, these
exercise the REAL seed scenario generators through a real Postgres test
DB and the real fetch.py conversion path — not hand-rolled fixtures —
because the point of a golden-scenario suite is catching a regression in
the actual integration path, not just the pure logic underneath it."""

import random
from datetime import date, timedelta

from faker import Faker
from sqlalchemy import select

from agents.decay.agent import run_decay_agent
from agents.expansion.gate import check_expansion_gate
from agents.llm.fake import HeuristicLLMProvider
from agents.renewal.diagnosis import assess_renewal_readiness
from agents.second_creator.agent import find_single_threaded_departments
from core.jobs.fetch import (
    account_context,
    fetch_campaign_facts,
    fetch_department_facts,
    fetch_stakeholder_facts,
    fetch_user_facts,
    fetch_value_doc_facts,
)
from core.models import Account, AccountIdentity, AccountPlan
from metrics.config import default_config
from seed import scenarios
from seed.cli import write_portfolio
from signals.triggers import trigger_volume_ratio_below_085

AS_OF = date(2026, 9, 5)


def _insert_scenario(db_session, scenario_fn):
    rng = random.Random(42)
    faker = Faker()
    faker.seed_instance(42)
    objects = scenario_fn(rng, faker, AS_OF, 0)
    write_portfolio(db_session, objects)
    identity = next(o for o in objects if isinstance(o, AccountIdentity))
    account = next(o for o in objects if isinstance(o, Account))
    return identity, account


def _account_plan(db_session, account_id):
    return db_session.execute(
        select(AccountPlan).where(AccountPlan.account_id == account_id).order_by(AccountPlan.last_refreshed.desc())
    ).scalars().first()


def test_seasonal_dip_does_not_fire_the_decay_trigger(db_session):
    identity, account = _insert_scenario(db_session, scenarios.seasonal_dip)
    campaigns = fetch_campaign_facts(db_session, identity.id)

    signal = trigger_volume_ratio_below_085(campaigns, account.contract_start, AS_OF, default_config())

    assert signal is None


def test_champion_departure_is_diagnosed_as_person_left_and_drafts_creator_outreach(db_session):
    identity, account = _insert_scenario(db_session, scenarios.champion_departure_collapse)
    plan = _account_plan(db_session, identity.id)

    result = run_decay_agent(
        campaigns=fetch_campaign_facts(db_session, identity.id),
        departments=fetch_department_facts(db_session, identity.id),
        users=fetch_user_facts(db_session, identity.id),
        stakeholders=fetch_stakeholder_facts(db_session, identity.id),
        account=account_context(account),
        stated_objective=plan.stated_objective, how_measured=plan.how_measured,
        tier=account.tier.value, as_of=AS_OF,
        classifier=HeuristicLLMProvider(), drafter=HeuristicLLMProvider(),
    )

    assert result.diagnosis.evidence["creator_deactivated"] is True
    assert result.diagnosis.evidence["champion_departed_no_successor"] is True
    assert result.cause == "person_left"
    assert result.action.type == "decay_outreach_creator"
    assert result.closes_play_run is False


def test_oversold_commitment_is_diagnosed_as_oversold_not_decay(db_session):
    identity, account = _insert_scenario(db_session, scenarios.oversold_commitment)
    campaigns = fetch_campaign_facts(db_session, identity.id)
    consumed = sum(1 for c in campaigns if c.billable)

    readiness = assess_renewal_readiness(
        value_docs=fetch_value_doc_facts(db_session, identity.id),
        consumed=consumed, campaigns=campaigns,
        stakeholders=fetch_stakeholder_facts(db_session, identity.id),
        account=account_context(account), as_of=AS_OF,
    )

    assert readiness.utilization_status == "oversold_at_signing"
    assert readiness.utilization_pace < 0.70


def test_single_threaded_department_going_quiet_is_caught_in_both_live_departments(db_session):
    identity, account = _insert_scenario(db_session, scenarios.single_threaded_department)
    campaigns = fetch_campaign_facts(db_session, identity.id)

    candidates = find_single_threaded_departments(campaigns, AS_OF)

    assert len(candidates) == 2  # every live department in this scenario has exactly one creator


def test_expansion_gate_near_miss_fails_on_exactly_one_condition(db_session):
    """expansion_ready is deliberately built to clear all six conditions
    (Phase 6). A near-miss should look identical except for one — proving
    the gate doesn't pass on "mostly qualified." Health-score history is
    supplied directly (a fresh scenario insert has none yet) so the test
    isolates the champion-introduction condition rather than also
    failing on missing scoring history."""
    identity, account = _insert_scenario(db_session, scenarios.expansion_ready)
    plan = _account_plan(db_session, identity.id)
    qualifying_history = [(AS_OF - timedelta(days=d), "healthy") for d in range(0, 70, 7)]

    near_miss = check_expansion_gate(
        value_docs=fetch_value_doc_facts(db_session, identity.id),
        campaigns=fetch_campaign_facts(db_session, identity.id),
        stakeholders=fetch_stakeholder_facts(db_session, identity.id),
        health_score_history=qualifying_history,
        target_department=plan.expansion_target_department,
        target_owner=plan.expansion_target_owner,
        champion_introduction=False,  # the one condition this account "just misses" on
        new_budget_holder=plan.expansion_new_budget_holder,
        as_of=AS_OF,
    )
    fully_qualifying = check_expansion_gate(
        value_docs=fetch_value_doc_facts(db_session, identity.id),
        campaigns=fetch_campaign_facts(db_session, identity.id),
        stakeholders=fetch_stakeholder_facts(db_session, identity.id),
        health_score_history=qualifying_history,
        target_department=plan.expansion_target_department,
        target_owner=plan.expansion_target_owner,
        champion_introduction=plan.expansion_champion_introduction,
        new_budget_holder=plan.expansion_new_budget_holder,
        as_of=AS_OF,
    )

    assert fully_qualifying.qualified is True
    assert near_miss.qualified is False
    assert near_miss.missing == ["champion_not_willing_or_departed"]
