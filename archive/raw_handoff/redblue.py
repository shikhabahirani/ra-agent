"""
CLI entrypoint for one full Red -> Blue round.

Red attacks the live target and produces a raw transcript. core.round_runner
hands that transcript to Blue, who reads it, patches the target's system
prompt, and verifies the patch itself. One round: no Red re-attack of the
patch yet (see core/round_runner.py).
"""

import argparse
import os
import sys

import anthropic
from dotenv import load_dotenv

from core.agent_loop import run_agent_loop
from core.round_runner import run_round
from core.util import MODEL, read_target
from domains.security.blue_agent import (
    AGENT_MAX_TOKENS as BLUE_MAX_TOKENS,
    AGENT_SYSTEM_PROMPT as BLUE_SYSTEM_PROMPT,
    MAX_ROUNDS as BLUE_MAX_ROUNDS,
    VERIFY_PATCH_TOOL,
    build_kickoff_messages as build_blue_kickoff,
    make_dispatch as make_blue_dispatch,
)
from domains.security.judge import judge_attempt
from domains.security.probe import probe_target
from domains.security.red_agent import (
    AGENT_MAX_TOKENS as RED_MAX_TOKENS,
    AGENT_SYSTEM_PROMPT as RED_SYSTEM_PROMPT,
    ATTEMPT_ATTACK_TOOL,
    MAX_ROUNDS as RED_MAX_ROUNDS,
    build_kickoff_messages as build_red_kickoff,
    make_dispatch as make_red_dispatch,
)

load_dotenv()

DEFAULT_TARGET_PATH = "target.txt"
RED_TRANSCRIPT_PATH = "redblue_red_transcript.md"
BLUE_REPORT_PATH = "redblue_blue_report.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="One Red -> Blue round against a target AI.")
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

    def run_red():
        print(f"=== RED: attacking {args.target} (budget: {RED_MAX_ROUNDS} attempts) ===\n")
        return run_agent_loop(
            client,
            model=MODEL,
            max_tokens=RED_MAX_TOKENS,
            system_prompt=RED_SYSTEM_PROMPT,
            tools=[ATTEMPT_ATTACK_TOOL],
            initial_messages=build_red_kickoff(target_text),
            dispatch=make_red_dispatch(client, target_text, probe_target, judge_attempt),
            max_iterations=RED_MAX_ROUNDS,
        )

    def run_blue(red_result):
        print(f"\n=== BLUE: patching from Red's raw transcript (budget: {BLUE_MAX_ROUNDS} verifications) ===\n")
        return run_agent_loop(
            client,
            model=MODEL,
            max_tokens=BLUE_MAX_TOKENS,
            system_prompt=BLUE_SYSTEM_PROMPT,
            tools=[VERIFY_PATCH_TOOL],
            initial_messages=build_blue_kickoff(target_text, red_result.transcript),
            dispatch=make_blue_dispatch(client, probe_target),
            max_iterations=BLUE_MAX_ROUNDS,
        )

    red_result, blue_result = run_round(run_red, run_blue)

    print("\n=== RED FINAL REPORT ===\n")
    print(red_result.final_text)
    print("\n=== BLUE FINAL REPORT ===\n")
    print(blue_result.final_text)

    with open(RED_TRANSCRIPT_PATH, "w", encoding="utf-8") as f:
        f.write(red_result.transcript)
    with open(BLUE_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(blue_result.final_text)
    print(f"\nRed's raw transcript saved to {RED_TRANSCRIPT_PATH}")
    print(f"Blue's report saved to {BLUE_REPORT_PATH}")


if __name__ == "__main__":
    main()
