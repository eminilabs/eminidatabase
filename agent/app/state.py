from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class NodeState:
    node_id: str
    node_secret: str
    hostname: str
    region_code: str
    registered_at: str


def state_file(state_dir: Path) -> Path:
    return state_dir / "node_state.json"


def load_state(state_dir: Path) -> NodeState | None:
    path = state_file(state_dir)
    if not path.exists():
        return None
    return NodeState(**json.loads(path.read_text()))


def save_state(state_dir: Path, state: NodeState) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file(state_dir).write_text(json.dumps(asdict(state), indent=2))


def key_path(state_dir: Path) -> Path:
    return state_dir / "node.key"


def cert_path(state_dir: Path) -> Path:
    return state_dir / "node.crt"


def ca_cert_path(state_dir: Path) -> Path:
    return state_dir / "ca.crt"
