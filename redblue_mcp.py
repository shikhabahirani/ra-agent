"""
CLI entrypoint for one Red -> Blue round using the structured handoff, with
probe_target and judge_attempt discovered from a live MCP server
(tools/mcp_probe_server.py) at startup instead of imported directly.

Identical orchestration to redblue_structured.py - same core/agent_loop.py,
same dispatch logic in red_agent.py/blue_agent.py, same structured Red
report, same round_runner gate. The only thing that differs is where
probe_target/judge_attempt come from: this file spawns the MCP server as a
subprocess, discovers its tools, and wires MCP-backed wrappers into the
exact same dispatch functions redblue_structured.py wires direct-import
functions into.
"""

import argparse
import json
import os
import sys

import anthropic
from dotenv import load_dotenv

from core.agent_loop import run_agent_loop
from core.round_runner import run_round
from core.tool_registry import connect_mcp_registry
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
MCP_SERVER_SCRIPT = "tools/mcp_probe_server.py"
RED_REPORT_PATH = "redblue_mcp_red_report.json"
BLUE_REPORT_PATH = "redblue_mcp_blue_report.md"


def has_confirmed_vulnerabilities(red_result) -> bool:
    return len(red_result.structured.get("vulnerabilities", [])) > 0


def _mcp_probe_fn(registry):
    def probe_target(client, target_system_prompt, message):
        return registry.call("probe_target", {"system_prompt": target_system_prompt, "message": message})

    return probe_target


def _mcp_judge_fn(registry):
    def judge_attempt(client, target_system_prompt, message, target_response):
        return registry.call(
            "judge_attempt",
            {
                "target_system_prompt": target_system_prompt,
                "message": message,
                "target_response": target_response,
            },
        )

    return judge_attempt


def main() -> None:
    parser = argparse.ArgumentParser(description="One Red -> Blue round, structured handoff, MCP-discovered tools.")
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

    print(f"Connecting to MCP server ({MCP_SERVER_SCRIPT})...")
    with connect_mcp_registry(sys.executable, [MCP_SERVER_SCRIPT]) as registry:
        print(f"Discovered tools via MCP: {', '.join(registry.names())}\n")

        probe_fn = _mcp_probe_fn(registry)
        judge_fn = _mcp_judge_fn(registry)

        def run_red():
            print(f"=== RED: attacking {args.target} via MCP (budget: {RED_MAX_ROUNDS} attempts) ===\n")
            return run_agent_loop(
                client,
                model=MODEL,
                max_tokens=RED_MAX_TOKENS,
                system_prompt=RED_SYSTEM_PROMPT,
                tools=[ATTEMPT_ATTACK_TOOL, SUBMIT_RED_REPORT_TOOL],
                initial_messages=build_red_kickoff(target_text),
                dispatch=make_red_dispatch(client, target_text, probe_fn, judge_fn),
                max_iterations=RED_MAX_ROUNDS,
                terminal_tools=frozenset({"submit_red_report"}),
            )

        def run_blue(red_result):
            print(f"\n=== BLUE: patching via MCP (budget: {BLUE_MAX_ROUNDS} verifications) ===\n")
            return run_agent_loop(
                client,
                model=MODEL,
                max_tokens=BLUE_MAX_TOKENS,
                system_prompt=BLUE_SYSTEM_PROMPT,
                tools=[VERIFY_PATCH_TOOL],
                initial_messages=build_kickoff_messages_from_structured(target_text, red_result.structured),
                dispatch=make_blue_dispatch(client, probe_fn),
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
