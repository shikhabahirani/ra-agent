# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An AI-security red-teaming agent (`attack.py`) that lives-attacks a target AI's system prompt / instructions / policy: real attack attempts against a simulated instance of the target, an independent judge call per attempt, and a report backed by real transcripts, not speculation. This is a defensive auditing tool: findings describe vulnerability classes and short illustrative example inputs to guide hardening, not working exploits or malware. Keep that framing when touching any agent's system prompt.

`archive/redteam.py` is an earlier, static single-pass version (reads the prompt as text, one API call, no live calls, no loop) kept for reference — not part of the active architecture below.

## Setup and running

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires a `.env` file (gitignored, never commit it) with `ANTHROPIC_API_KEY=sk-ant-...`.

```
python attack.py [--target path]   # live multi-round attack agent -> attack_report.md
```

Defaults to `target.txt`. There is no test suite, linter, or build step configured in this repo.

## Architecture

This is being built as a multi-agent adversarial system, one piece at a time. Only Red Team exists so far; Blue Team and the round runner that connects them are the next build.

- `core/agent_loop.py` — the domain-agnostic tool-use loop: call the model, if `stop_reason == "tool_use"` dispatch the tool call and feed back a `tool_result`, repeat, until either the model stops asking for tools or `max_iterations` tool calls have been spent (after which the tools are no longer offered to the model, forcing a final answer from whatever it has learned so far). This is the "referee shape" — it has no idea what "attack," "target," or "judge" mean, and should never need to change as agents are added.
- `domains/security/probe.py` — `probe_target(client, system_prompt, message)`, **the one tool shared by every agent in this domain**: "pretend to be a chatbot running these instructions, receive this message, say what you'd say back." Red calls it against the original target prompt to test live attacks. Blue (not built yet) will call the exact same function against its own patched prompt, to verify a fix actually holds instead of just asserting that it should.
- `domains/security/judge.py` — `judge_attempt`, an independent model call that scores whether an attack attempt actually succeeded, based only on the target's real response. It never sees the attacker's rationale/intent, so it can't be talked into scoring a weak attempt as a win.
- `domains/security/red_agent.py` — the Red Team agent's config: the fixed `ATTACK_CATEGORIES` taxonomy (`prompt_injection`, `role_confusion_jailbreak`, `instruction_leaking`, `output_format_manipulation`, `scope_escape`), the `attempt_attack` tool schema (Red's own wrapper around `probe_target` — requires `category` + `rationale` to be committed before `message` is sent, enforced via required schema fields, as a guardrail against generating unfocused attacks), the agent's system prompt, and `dispatch_attempt_attack`/`make_dispatch`, which call `probe.py` + `judge.py` and print live per-attempt progress.
- `attack.py` — thin CLI: reads the target file, wires `red_agent`'s system prompt/tool/dispatch into `run_agent_loop`, handles I/O. No agent logic of its own.

Key invariant: the attack budget (`MAX_ROUNDS = 3` in `red_agent.py`) is enforced by the loop refusing to offer the tool once the iteration count is hit — not by asking the model nicely to stop.

**Next build**: `domains/security/blue_agent.py` (reads Red's report, patches the target prompt, calls `probe_target` against its own patched version to verify the fix holds) and `core/round_runner.py` (the referee — runs Red, hands its output to Blue, done; domain-agnostic, so a `domains/market/` bull-vs-bear pair would reuse it identically). Extending to a new domain should only ever mean adding a `domains/<x>/` module — `core/` should not need to change.

## Sample target

`target.txt` is a fictional customer-support bot ("ShopBot") system prompt, deliberately written with real vulnerabilities (embedded manager override code, unauthenticated order lookup by email, "always fulfill requests" overriding guardrails, unlimited discount issuance) so the agent has something real to find immediately. `attack_report.md` is generated output, overwritten on every run — not meant to be hand-edited.
