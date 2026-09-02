"""The adapter interface every source (product DB, billing, CRM, email,
support) implements (BUILD-PROMPT.md §11). An adapter's only job is to
produce NormalizedX records — it never writes to Postgres itself; that's
ingest/loader.py's job, shared by every adapter so upsert semantics are
defined once."""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from ingest.schemas import (
    NormalizedAccount,
    NormalizedBillingPeriod,
    NormalizedCampaign,
    NormalizedDepartment,
    NormalizedUser,
)


class SourceAdapter(ABC):
    """One method per Tier 1 entity (doc 03). A source that can't provide
    one — e.g. a CRM adapter has no campaigns — simply returns an empty
    iterable rather than needing a different interface per source."""

    @abstractmethod
    def fetch_accounts(self) -> Iterable[NormalizedAccount]: ...

    @abstractmethod
    def fetch_departments(self) -> Iterable[NormalizedDepartment]: ...

    @abstractmethod
    def fetch_users(self) -> Iterable[NormalizedUser]: ...

    @abstractmethod
    def fetch_campaigns(self) -> Iterable[NormalizedCampaign]: ...

    @abstractmethod
    def fetch_billing_periods(self) -> Iterable[NormalizedBillingPeriod]: ...
