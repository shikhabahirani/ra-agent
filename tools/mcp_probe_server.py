"""
MCP server exposing probe_target and judge_attempt as discoverable tools.

Thin wrapper only - no reimplementation. Both tools call straight through
to the real implementations in domains.security.probe and
domains.security.judge, unchanged. This process owns its own Anthropic
client and loads its own .env, since it runs as a separate subprocess from
whatever agent discovers it over MCP.

Run standalone: python3 tools/mcp_probe_server.py
(Also spawned automatically by core.tool_registry.connect_mcp_registry.)
"""

import os
import sys
import json
import anthropic
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from domains.security.judge import judge_attempt as _judge_attempt
from domains.security.probe import probe_target as _probe_target

load_dotenv(os.path.join(REPO_ROOT, ".env"))

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

mcp = FastMCP("red-blue-probe-server")


@mcp.tool()
def probe_target(system_prompt: str, message: str) -> str:
    """Simulate the target chatbot: send `message` to a live Claude call
    running under `system_prompt`, return its real response."""
    return _probe_target(_client, system_prompt, message)


@mcp.tool()
def judge_attempt(target_system_prompt: str, message: str, target_response: str) -> dict:
    """Independently judge whether an attack attempt against the target
    actually succeeded."""
    return _judge_attempt(_client, target_system_prompt, message, target_response)


@mcp.tool()
def check_response_for_pii(response: str) -> str:
    """Check if a response contains potential PII like emails or phone numbers."""
    import re
    findings = []
    if re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', response):
        findings.append("Email address detected")
    if re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', response):
        findings.append("Phone number detected")
    return json.dumps({"pii_found": len(findings) > 0, "findings": findings})


if __name__ == "__main__":
    mcp.run(transport="stdio")
