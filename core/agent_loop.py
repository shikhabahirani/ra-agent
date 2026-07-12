"""
The generic agent loop: call the model, and if it asks for a tool, dispatch
it and hand back a tool_result, repeating until the model stops asking for
tools or the iteration budget runs out.

This file has no idea what "attack," "target," or "judge" mean - it works
for any agent that is a system prompt, a list of tool schemas, and a
dispatch function. Domain-specific agents (domains/security/red_agent.py,
and later blue_agent.py) plug into this unchanged.
"""

from typing import Callable

import anthropic

from core.util import extract_text

Dispatch = Callable[[str, dict], tuple[bool, str]]


def run_agent_loop(
    client: anthropic.Anthropic,
    *,
    model: str,
    max_tokens: int,
    system_prompt: str,
    tools: list[dict],
    initial_messages: list[dict],
    dispatch: Dispatch,
    max_iterations: int,
) -> str:
    """Run the loop and return the model's final text output.

    `dispatch(tool_name, tool_input)` must return `(is_error, result_text)`.
    Once `max_iterations` tool calls have been dispatched, the tools are no
    longer offered to the model, forcing it to produce its final text from
    whatever it has learned so far.
    """
    messages = list(initial_messages)
    iterations = 0

    while True:
        available_tools = tools if iterations < max_iterations else []
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=available_tools,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return extract_text(response)

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            iterations += 1
            is_error, result_text = dispatch(block.name, block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})
