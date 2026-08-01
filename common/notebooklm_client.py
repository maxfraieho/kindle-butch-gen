"""
notebooklm_client.py — Python client for NotebookLM MCP streamable-HTTP server.

Protocol: stateful streamable-HTTP MCP (not standard REST).
  1. POST /mcp with initialize  ->  response header mcp-session-id:<hex>
  2. POST notifications/initialized  (no response expected)
  3. All subsequent requests include mcp-session-id header
  4. Responses are SSE-framed:  event: message\\ndata: {...}\\n\\n
  5. Headers: Content-Type: application/json, Accept: application/json, text/event-stream

Session is lazy-initialized on first call and reused.  On "invalid session" (400)
the client re-initializes once automatically and retries.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import requests


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class NotebookLMConnectionError(Exception):
    """Raised on network / transport failures."""


class NotebookLMToolError(Exception):
    """Raised when MCP returns a JSON-RPC error or an empty tool result."""


# ---------------------------------------------------------------------------
# SSE parser
# ---------------------------------------------------------------------------

def _parse_sse(body: str) -> dict:
    """Extract JSON payload from SSE-framed response body.

    Expected format::

        event: message
        data: {"jsonrpc": "2.0", ...}

    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            data_str = stripped[len("data:"):].strip()
            if data_str:
                return json.loads(data_str)
    raise NotebookLMConnectionError(
        f"No 'data:' line found in SSE response body: {body[:300]!r}"
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class NotebookLMClient:
    """Client for the NotebookLM MCP streamable-HTTP server.

    Args:
        base_url: Full URL to the MCP endpoint (e.g. http://host:8002/mcp).
        timeout:  Per-request HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://192.168.3.184:8002/mcp",
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session_id: str | None = None
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """Perform the MCP handshake: initialize + notifications/initialized."""
        payload = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "notebooklm_client", "version": "1.0"},
            },
        }
        try:
            resp = self._http.post(self.base_url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NotebookLMConnectionError(f"initialize failed: {exc}") from exc

        if resp.status_code != 200:
            raise NotebookLMConnectionError(
                f"initialize returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        session_id = resp.headers.get("mcp-session-id")
        if not session_id:
            raise NotebookLMConnectionError(
                "Server did not return mcp-session-id header in initialize response"
            )

        self._session_id = session_id
        self._http.headers["mcp-session-id"] = session_id

        # Notify server that client is ready (fire-and-forget)
        notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        try:
            self._http.post(self.base_url, json=notif, timeout=self.timeout)
        except requests.RequestException:
            pass  # best-effort; not critical

    def _ensure_session(self) -> None:
        if self._session_id is None:
            self._initialize()

    # ------------------------------------------------------------------
    # Core transport
    # ------------------------------------------------------------------

    def _post_rpc(self, method: str, params: dict) -> dict:
        """POST a JSON-RPC request, parse SSE response, return result dict.

        Retries up to 3 times on transient network errors.
        On HTTP 400 "session" error, re-initializes and retries once.
        """
        self._ensure_session()

        max_retries = 3
        for attempt in range(max_retries):
            payload = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": method,
                "params": params,
            }
            try:
                resp = self._http.post(
                    self.base_url, json=payload, timeout=self.timeout
                )
            except requests.RequestException as exc:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise NotebookLMConnectionError(
                    f"{method} network error after {max_retries} attempts: {exc}"
                ) from exc

            # Session expired — reinitialize once and retry
            if resp.status_code == 400 and "session" in resp.text.lower():
                if attempt == 0:
                    self._session_id = None
                    self._initialize()
                    continue
                raise NotebookLMConnectionError(
                    f"Session invalid even after reinitialization: {resp.text[:200]}"
                )

            if resp.status_code != 200:
                raise NotebookLMConnectionError(
                    f"{method} returned HTTP {resp.status_code}: {resp.text[:300]}"
                )

            envelope = _parse_sse(resp.text)

            if "error" in envelope:
                err = envelope["error"]
                raise NotebookLMToolError(
                    f"{method} error {err.get('code', '?')}: {err.get('message', err)}"
                )

            return envelope.get("result", envelope)

        raise NotebookLMConnectionError(
            f"{method} failed after {max_retries} retries"
        )

    def _call_tool(self, name: str, arguments: dict) -> Any:
        """Call an MCP tool by name, return parsed content.

        Raises:
            NotebookLMToolError: if the tool returns no content or an error.
        """
        result = self._post_rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        if not content:
            raise NotebookLMToolError(
                f"Tool '{name}' returned empty content: {result}"
            )
        item = content[0]
        if item.get("type") == "text":
            text = item["text"]
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
        return item

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notebooks_list(self) -> list[dict]:
        """Return all notebooks."""
        result = self._call_tool("notebooks_list", {})
        if isinstance(result, list):
            return result
        # Some server versions wrap in a dict
        if isinstance(result, dict):
            return result.get("notebooks", list(result.values()))
        return result

    def sources_list(self, notebook_id: str) -> list[dict]:
        """Return all sources for a notebook."""
        result = self._call_tool("sources_list", {"notebook_id": notebook_id})
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("sources", list(result.values()))
        return result

    def sources_add_text(
        self, notebook_id: str, title: str, content: str
    ) -> dict:
        """Add a text source to a notebook.  Returns the new source dict (with id)."""
        result = self._call_tool(
            "sources_add_text",
            {"notebook_id": notebook_id, "title": title, "content": content},
        )
        if not isinstance(result, dict):
            raise NotebookLMToolError(
                f"sources_add_text expected dict result, got: {type(result)}: {result!r}"
            )
        return result

    def chat_ask(
        self,
        notebook_id: str,
        question: str,
        source_ids: list[str] | None = None,
    ) -> str:
        """Ask a question. Returns the answer string."""
        args: dict[str, Any] = {
            "notebook_id": notebook_id,
            "question": question,
        }
        if source_ids is not None:
            args["source_ids"] = source_ids
        result = self._call_tool("chat_ask", args)
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("response", "answer", "text", "content"):
                if key in result:
                    return str(result[key])
            return json.dumps(result)
        return str(result)

    def generate_study_guide(
        self,
        notebook_id: str,
        source_ids: list[str] | None = None,
        language: str = "en",
        extra_instructions: str | None = None,
    ) -> dict:
        """Generate a Study Guide report (async; returns task dict with task_id)."""
        args: dict[str, Any] = {
            "notebook_id": notebook_id,
            "language": language,
        }
        if source_ids is not None:
            args["source_ids"] = source_ids
        if extra_instructions is not None:
            args["extra_instructions"] = extra_instructions
        result = self._call_tool("generate_study_guide", args)
        if not isinstance(result, dict):
            raise NotebookLMToolError(
                f"generate_study_guide expected dict, got: {result!r}"
            )
        return result

    def artifacts_wait(
        self, notebook_id: str, task_id: str, timeout: int = 600
    ) -> dict:
        """Block until an artifact generation task completes. Returns artifact dict."""
        result = self._call_tool(
            "artifacts_wait",
            {
                "notebook_id": notebook_id,
                "task_id": task_id,
                "timeout": timeout,
            },
        )
        if not isinstance(result, dict):
            raise NotebookLMToolError(
                f"artifacts_wait expected dict, got: {result!r}"
            )
        return result
