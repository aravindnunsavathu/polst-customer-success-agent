import enum


class CommercialModel(str, enum.Enum):
    AD_HOC = "ad_hoc"
    COMMITTED = "committed"


class Tier(str, enum.Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


class Quadrant(str, enum.Enum):
    INVEST = "invest"
    PROTECT = "protect"
    MAINTAIN = "maintain"
    QUALIFY = "qualify"


class StakeholderType(str, enum.Enum):
    ECONOMIC_BUYER = "economic_buyer"
    EXEC_SPONSOR = "exec_sponsor"
    CHAMPION = "champion"
    CREATOR = "creator"
    BLOCKER = "blocker"


class RelationshipStrength(str, enum.Enum):
    STRONG = "strong"
    NEUTRAL = "neutral"
    WEAK = "weak"
    UNKNOWN = "unknown"


class UserEventType(str, enum.Enum):
    DEACTIVATION = "deactivation"
    INVITATION_SENT = "invitation_sent"
    INVITATION_ACCEPTED = "invitation_accepted"


class HealthBand(str, enum.Enum):
    HEALTHY = "healthy"
    WATCH = "watch"
    AT_RISK = "at_risk"
    CRITICAL = "critical"


class SignalSeverity(str, enum.Enum):
    T1 = "T1"  # 3-day SLA
    T2 = "T2"  # 10-day SLA
    T3 = "T3"  # automated sequence, immediate


class PlayType(str, enum.Enum):
    ONBOARDING = "onboarding"
    DECAY = "decay"
    RENEWAL = "renewal"
    EXPANSION = "expansion"


class AutonomyLevel(str, enum.Enum):
    AUTO = "auto"
    DRAFT = "draft"
    HUMAN_WRITES = "human_writes"
    NEVER = "never"


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ReportType(str, enum.Enum):
    """Portfolio Analyst's four cadenced outputs (BUILD-PROMPT.md §7) plus
    the VoC Router's one — all "write to the console, draft nothing
    outbound," so they share one table rather than five near-identical
    ones."""

    AT_RISK_CRITICAL_REVIEW = "at_risk_critical_review"  # weekly
    WATCH_REVIEW = "watch_review"  # bi-weekly
    MONTHLY_CEO_SNAPSHOT = "monthly_ceo_snapshot"  # monthly — NRR roll-up + portfolio snapshot
    CALIBRATION_INPUT = "calibration_input"  # quarterly
    VOC_RANKED_LIST = "voc_ranked_list"


class RejectionReasonCategory(str, enum.Enum):
    """Structured per BUILD-PROMPT.md §8: rejection reasons are training data."""

    WRONG_CAUSE = "wrong_cause"
    WRONG_TONE = "wrong_tone"
    WRONG_RECIPIENT = "wrong_recipient"
    FACTUALLY_INCORRECT = "factually_incorrect"
    VOLUME_PUSHING = "volume_pushing"
    PREMATURE = "premature"
    OTHER = "other"
