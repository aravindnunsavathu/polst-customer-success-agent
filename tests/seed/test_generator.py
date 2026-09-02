from datetime import date

from core.models import Account, AccountIdentity, Campaign
from seed.generator import generate_portfolio


def test_generates_forty_accounts():
    objects = generate_portfolio(seed=1, as_of=date(2026, 9, 1))
    accounts = [o for o in objects if isinstance(o, Account)]
    identities = [o for o in objects if isinstance(o, AccountIdentity)]
    assert len(accounts) == 40
    assert len(identities) == 40


def test_deterministic_given_same_seed_and_date():
    as_of = date(2026, 9, 1)
    first = generate_portfolio(seed=7, as_of=as_of)
    second = generate_portfolio(seed=7, as_of=as_of)

    first_names = sorted(o.name for o in first if isinstance(o, Account))
    second_names = sorted(o.name for o in second if isinstance(o, Account))
    assert first_names == second_names

    first_campaigns = sum(1 for o in first if isinstance(o, Campaign))
    second_campaigns = sum(1 for o in second if isinstance(o, Campaign))
    assert first_campaigns == second_campaigns


def test_no_campaign_predates_its_account_contract():
    objects = generate_portfolio(seed=3, as_of=date(2026, 9, 1))
    accounts_by_identity = {
        o.account_id: o for o in objects if isinstance(o, Account)
    }
    campaigns = [o for o in objects if isinstance(o, Campaign)]
    violations = [
        c for c in campaigns
        if c.created_at.date() < accounts_by_identity[c.account_id].contract_start
    ]
    assert violations == []
