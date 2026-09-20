from __future__ import annotations

import asyncio
import datetime as dt
import logging
from pathlib import Path

import httpx

from app.config import AgentSettings
from app.crypto import generate_csr_pem, generate_private_key, save_private_key
from app.resources import collect_capacity, collect_usage
from app.state import NodeState, ca_cert_path, cert_path, key_path, load_state, save_state

logger = logging.getLogger("agent.control_plane_client")


async def register(settings: AgentSettings) -> NodeState:
    if not settings.bootstrap_token:
        raise RuntimeError("BOOTSTRAP_TOKEN is required for the first registration run")

    state_dir = Path(settings.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    private_key = generate_private_key()
    hostname = settings.resolved_hostname()
    csr_pem = generate_csr_pem(private_key, common_name=hostname)

    payload = {
        "hostname": hostname,
        "region_code": settings.region_code,
        "csr_pem": csr_pem,
        "ip_address": settings.ip_address,
        "agent_version": settings.agent_version,
        "agent_port": settings.agent_port,
        "postgres_port": settings.postgres_port,
        **collect_capacity(),
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.control_plane_url}/nodes/register",
            headers={"Authorization": f"Bearer {settings.bootstrap_token}"},
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()

    save_private_key(key_path(state_dir), private_key)
    cert_path(state_dir).write_text(body["certificate_pem"])
    ca_cert_path(state_dir).write_text(body["ca_certificate_pem"])

    state = NodeState(
        node_id=body["node_id"],
        node_secret=body["node_secret"],
        hostname=hostname,
        region_code=settings.region_code,
        registered_at=dt.datetime.now(dt.UTC).isoformat(),
    )
    save_state(state_dir, state)
    return state


async def send_heartbeat(settings: AgentSettings, state: NodeState) -> None:
    payload = {"agent_version": settings.agent_version, **collect_usage()}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.control_plane_url}/nodes/{state.node_id}/heartbeat",
            headers={"Authorization": f"Bearer {state.node_secret}"},
            json=payload,
        )
        resp.raise_for_status()


async def heartbeat_loop(settings: AgentSettings, state: NodeState) -> None:
    while True:
        try:
            await send_heartbeat(settings, state)
            logger.info("heartbeat sent")
        except Exception:
            logger.exception("heartbeat failed — will retry next interval")
        await asyncio.sleep(settings.heartbeat_interval_seconds)


def ensure_registered(settings: AgentSettings) -> NodeState:
    state = load_state(Path(settings.state_dir))
    if state is None:
        raise RuntimeError(
            "No node identity found. Run `python bootstrap.py` once before starting the agent."
        )
    return state
