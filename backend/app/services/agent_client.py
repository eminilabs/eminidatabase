"""Thin mTLS HTTP client for Control Plane -> Data Plane Agent calls.

Used by both the manual health-check endpoint (app/api/v1/endpoints/nodes.py) and
the orchestrator's job execution — one place owns how the Control Plane talks to an
agent, so the mTLS wiring can't drift between call sites.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.models.node import Node
from app.services.ca import ensure_control_plane_client_cert


class AgentUnreachableError(Exception):
    """The agent could not be reached at all (network/TLS/timeout failure) — the
    caller has no more information about the request than "it never got there"."""


class AgentRequestError(Exception):
    """The agent *was* reached and responded with an error (e.g. it rejected the
    request as invalid) — callers should surface `status_code`/`detail` to the
    user rather than treating this the same as an unreachable node."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(f"Agent rejected the request ({status_code}): {detail}")
        self.status_code = status_code
        self.detail = detail


async def call_agent(
    node: Node,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> httpx.Response:
    if not node.ip_address:
        raise AgentUnreachableError(f"Node {node.id} has no known IP address")

    key_path, cert_path, ca_cert_path = ensure_control_plane_client_cert()
    url = f"https://{node.ip_address}:{node.agent_port}{path}"
    try:
        async with httpx.AsyncClient(
            cert=(str(cert_path), str(key_path)), verify=str(ca_cert_path), timeout=timeout
        ) as client:
            resp = await client.request(method, url, json=json, params=params)
            resp.raise_for_status()
            return resp
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text
        raise AgentRequestError(exc.response.status_code, detail) from exc
    except httpx.HTTPError as exc:
        raise AgentUnreachableError(f"Agent call to {node.id} failed: {exc}") from exc
