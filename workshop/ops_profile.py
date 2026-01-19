"""
Ops profile loader (customizable knobs for Opus/EAI).
Reads config/ops_profile.json; provides defaults if missing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = REPO_ROOT / "config" / "ops_profile.json"

DEFAULT_PROFILE: Dict[str, Any] = {
    "version": 1,
    "watch_paths": ["brain_server.py", "brain_orchestrator.py", "swarm", "system", "scripts", "docs", "config"],
    "ignore": [".venv", "__pycache__", "Logs", "node_modules", ".git"],
    "entrypoints": [],
    "dashboards": [],
    "docs": [],
    "queues_dir": "system/queues/from_claude_code",
}


def load_ops_profile(path: Path | None = None) -> Dict[str, Any]:
    profile_path = Path(path or PROFILE_PATH)
    profile = DEFAULT_PROFILE.copy()
    profile["_profile_path"] = str(profile_path)

    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            profile.update(data)
    except FileNotFoundError:
        profile["_warning"] = "ops_profile.json not found; using defaults."
    except Exception as exc:  # noqa: BLE001
        profile["_error"] = f"Failed to parse ops_profile.json: {exc}"

    return profile
