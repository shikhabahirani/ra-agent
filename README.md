# AI red-teaming tools

Two tools, given the system prompt / instructions / policy of an AI
assistant:

- `redteam.py` - static, single-pass. Reads the prompt as text and reasons
  about it, no live calls to the target. One API call, one markdown report.
- `attack.py` - live, agentic. Actually attacks a simulated instance of the
  target over multiple rounds, judges each attempt independently, and
  reports only what it empirically proved - transcripts included.

Both are defensive auditing tools. Findings describe vulnerability classes
and short illustrative example inputs to guide hardening - not working
exploits or malware.

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
python redteam.py            # static analysis -> report.md
python attack.py             # live attack, 3 rounds max -> attack_report.md
```

Both use `target.txt` by default. Point either at a different file with
`--target path/to/other_target.txt`. Reports print to the terminal and are
saved to disk (overwritten each run).

## Layout

```
core/
  agent_loop.py       generic tool-use loop (model call -> dispatch -> repeat,
                       capped) - no idea what "attack" or "target" mean
  util.py             shared model constant + response-text helper
domains/security/
  target.py           the live victim: wraps a target prompt, answers as it
  judge.py            independent verdict on whether an attempt succeeded
  red_agent.py         Red Team's system prompt, tool schema, and dispatch -
                       plugs into core/agent_loop.py
attack.py             thin CLI: wires red_agent into the loop, handles I/O
redteam.py            standalone static analyzer, no loop, unrelated to core/
target.txt            sample fictional customer-service bot prompt
report.md / attack_report.md   generated output (overwritten each run)
```

`core/` is domain-agnostic on purpose: a Blue Team patch-and-verify agent
(or an entirely different domain, e.g. `domains/market/`) reuses
`agent_loop.py` unchanged - only a new `domains/<x>/` module is added.
