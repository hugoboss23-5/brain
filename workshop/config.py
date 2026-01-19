"""
Centralized config loader for Opus Workshop.
Reads brain_config.json, applies safe defaults, and exposes helper utilities.
All paths are resolved relative to the repo root (two levels up from this file).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = {
    "server_port": 8000,
    "brain_path": str(REPO_ROOT),
    "allowed_operations": [],
}
CONFIG_PATH = REPO_ROOT / "brain_config.json"


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load brain_config.json with defaults and light error reporting."""
    path = Path(config_path or CONFIG_PATH)
    cfg: Dict[str, Any] = DEFAULT_CONFIG.copy()
    cfg["_config_path"] = str(path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update(data)
    except FileNotFoundError:
        cfg["_warning"] = "brain_config.json not found; using defaults."
    except Exception as exc:  # noqa: BLE001
        cfg["_error"] = f"Failed to parse config: {exc}"

    brain_path = Path(os.path.expanduser(cfg.get("brain_path", DEFAULT_CONFIG["brain_path"])))
    cfg["brain_path"] = brain_path
    cfg["server_port"] = int(cfg.get("server_port", DEFAULT_CONFIG["server_port"]))
    cfg["_repo_root"] = str(REPO_ROOT)
    return cfg


def server_url(cfg: Dict[str, Any]) -> str:
    """Return the local brain server base URL."""
    return f"http://127.0.0.1:{cfg.get('server_port', DEFAULT_CONFIG['server_port'])}"


def hive_path(cfg: Dict[str, Any]) -> Path:
    """Path to swarm hive memory file."""
    return Path(cfg.get("brain_path", REPO_ROOT)) / "swarm" / "hive_memory.json"


def queues_path(cfg: Dict[str, Any]) -> Path:
    """Path to the Claude Code queue directory."""
    return Path(cfg.get("brain_path", REPO_ROOT)) / "system" / "queues" / "from_claude_code"
