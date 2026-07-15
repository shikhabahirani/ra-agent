"""
Generic registry mapping a tool name to a synchronous callable. Tool
sources are pluggable - a registry can hold plain local functions, or
tools backed by a remote MCP server. Callers only ever see
`registry.call(name, tool_input)`; they don't know or care where the tool
actually lives.

MCP's client API is async top to bottom; the rest of this codebase
(core/agent_loop.py, every dispatch function) is sync top to bottom.
Rather than making everything async to accommodate one dependency,
connect_mcp_registry runs a single background thread that owns a
persistent asyncio event loop and MCP session for as long as the `with`
block is open - one subprocess, one session, reused for every call.
`registry.call()` just hands a coroutine to that loop and blocks for the
result, so callers never touch asyncio themselves.
"""

import asyncio
import json
import threading
from contextlib import contextmanager
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable[[dict], Any]] = {}

    def register(self, name: str, fn: Callable[[dict], Any]) -> None:
        self._tools[name] = fn

    def call(self, name: str, tool_input: dict) -> Any:
        if name not in self._tools:
            raise KeyError(f"No tool registered for '{name}'")
        return self._tools[name](tool_input)

    def names(self) -> list[str]:
        return sorted(self._tools)


class _MCPSession:
    """Owns a background thread running a persistent event loop, a live
    MCP subprocess, and a ClientSession connected to it over stdio."""

    def __init__(self, command: str, args: list[str]):
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._session: ClientSession | None = None
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, args=(command, args), daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            raise self._error

    def _run(self, command: str, args: list[str]) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main(command, args))
        except Exception as exc:
            self._error = exc
            self._ready.set()

    async def _main(self, command: str, args: list[str]) -> None:
        server_params = StdioServerParameters(command=command, args=args)
        self._stop = asyncio.Event()
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                self._ready.set()
                await self._stop.wait()

    def list_tools(self):
        future = asyncio.run_coroutine_threadsafe(self._session.list_tools(), self._loop)
        return future.result()

    def call_tool(self, name: str, arguments: dict):
        future = asyncio.run_coroutine_threadsafe(self._session.call_tool(name, arguments), self._loop)
        return future.result()

    def close(self) -> None:
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout=10)


def _extract_result(result) -> Any:
    text = "".join(
        block.text for block in result.content if getattr(block, "type", None) == "text"
    )
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool call failed: {text}")

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        # MCP's structured-output schema must be a JSON object at the top
        # level, so FastMCP wraps a tool that returns a scalar (str, int,
        # bool, ...) in {"result": <value>}. Unwrap that convention here so
        # a tool declared `-> str` actually hands callers a str.
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


def _make_wrapper(session: _MCPSession, tool_name: str) -> Callable[[dict], Any]:
    def wrapper(tool_input: dict) -> Any:
        result = session.call_tool(tool_name, tool_input)
        return _extract_result(result)

    return wrapper


@contextmanager
def connect_mcp_registry(command: str, args: list[str]):
    """Spawn an MCP server subprocess, discover its tools, and yield a
    ToolRegistry with one synchronous wrapper per discovered tool name."""
    session = _MCPSession(command, args)
    try:
        registry = ToolRegistry()
        for tool in session.list_tools().tools:
            registry.register(tool.name, _make_wrapper(session, tool.name))
        yield registry
    finally:
        session.close()
