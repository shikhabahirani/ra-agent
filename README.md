# AI red-teaming agent

Given the system prompt / instructions / policy of an AI assistant, this
runs a live Red Team agent against it - real attack attempts, real
responses, an independent judge call per attempt - and optionally a Blue
Team agent that patches confirmed findings and verifies the fix against a
live instance. Reports are backed by transcripts and evidence, not
speculation.

This is a defensive auditing tool. Findings describe vulnerability classes
and short illustrative example inputs to guide hardening - not working
exploits or malware.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then create a `.env` file (never commit it - already in `.gitignore`):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

Three entrypoints, all default to `target.txt` (override with `--target path`):

```
python attack.py               # Red only, standalone -> attack_report.md
python redblue_structured.py   # Red -> Blue, one round, direct-import tools
python redblue_mcp.py          # same round, tools discovered live via MCP
```

`redblue_structured.py` and `redblue_mcp.py` produce identical orchestration
- same agents, same structured JSON handoff, same round-runner gate (Blue
never runs if Red confirmed nothing). They differ only in where
`probe_target`/`judge_attempt` come from.

## Why MCP for two of the tools

`red_agent.py`/`blue_agent.py` never import `probe_target`/`judge_attempt`
themselves - `dispatch_attempt_attack`/`make_dispatch` take them as
`probe_fn`/`judge_fn` parameters, and each entrypoint decides where those
come from:

- `redblue_structured.py` imports the real functions directly and passes
  them in.
- `redblue_mcp.py` spawns `tools/mcp_probe_server.py` as a subprocess,
  discovers its tools at runtime, and passes in MCP-backed wrappers that
  call the identical underlying functions over the MCP protocol instead.

What MCP buys over a direct import: the two live-call tools become a
separate, independently runnable process - discoverable by any agent (or
any language) that speaks MCP, not just this codebase. Adding or changing a
tool means editing the server once, not every agent that calls it. The cost
is real complexity - MCP's client is async, this codebase is sync
end-to-end, so `core/tool_registry.py` bridges the two with a background
thread holding a persistent event loop and session. That cost only pays for
itself once more than one consumer needs these tools, which is why
`redblue_structured.py` stays as the simpler direct-import baseline rather
than being replaced.

## Layout

```
core/
  agent_loop.py        generic tool-use loop: model call -> dispatch ->
                        repeat, capped, with optional terminal tools for
                        structured output. Knows nothing about "attack,"
                        "judge," or "MCP."
  round_runner.py       the referee: runs agent A, then agent B on A's
                        result, gated by an optional caller-supplied
                        predicate. Domain-agnostic.
  tool_registry.py      generic name -> callable registry, backed by either
                        plain local functions or an MCP-discovered server -
                        dispatch code never knows which.
  util.py               MODEL constant, extract_text, read_target
domains/security/
  probe.py              probe_target - the live victim simulator
  judge.py               judge_attempt - independent verdict via a forced
                        tool call, never sees the attacker's intent
  red_agent.py           Red's taxonomy, attempt_attack tool, structured
                        submit_red_report tool, system prompt, dispatch -
                        takes probe_fn/judge_fn as parameters
  blue_agent.py          Blue's patch-and-verify agent, same
                        parameter-injection pattern for probe_fn
tools/
  mcp_probe_server.py    FastMCP server exposing probe_target and
                        judge_attempt (plus an experimental
                        check_response_for_pii, not yet wired into any
                        agent) as MCP tools - thin wrapper, reuses the real
                        functions unchanged
attack.py                standalone Red entrypoint
redblue_structured.py    Red -> Blue entrypoint, direct-import tools
redblue_mcp.py           Red -> Blue entrypoint, MCP-discovered tools
target.txt               sample vulnerable customer-service bot prompt
archive/
  redteam.py              earliest version: static single-pass, no loop
  raw_handoff/             pre-structured-JSON Red -> Blue (Blue read Red's
                        raw transcript instead of typed JSON)
experiments/              self-contained experiments, don't affect core
```

## Future work

- Blue's free-text summary can overclaim verification coverage when its verify budget is exhausted. Next fix: force verification status per vulnerability through a structured enum (VERIFIED / UNVERIFIED_BUDGET_EXHAUSTED) instead of relying on prose honesty.
- Red's submit_red_report tool call can omit fields marked "required" in its schema (observed: summary missing entirely) - the API doesn't guarantee a generated tool call actually satisfies its own required list. Next fix: validate required fields client-side after the tool call and retry/error on an incomplete report, instead of trusting the schema was honored.
