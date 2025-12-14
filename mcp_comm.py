import asyncio
import json
import logging
from typing import Any, Dict, Optional, Callable

# Use a module logger (writes to stderr by default) to avoid polluting stdout
logger = logging.getLogger(__name__)


class MCPClient:
    """
    Minimal MCP client wrapper for LLM tool-use.

    Supports a pluggable transport (e.g., HTTP, stdio). Use with
    `MCPRegistry` to resolve servers and call tools.
    """

    def __init__(self, transport: Callable[[str, Dict[str, Any]], Any]):
        self._transport = transport

    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "server_id": server_id,
            "tool": tool_name,
            "arguments": arguments,
        }
        logger.debug("MCP call_tool -> server: %s, tool: %s", server_id, tool_name)
        try:
            logger.debug("payload: %s", json.dumps(payload, ensure_ascii=False))
        except Exception:
            logger.debug("payload: %s", payload)

        raw = None
        try:
            raw = await _maybe_await(self._transport("call_tool", payload))
        except Exception as e:
            logger.exception("MCP transport raised exception")
            raise

        try:
            logger.debug("raw response: %s", json.dumps(raw, ensure_ascii=False))
        except Exception:
            logger.debug("raw response: %s", raw)

        parsed = _ensure_dict(raw)
        try:
            logger.debug("parsed response: %s", json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception:
            logger.debug("parsed response: %s", parsed)

        return parsed

    async def list_tools(self, server_id: str) -> Dict[str, Any]:
        payload = {"server_id": server_id}
        logger.debug("MCP list_tools -> server: %s", server_id)
        try:
            logger.debug("payload: %s", json.dumps(payload, ensure_ascii=False))
        except Exception:
            logger.debug("payload: %s", payload)

        raw = None
        try:
            raw = await _maybe_await(self._transport("list_tools", payload))
        except Exception as e:
            logger.exception("MCP transport raised exception")
            raise

        try:
            logger.debug("raw response: %s", json.dumps(raw, ensure_ascii=False))
        except Exception:
            logger.debug("raw response: %s", raw)

        parsed = _ensure_dict(raw)
        try:
            logger.debug("parsed response: %s", json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception:
            logger.debug("parsed response: %s", parsed)

        return parsed


async def _maybe_await(v):
    if asyncio.iscoroutine(v):
        return await v
    return v


def _ensure_dict(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return {"ok": False, "error": "Invalid JSON response", "raw": v}
    return {"ok": False, "error": "Invalid response type", "raw": v}
