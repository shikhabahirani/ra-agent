"""
CLI entrypoint for one Red -> Blue round using the structured handoff
(FIX 1-3): Red files a typed submit_red_report instead of free text, Blue
receives only the parsed JSON (never Red's raw transcript), and
core.round_runner gates Blue on a real Python check - if Red confirmed zero
vulnerabilities, Blue never runs.

This is the "after" counterpart to redblue.py's "before" - same target, same
attack mechanics, different handoff. Run both against the same target.txt to
compare.
"""

import argparse
import json
import os
import sys

import anthropic
from dotenv import load_dotenv

from core.agent_loop import run_agent_loop
from core.round_runner import run_round
from core.util import MODEL, read_target
from domains.security.blue_agent import (
    AGENT_MAX_TOKENS as BLUE_MAX_TOKENS,
    MAX_ROUNDS as BLUE_MAX_ROUNDS,
    STRUCTURED_AGENT_SYSTEM_PROMPT as BLUE_SYSTEM_PROMPT,
    VERIFY_PATCH_TOOL,
    build_kickoff_messages_from_structured,
    make_dispatch as make_blue_dispatch,
)
from domains.security.red_agent import (
    AGENT_MAX_TOKENS as RED_MAX_TOKENS,
    ATTEMPT_ATTACK_TOOL,
    MAX_ROUNDS as RED_MAX_ROUNDS,
    STRUCTURED_AGENT_SYSTEM_PROMPT as RED_SYSTEM_PROMPT,
    SUBMIT_RED_REPORT_TOOL,
    build_kickoff_messages as build_red_kickoff,
    make_dispatch as make_red_dispatch,
)

load_dotenv()

DEFAULT_TARGET_PATH = "target.txt"
RED_REPORT_PATH = "redblue_structured_red_report.json"
BLUE_REPORT_PATH = "redblue_structured_blue_report.md"


def has_confirmed_vulnerabilities(red_result) -> bool:
    return len(red_result.structured.get("vulnerabilities", [])) > 0


def main() -> None:
    parser = argparse.ArgumentParser(description="One Red -> Blue round, structured handoff.")
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
        print(f"=== RED: attacking {args.target} (budget: {RED_MAX_ROUNDS} attempts, structured report) ===\n")
        return run_agent_loop(
            client,
            model=MODEL,
            max_tokens=RED_MAX_TOKENS,
            system_prompt=RED_SYSTEM_PROMPT,
            tools=[ATTEMPT_ATTACK_TOOL, SUBMIT_RED_REPORT_TOOL],
            initial_messages=build_red_kickoff(target_text),
            dispatch=make_red_dispatch(client, target_text),
            max_iterations=RED_MAX_ROUNDS,
            terminal_tools=frozenset({"submit_red_report"}),
        )

    def run_blue(red_result):
        print(f"\n=== BLUE: patching from Red's structured report (budget: {BLUE_MAX_ROUNDS} verifications) ===\n")
        return run_agent_loop(
            client,
            model=MODEL,
            max_tokens=BLUE_MAX_TOKENS,
            system_prompt=BLUE_SYSTEM_PROMPT,
            tools=[VERIFY_PATCH_TOOL],
            initial_messages=build_kickoff_messages_from_structured(target_text, red_result.structured),
            dispatch=make_blue_dispatch(client),
            max_iterations=BLUE_MAX_ROUNDS,
        )

    red_result, blue_result = run_round(
        run_red,
        run_blue,
        should_run_b=has_confirmed_vulnerabilities,
        skip_message="\nRed found 0 confirmed vulnerabilities. Skipping Blue Team.",
    )

    n_vulns = len(red_result.structured.get("vulnerabilities", []))
    n_failed = len(red_result.structured.get("failed_attempts", []))
    print(f"\n=== RED STRUCTURED REPORT ===\n")
    print(f"Confirmed vulnerabilities: {n_vulns}")
    print(f"Failed attempts: {n_failed}")
    for v in red_result.structured.get("vulnerabilities", []):
        print(f"  [{v.get('id')}] {v.get('title')} ({v.get('severity')}, {v.get('category')})")
    print(f"\nSummary: {red_result.structured.get('summary', '')}")

    with open(RED_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(red_result.structured, f, indent=2)
    print(f"\nRed's structured report saved to {RED_REPORT_PATH}")

    if blue_result is None:
        print("No Blue report - Blue did not run.")
        return

    print("\n=== BLUE FINAL REPORT ===\n")
    print(blue_result.final_text)

    with open(BLUE_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(blue_result.final_text)
    print(f"\nBlue's report saved to {BLUE_REPORT_PATH}")


if __name__ == "__main__":
    main()
