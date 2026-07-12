"""Shared, domain-agnostic helpers used by every agent."""

import anthropic

MODEL = "claude-sonnet-5"


def extract_text(response: anthropic.types.Message) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()
