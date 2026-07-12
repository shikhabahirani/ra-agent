# AI red-teaming agent

Given the system prompt / instructions / policy of an AI assistant,
`attack.py` runs a live Red Team agent against it: real attack attempts,
real responses, an independent judge call per attempt, and a report backed
by transcripts instead of speculation.

This is a defensive auditing tool. Findings describe vulnerability classes
and short illustrative example inputs to guide hardening - not working
exploits or malware.

`archive/` holds `redteam.py`, an earlier static single-pass version (reads
the prompt as text, one API call, no live target calls, no loop) - superseded
by the live agent but kept for reference.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install anthropic python-dotenv
```

Then create a `.env` file (never commit it - already in `.gitignore`):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```
python attack.py             # live attack, 3 rounds max -> attack_report.md
```

Uses `target.txt` by default. Point it at a different file with
`--target path/to/other_target.txt`. The report prints to the terminal and is
saved to disk (overwritten each run).

## Layout

```
core/
  agent_loop.py       generic tool-use loop (model call -> dispatch -> repeat,
                       capped) - the referee shape: it doesn't know "attack,"
                       "target," or "judge." Any agent that's a system
                       prompt + a tool list + a dispatch function plugs in.
  util.py             MODEL constant, extract_text, read_target
domains/security/
  probe.py            probe_target - the ONE tool shared by every agent in
                       this domain. Red calls it against the original prompt
                       to test attacks; Blue (not built yet) will call the
                       same function against its own patched prompt to
                       verify a fix actually holds.
  judge.py            independent verdict on whether an attempt succeeded -
                       a separate model call that never sees the attacker's
                       intent, so it can't be talked into a false positive
  red_agent.py         Red Team's system prompt, its attempt_attack tool
                       (wraps probe_target with a category+rationale
                       guardrail), and its dispatch - plugs into
                       core/agent_loop.py
attack.py             thin CLI: wires red_agent into the loop, handles I/O
target.txt            sample fictional customer-service bot prompt
attack_report.md       generated output (overwritten each run)
archive/               superseded pre-refactor files, kept for reference
```

`core/` is domain-agnostic on purpose: Blue Team (`domains/security/blue_agent.py`,
not built yet) reuses `agent_loop.py` unchanged, and so would an unrelated
domain like `domains/market/` - only a new `domains/<x>/` module gets added.
The still-missing piece is `core/round_runner.py`, the referee that runs
Red then hands its output to Blue - that's next.
