"""The live victim: wraps a target system prompt and answers as that AI would."""

import anthropic

from core.util import MODEL, extract_text

TARGET_MAX_TOKENS = 1024


def send_message_to_target(client: anthropic.Anthropic, target_system_prompt: str, message: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=TARGET_MAX_TOKENS,
        system=target_system_prompt,
        messages=[{"role": "user", "content": message}],
    )
    return extract_text(response)
