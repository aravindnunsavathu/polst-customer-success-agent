"""Normalized shapes every source adapter must produce. Nothing downstream
of an adapter — the loader, the metrics engine, anything else — ever sees
a vendor-specific field name or format; it only sees these. This is the
boundary BUILD-PROMPT.md §4 draws when it says "ingestion adapters
normalise into it; nothing downstream reads a vendor shape directly."""

from datetime import date, datetime

from pydantic import BaseModel


class NormalizedAccount(BaseModel):
    external_id: str
    name: str
    contract_start: date
    term: str
    plan: str | None = None


class NormalizedDepartment(BaseModel):
    external_id: str
    account_external_id: str
    name: str
    created_at: datetime


class NormalizedUser(BaseModel):
    external_id: str
    account_external_id: str
    department_external_id: str | None = None
    role: str | None = None
    created_at: datetime
    last_active_at: datetime | None = None
    deactivated_at: datetime | None = None


class NormalizedCampaign(BaseModel):
    external_id: str
    account_external_id: str
    department_external_id: str
    creator_external_id: str
    created_at: datetime
    launched_at: datetime | None = None
    template_type: str | None = None
    billable: bool = True


class NormalizedBillingPeriod(BaseModel):
    account_external_id: str
    period: date
    billable_campaign_count: int
