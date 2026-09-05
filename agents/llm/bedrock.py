"""Real provider: Claude via Amazon Bedrock (BUILD-PROMPT.md §16.6's
resolved model-access assumption). Authored but not exercised against a
live API — this environment has no AWS credentials, the same situation
as /infra's Terraform. Review against the actual Bedrock Converse API
response shape before pointing a real agent at it.

Imports boto3 lazily so nothing outside this one module needs the AWS
SDK installed to run /agents' pure logic or its tests."""

import json
import time

from agents.llm.base import LLMProvider, LLMResponse, LLMUsage

# Rough on-demand per-token pricing for cost logging (§11a: "every call
# logs ... cost to the action record"). These drift — treat as an
# estimate, not a billing source of truth, and update when Bedrock's
# pricing page changes.
_COST_PER_1K_INPUT_TOKENS_USD = 0.003
_COST_PER_1K_OUTPUT_TOKENS_USD = 0.015


class BedrockClaudeProvider(LLMProvider):
    def __init__(self, model_id: str, region: str = "us-east-1"):
        self.model_id = model_id
        self.region = region
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import boto3  # local import — see module docstring

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def complete(
        self, *, system: str, prompt: str, response_schema: dict | None = None, max_tokens: int = 1024
    ) -> LLMResponse:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        if response_schema is not None:
            # Constrained via tool-forcing: one tool matching the schema,
            # forced choice, so Claude always returns the structured
            # object instead of free text. Standard Bedrock/Anthropic
            # pattern — verify field names against the live API on first
            # real use.
            body["tools"] = [
                {
                    "name": "respond",
                    "description": "Return the structured response.",
                    "input_schema": response_schema,
                }
            ]
            body["tool_choice"] = {"type": "tool", "name": "respond"}

        start = time.monotonic()
        raw = self.client.invoke_model(modelId=self.model_id, body=json.dumps(body))
        latency_ms = (time.monotonic() - start) * 1000
        payload = json.loads(raw["body"].read())

        parsed = None
        if response_schema is not None:
            tool_use = next(
                (block for block in payload.get("content", []) if block.get("type") == "tool_use"), None
            )
            if tool_use is None:
                raise ValueError("Bedrock response had no tool_use block for a schema-constrained call")
            parsed = tool_use["input"]
            text = json.dumps(parsed)
        else:
            text_block = next(
                (block for block in payload.get("content", []) if block.get("type") == "text"), None
            )
            text = text_block["text"] if text_block else ""

        usage = payload.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost_usd = (
            input_tokens / 1000 * _COST_PER_1K_INPUT_TOKENS_USD
            + output_tokens / 1000 * _COST_PER_1K_OUTPUT_TOKENS_USD
        )

        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=LLMUsage(
                provider="bedrock",
                model=self.model_id,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            ),
        )
