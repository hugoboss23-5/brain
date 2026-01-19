"""
Status probes for Opus Workshop.
All functions are read-only and safe to call while Brain is running.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

from workshop.config import hive_path, load_config, queues_path, server_url


def _duration_ms(start: float) -> int:
    return int((time.time() - start) * 1000)


def probe_server(cfg: Dict[str, Any], timeout: float = 2.0) -> Dict[str, Any]:
    """Ping /status on the brain server."""
    url = f"{server_url(cfg)}/status"
    started = time.time()
    try:
        resp = requests.get(url, timeout=timeout)
        latency = _duration_ms(started)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "online": True,
                "latency_ms": latency,
                "hierarchy": data.get("hierarchy"),
                "memory": data.get("memory"),
                "ollama": data.get("ollama"),
                "available_models": data.get("available_models", []),
            }
        return {"online": False, "status_code": resp.status_code, "latency_ms": latency}
    except Exception as exc:  # noqa: BLE001
        return {"online": False, "error": str(exc), "latency_ms": _duration_ms(started)}


def probe_memory(cfg: Dict[str, Any], timeout: float = 2.0) -> Dict[str, Any]:
    """Fetch /memory for task counters."""
    url = f"{server_url(cfg)}/memory"
    started = time.time()
    try:
        resp = requests.get(url, timeout=timeout)
        latency = _duration_ms(started)
        if resp.status_code == 200:
            return {"online": True, "latency_ms": latency, "memory": resp.json()}
        return {"online": False, "status_code": resp.status_code, "latency_ms": latency}
    except Exception as exc:  # noqa: BLE001
        return {"online": False, "error": str(exc), "latency_ms": _duration_ms(started)}


def read_hive(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize swarm hive memory."""
    path = hive_path(cfg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"present": False, "message": "hive_memory.json not found"}
    except Exception as exc:  # noqa: BLE001
        return {"present": False, "error": f"Failed to read hive memory: {exc}"}

    return {
        "present": True,
        "task": data.get("task"),
        "discoveries": len(data.get("discoveries", [])),
        "solutions": len(data.get("solutions", [])),
        "votes": {k: len(v) for k, v in data.get("votes", {}).items()},
        "consensus": data.get("consensus") or data.get("task"),
    }


def summarize_queues(cfg: Dict[str, Any], limit: int = 12) -> Dict[str, Any]:
    """List files under system/queues/from_claude_code."""
    root = queues_path(cfg)
    try:
        files = sorted([p.name for p in root.iterdir() if p.is_file()])
    except FileNotFoundError:
        return {"present": False, "message": "queue directory missing"}
    except Exception as exc:  # noqa: BLE001
        return {"present": False, "error": f"Failed to read queue: {exc}"}

    return {
        "present": True,
        "count": len(files),
        "sample": files[:limit],
    }


def dashboards(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Known dashboards and how to launch them (no auto-execution)."""
    brain_path: Path = Path(cfg.get("brain_path"))
    return [
        {
            "name": "Swarm Dashboard",
            "path": str(brain_path / "swarm" / "dashboard.html"),
            "launch": "Open in browser (file://) or serve via any static server.",
        },
        {
            "name": "Jaw Dropper",
            "path": str(brain_path / "scripts" / "JAW_DROPPER.py"),
            "launch": "python scripts/JAW_DROPPER.py",
        },
        {
            "name": "Agent Dashboard",
            "path": str(brain_path / "agent_dashboard.html"),
            "launch": "Open in browser (file://) for static view.",
        },
    ]


def compose_status() -> Dict[str, Any]:
    """Build a full status snapshot in one call."""
    cfg = load_config()
    return {
        "config": {
            "brain_path": str(cfg.get("brain_path")),
            "server_port": cfg.get("server_port"),
            "config_path": cfg.get("_config_path"),
            "warning": cfg.get("_warning"),
            "error": cfg.get("_error"),
        },
        "server": probe_server(cfg),
        "memory": probe_memory(cfg),
        "hive": read_hive(cfg),
        "queues": summarize_queues(cfg),
        "dashboards": dashboards(cfg),
    }
