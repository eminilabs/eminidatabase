"""Run this once on a fresh VPS, before starting the agent server.

Generates this node's keypair, sends a CSR + the one-shot bootstrap token to the
Control Plane, and saves the signed certificate, CA certificate, and node
credentials to STATE_DIR. See docs/architecture/03-database-orchestrator-et-agent.md
§"Enregistrement d'un node (bootstrap)".

Usage:
    BOOTSTRAP_TOKEN=... REGION_CODE=... python bootstrap.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

from app.config import get_agent_settings
from app.control_plane_client import register
from app.state import load_state


async def main() -> None:
    settings = get_agent_settings()

    if load_state(Path(settings.state_dir)) is not None:
        print(
            "This node already has a saved identity in STATE_DIR. "
            "Delete it first if you really want to re-register.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        state = await register(settings)
    except httpx.HTTPStatusError as exc:
        print(f"Registration rejected by Control Plane: {exc.response.text}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Registered as node {state.node_id} ({state.hostname}).")
    print(f"Credentials and certificate saved under {settings.state_dir}/")
    print()
    print("Start the agent with mTLS enforced, e.g.:")
    print(
        f"  uvicorn app.main:app --host 0.0.0.0 --port {settings.agent_port} "
        f"--ssl-keyfile {settings.state_dir}/node.key "
        f"--ssl-certfile {settings.state_dir}/node.crt "
        f"--ssl-ca-certs {settings.state_dir}/ca.crt "
        "--ssl-cert-reqs 2"
    )


if __name__ == "__main__":
    asyncio.run(main())
