"""
The generic agent loop: call the model, and if it asks for a tool, dispatch
it and hand back a tool_result, repeating until the model stops asking for
tools, the iteration budget runs out, or a terminal tool is called.

This file has no idea what "attack," "target," "judge," or "report" mean -
it works for any agent that is a system prompt, a list of tool schemas, and
a dispatch function. Domain-specific agents (domains/security/red_agent.py,
domains/security/blue_agent.py) plug into this unchanged.
"""

import json
from dataclasses import dataclass
from typing import Callable

import anthropic

from core.util import extract_text

Dispatch = Callable[[str, dict], tuple[bool, str]]


@dataclass
class AgentResult:
    final_text: str
    transcript: str
    structured: dict | None = None


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
    terminal_tools: frozenset[str] = frozenset(),
) -> AgentResult:
    """Run the loop and return the model's final output.

    Two ways an agent can finish:
    - it stops asking for tools and just writes text -> `.final_text`
    - it calls a tool named in `terminal_tools` -> that call's parsed input
      is returned as `.structured`, without being dispatched

    `.transcript` always holds the full raw history (every reasoning turn,
    tool call, and tool result, in order) regardless of how it finished -
    callers that need to see how the agent got there (e.g. a downstream
    agent consuming this one's work) use that.

    `dispatch(tool_name, tool_input)` must return `(is_error, result_text)`.
    Once `max_iterations` non-terminal tool calls have been dispatched, only
    terminal tools are still offered - and if any are, the model is forced
    to call one (`tool_choice: any`) rather than falling back to prose, so a
    caller relying on `.structured` is guaranteed to get it.
    """
    messages = list(initial_messages)
    iterations = 0
    transcript_parts = []

    while True:
        if iterations < max_iterations:
            available_tools = tools
            force_a_tool = False
        else:
            available_tools = [t for t in tools if t["name"] in terminal_tools]
            force_a_tool = bool(available_tools)

        create_kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=available_tools,
        )
        if force_a_tool:
            create_kwargs["tool_choice"] = {"type": "any"}

        response = client.messages.create(**create_kwargs)
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text" and block.text.strip():
                transcript_parts.append(block.text.strip())
            elif block.type == "tool_use":
                transcript_parts.append(
                    f"[called {block.name} with {json.dumps(block.input)}]"
                )

        for block in response.content:
            if block.type == "tool_use" and block.name in terminal_tools:
                return AgentResult(
                    final_text=extract_text(response),
                    transcript="\n\n".join(transcript_parts),
                    structured=block.input,
                )

        if response.stop_reason != "tool_use":
            return AgentResult(
                final_text=extract_text(response),
                transcript="\n\n".join(transcript_parts),
            )

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            iterations += 1
            is_error, result_text = dispatch(block.name, block.input)
            transcript_parts.append(f"[result]\n{result_text}")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})
