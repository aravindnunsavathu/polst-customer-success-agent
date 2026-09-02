"""Reference SourceAdapter implementation, reading a single JSON export —
doc 03's "manual export on request" delivery mechanism, the one Tier 1
option that needs no work from Product to start using. A CSV or live
product-DB adapter follows the exact same SourceAdapter interface; this
is what every future adapter's fixture-backed test is modeled on."""

import json
from pathlib import Path

from ingest.base import SourceAdapter
from ingest.schemas import (
    NormalizedAccount,
    NormalizedBillingPeriod,
    NormalizedCampaign,
    NormalizedDepartment,
    NormalizedUser,
)


class FixtureAdapter(SourceAdapter):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        with open(self.path) as f:
            self._data = json.load(f)

    def fetch_accounts(self):
        return [NormalizedAccount(**row) for row in self._data.get("accounts", [])]

    def fetch_departments(self):
        return [NormalizedDepartment(**row) for row in self._data.get("departments", [])]

    def fetch_users(self):
        return [NormalizedUser(**row) for row in self._data.get("users", [])]

    def fetch_campaigns(self):
        return [NormalizedCampaign(**row) for row in self._data.get("campaigns", [])]

    def fetch_billing_periods(self):
        return [
            NormalizedBillingPeriod(**row) for row in self._data.get("billing_periods", [])
        ]
