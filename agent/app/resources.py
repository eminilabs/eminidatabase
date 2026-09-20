"""Resource reporting sent at registration and on every heartbeat.

cf. docs/architecture/03-database-orchestrator-et-agent.md — the Orchestrator's
placement decisions in Phase 3 will be only as good as what's reported here.
"""

from __future__ import annotations

import shutil

import psutil


def collect_capacity() -> dict:
    """Total capacity — reported once, at registration."""
    disk = shutil.disk_usage("/")
    return {
        "cpu_total": psutil.cpu_count(logical=True) or 1,
        "ram_total_mb": round(psutil.virtual_memory().total / (1024 * 1024)),
        "storage_total_gb": round(disk.total / (1024**3)),
    }


def collect_usage() -> dict:
    """Current usage — reported on every heartbeat."""
    disk = shutil.disk_usage("/")
    return {
        "cpu_used": psutil.cpu_percent(interval=0.2) / 100 * (psutil.cpu_count(logical=True) or 1),
        "ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024)),
        "storage_used_gb": round(disk.used / (1024**3)),
    }
