"""
probe_target - the one tool shared by every agent in this domain.

It's "pretend to be a chatbot running these instructions, receive this
message, say what you'd say back." Red calls it against the original,
unpatched system prompt to test live attacks. Blue (once it exists) calls
the exact same function against its own patched system prompt, to verify a
fix actually holds instead of just asserting that it should.
"""

import anthropic

from core.util import MODEL, extract_text

PROBE_MAX_TOKENS = 1024


def probe_target(client: anthropic.Anthropic, system_prompt: str, message: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=PROBE_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )
    return extract_text(response)
