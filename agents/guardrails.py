"""The no-volume-pushing guardrail (BUILD-PROMPT.md §2.5): "no agent
output may have 'run more campaigns' as its primary call to action."
Deterministic keyword check — per CLAUDE.md, "gates are enforced in
code, not in prompts," so this isn't asking the model to police itself.
A keyword list can't catch every rephrasing; it catches the literal
failure mode the brief names and makes it visible before anything
reaches the approval queue, rather than trusting the draft blindly."""

VOLUME_PUSHING_PHRASES = [
    "run more campaigns",
    "increase your campaign volume",
    "increase your usage",
    "boost your volume",
    "boost your usage",
    "your usage is down",
    "your campaign count is down",
    "run another campaign to hit",
    "more campaigns this month",
    "ramp up your campaigns",
]


def check_volume_pushing(draft_text: str) -> list[str]:
    """Returns the matched violation phrases — empty means it passed."""
    lowered = draft_text.lower()
    return [phrase for phrase in VOLUME_PUSHING_PHRASES if phrase in lowered]
