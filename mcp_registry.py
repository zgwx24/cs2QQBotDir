import os
import json
from typing import Any, Dict, Optional, Callable, List


class MCPRegistry:
    """
    Simple registry for MCP servers.

    Stores per-server transport config. Each entry must provide a callable
    transport with signature transport(action: str, payload: Dict) -> Any.

    Example HTTP transport factory is provided.
    """

    def __init__(self):
        self._servers: Dict[str, Dict[str, Any]] = {}

    def register(self, server_id: str, transport: Callable[[str, Dict[str, Any]], Any], meta: Optional[Dict[str, Any]] = None):
        self._servers[server_id] = {
            "transport": transport,
            "meta": meta or {},
        }

    def get_transport(self, server_id: str) -> Callable[[str, Dict[str, Any]], Any]:
        cfg = self._servers.get(server_id)
        if not cfg:
            raise KeyError(f"MCP server not registered: {server_id}")
        return cfg["transport"]

    def list(self) -> Dict[str, Dict[str, Any]]:
        return self._servers.copy()


def build_http_transport(base_url: str, api_key: Optional[str] = None):
    import requests

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    def transport(action: str, payload: Dict[str, Any]):
        url = f"{base_url.rstrip('/')}/mcp/{action}"
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    return transport


# Optional: bootstrap from environment for convenience
# Example envs per server: MCP_WEATHER_URL, MCP_WEATHER_KEY
# Register known servers here so qqbot.py can import and use directly

def load_registry_from_file(config_path: str) -> MCPRegistry:
    """
    Load MCP servers from a JSON file.

    Expected format:
    {
      "servers": [
        {"id": "weather", "type": "http", "base_url": "http://host", "api_key": "..."}
      ]
    }
    """
    reg = MCPRegistry()
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    servers: List[Dict[str, Any]] = data.get("servers", [])
    for s in servers:
        sid = s.get("id")
        stype = s.get("type", "http")
        if not sid:
            continue
        if stype == "http":
            base_url = s.get("base_url")
            api_key = s.get("api_key")
            if base_url:
                reg.register(sid, build_http_transport(base_url, api_key), meta={"type": "http"})
    return reg


def default_registry(config_path: Optional[str] = None) -> MCPRegistry:
    """Create a registry from a file if provided; otherwise empty."""
    if config_path and os.path.exists(config_path):
        return load_registry_from_file(config_path)
    return MCPRegistry()
