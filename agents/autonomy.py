"""Resolves an action's autonomy level from the §9 matrix, with the v1
cap enforced in code (CLAUDE.md: "gates are enforced in code, not in
prompts"). Pure — the caller supplies approved_without_edit_count from a
real Action query; this module never touches the database itself."""

from functools import lru_cache
from pathlib import Path

import yaml

from core.enums import AutonomyLevel

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "autonomy_matrix.yaml"


@lru_cache(maxsize=1)
def _config(path: str | None = None) -> dict:
    with open(path or DEFAULT_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _row(action_type: str, config_path: str | None = None) -> dict:
    cfg = _config(config_path)
    try:
        return cfg["matrix"][action_type]
    except KeyError:
        raise ValueError(f"no autonomy row for action_type {action_type!r}")


def raw_matrix_level(tier: str, action_type: str, config_path: str | None = None) -> AutonomyLevel:
    row = _row(action_type, config_path)
    try:
        value = row["tiers"][tier]
    except KeyError:
        raise ValueError(f"no autonomy column for tier {tier!r} in action_type {action_type!r}")
    return AutonomyLevel(value)


def is_customer_facing(action_type: str, config_path: str | None = None) -> bool:
    return _row(action_type, config_path)["customer_facing"]


def promotion_threshold(config_path: str | None = None) -> int:
    return _config(config_path)["promotion_threshold_approved_without_edit"]


def resolve_autonomy(
    tier: str,
    action_type: str,
    approved_without_edit_count: int = 0,
    config_path: str | None = None,
) -> AutonomyLevel:
    """§9's v1 cap only applies to customer-facing action types — "human
    approval by default" (§2.6) is about what reaches a customer.
    score_detect_alert and internal_brief are Auto in the matrix and stay
    Auto here regardless of approved_without_edit_count; there's nothing
    to gate since nothing customer-facing is at stake. For customer-facing
    types, `auto` only actually applies once the promotion threshold is
    met — built, not just documented (§9: "Build the edit-rate tracking
    that makes that promotion decision evidential rather than a vibe")."""
    level = raw_matrix_level(tier, action_type, config_path)
    if (
        level == AutonomyLevel.AUTO
        and is_customer_facing(action_type, config_path)
        and approved_without_edit_count < promotion_threshold(config_path)
    ):
        return AutonomyLevel.DRAFT
    return level
