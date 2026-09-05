"""SLA clock, per BUILD-PROMPT.md §6: response time is purely a function
of account tier. T3's "immediate automated sequence" gets a due date of
now — there's no human response window to track, but the field stays
non-null so the console's SLA-clock display doesn't need a special case."""

from datetime import datetime, timedelta

SLA_DAYS = {"T1": 3, "T2": 10, "T3": 0}


def sla_due_at(tier: str, fired_at: datetime) -> datetime:
    return fired_at + timedelta(days=SLA_DAYS.get(tier, SLA_DAYS["T2"]))
