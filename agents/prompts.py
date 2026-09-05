"""Loads versioned prompt templates from /prompts — never inline strings
in agent code (BUILD-PROMPT.md §11). Uses string.Template ($identifier)
rather than str.format() so a prompt can show literal JSON braces in an
example without every one of them needing escaping."""

from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str, **kwargs) -> str:
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    return Template(text).substitute(**kwargs)
