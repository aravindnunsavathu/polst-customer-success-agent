"""Loads agents/llm/config/model_config.yaml and builds the right
LLMProvider for a given agent task. Pure file I/O + a lazy import of
boto3 only when "bedrock" is actually selected — nothing here requires
AWS credentials unless the config asks for them."""

from functools import lru_cache
from pathlib import Path

import yaml

from agents.llm.base import LLMProvider

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "model_config.yaml"


@lru_cache(maxsize=1)
def _raw_config(path: str | None = None) -> dict:
    with open(path or DEFAULT_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def provider_for(agent_task: str, config_path: str | None = None) -> LLMProvider:
    raw = _raw_config(config_path)
    spec = raw.get("agents", {}).get(agent_task, raw["default"])
    provider_name = spec["provider"]

    if provider_name == "heuristic":
        from agents.llm.fake import HeuristicLLMProvider

        return HeuristicLLMProvider()
    if provider_name == "bedrock":
        from agents.llm.bedrock import BedrockClaudeProvider

        return BedrockClaudeProvider(model_id=spec["model"])
    raise ValueError(f"unknown provider {provider_name!r} for agent task {agent_task!r}")
