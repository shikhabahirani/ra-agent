"""Shared, domain-agnostic helpers used by every agent."""

import sys

import anthropic

MODEL = "claude-haiku-4-5-20251001"


def extract_text(response: anthropic.types.Message) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()


def read_target(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: target file not found: {path}", file=sys.stderr)
        sys.exit(1)
