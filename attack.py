"""
CLI entrypoint for the live Red Team attack agent.

All the actual logic lives elsewhere: core/agent_loop.py is the generic
tool-use loop, domains/security/red_agent.py is this agent's system prompt,
tool schema, and dispatch. This file just wires them together and handles
I/O - reading the target file, printing progress, saving the report.
"""

import argparse
import os
import sys

import anthropic
from dotenv import load_dotenv

from core.agent_loop import run_agent_loop
from core.util import MODEL, read_target
from domains.security.judge import judge_attempt
from domains.security.probe import probe_target
from domains.security.red_agent import (
    AGENT_MAX_TOKENS,
    AGENT_SYSTEM_PROMPT,
    ATTEMPT_ATTACK_TOOL,
    MAX_ROUNDS,
    build_kickoff_messages,
    make_dispatch,
)

load_dotenv()

DEFAULT_TARGET_PATH = "target.txt"
ATTACK_REPORT_PATH = "attack_report.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="Live red-team attack agent against a target AI.")
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET_PATH,
        help=f"Path to the target's system prompt file (default: {DEFAULT_TARGET_PATH})",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: set the ANTHROPIC_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    target_text = read_target(args.target)
    client = anthropic.Anthropic(api_key=api_key)

    print(f"Live-attacking target: {args.target} (budget: {MAX_ROUNDS} attempts)\n")

    result = run_agent_loop(
        client,
        model=MODEL,
        max_tokens=AGENT_MAX_TOKENS,
        system_prompt=AGENT_SYSTEM_PROMPT,
        tools=[ATTEMPT_ATTACK_TOOL],
        initial_messages=build_kickoff_messages(target_text),
        dispatch=make_dispatch(client, target_text, probe_target, judge_attempt),
        max_iterations=MAX_ROUNDS,
    )
    report = result.final_text

    print("\n" + report)

    with open(ATTACK_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nSaved to {ATTACK_REPORT_PATH}")


if __name__ == "__main__":
    main()
