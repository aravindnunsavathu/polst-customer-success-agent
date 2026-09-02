"""Synthetic 40-account portfolio generator (BUILD-PROMPT.md §13).
Deterministic given (seed, as_of): same inputs always produce the same
portfolio, which matters for reproducible demos and for using this as
fixture data in later phases' golden tests. Pure in-memory generation —
no database or network access; see seed/cli.py for the write step."""

import random
from datetime import date

from faker import Faker

from seed.scenarios import SCENARIOS

ACCOUNTS_PER_SCENARIO = 5  # 8 scenarios x 5 = 40 accounts, per §13


def generate_portfolio(seed: int = 42, as_of: date | None = None) -> list:
    as_of = as_of or date.today()
    rng = random.Random(seed)
    faker = Faker()
    faker.seed_instance(seed)

    objects = []
    for scenario in SCENARIOS:
        for i in range(ACCOUNTS_PER_SCENARIO):
            objects.extend(scenario(rng, faker, as_of, i))
    return objects
