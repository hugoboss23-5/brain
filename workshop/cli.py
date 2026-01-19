"""
Opus Workshop CLI

Read-only operational surface to give Opus instant situational awareness and launch hints.
Usage:
    python workshop/cli.py status          # human-readable status
    python workshop/cli.py status --json   # machine-readable snapshot
    python workshop/cli.py launch          # show launch commands
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workshop.config import load_config
from workshop.ops_profile import load_ops_profile
from workshop.status import compose_status, dashboards


def _print_header(title: str) -> None:
    print(f"\n== {title} ==")


def _line(label: str, value: Any) -> None:
    print(f"{label:<18} {value}")


def render_status() -> None:
    snapshot = compose_status()
    cfg = snapshot["config"]
    server = snapshot["server"]
    memory = snapshot["memory"]
    hive = snapshot["hive"]
    queues = snapshot["queues"]

    _print_header("Config")
    _line("brain_path", cfg.get("brain_path"))
    _line("server_port", cfg.get("server_port"))
    if cfg.get("warning"):
        _line("warning", cfg.get("warning"))
    if cfg.get("error"):
        _line("error", cfg.get("error"))

    _print_header("Brain Server")
    if server.get("online"):
        _line("status", "online")
        _line("latency_ms", server.get("latency_ms"))
        _line("commander", server.get("hierarchy", {}).get("commander"))
        _line("hands", server.get("hierarchy", {}).get("hands"))
        _line("thinker", server.get("hierarchy", {}).get("thinker"))
        _line("swarm", server.get("hierarchy", {}).get("swarm"))
        _line("ollama", server.get("ollama"))
        if server.get("available_models"):
            _line("models", ", ".join(server["available_models"]))
    else:
        _line("status", "offline")
        _line("detail", server.get("error") or server.get("status_code"))

    _print_header("Memory (/memory)")
    if memory.get("online"):
        mem = memory.get("memory", {})
        _line("tasks_total", mem.get("total_tasks"))
        _line("tasks_success", mem.get("successful_tasks"))
        _line("tasks_failed", mem.get("failed_tasks"))
        _line("patterns", len(mem.get("learned_patterns", [])))
    else:
        _line("status", "unreachable")
        _line("detail", memory.get("error") or memory.get("status_code"))

    _print_header("Swarm Hive")
    if hive.get("present"):
        _line("task", hive.get("task"))
        _line("discoveries", hive.get("discoveries"))
        _line("solutions", hive.get("solutions"))
        _line("consensus", hive.get("consensus"))
        if hive.get("votes"):
            top_votes = sorted(hive["votes"].items(), key=lambda kv: kv[1], reverse=True)[:3]
            for proposal, count in top_votes:
                _line("vote", f"{count} :: {proposal}")
    else:
        _line("status", hive.get("message") or hive.get("error"))

    _print_header("Queues (from_claude_code)")
    if queues.get("present"):
        _line("files", queues.get("count"))
        sample = queues.get("sample") or []
        if sample:
            _line("sample", ", ".join(sample))
    else:
        _line("status", queues.get("message") or queues.get("error"))

    _print_header("Dashboards")
    for dash in dashboards(load_config()):
        _line(dash["name"], dash["path"])
        _line("launch", dash["launch"])


def render_json() -> None:
    snapshot = compose_status()
    print(json.dumps(snapshot, indent=2, default=str))


def render_launch() -> None:
    cfg = load_config()
    root: Path = Path(cfg.get("brain_path"))
    commands = {
        "brain_server": f"cd {root} && python brain_server.py",
        "orchestrator": f"cd {root} && python brain_orchestrator.py",
        "jaw_dropper": f"cd {root} && python scripts/JAW_DROPPER.py",
        "swarm_dashboard": f"Open {root / 'swarm' / 'dashboard.html'} in a browser",
    }
    _print_header("Launch (preview only)")
    for name, cmd in commands.items():
        _line(name, cmd)


def render_profile(as_json: bool = False) -> None:
    profile = load_ops_profile()
    if as_json:
        print(json.dumps(profile, indent=2))
        return

    _print_header("Ops Profile")
    _line("profile_path", profile.get("_profile_path"))
    if profile.get("_warning"):
        _line("warning", profile["_warning"])
    if profile.get("_error"):
        _line("error", profile["_error"])

    watches = ", ".join(profile.get("watch_paths", []))
    ignores = ", ".join(profile.get("ignore", []))
    _line("watch_paths", watches)
    _line("ignore", ignores)

    if profile.get("entrypoints"):
        _print_header("Entrypoints")
        for entry in profile["entrypoints"]:
            _line(entry.get("name", "entry"), f"{entry.get('command', '')} :: {entry.get('purpose', '')}")

    if profile.get("dashboards"):
        _print_header("Dashboards")
        for dash in profile["dashboards"]:
            _line(dash.get("name", "dash"), f"{dash.get('path', '')} :: {dash.get('launch', '')}")

    if profile.get("docs"):
        _print_header("Docs")
        _line("files", ", ".join(profile["docs"]))

    if profile.get("queues_dir"):
        _print_header("Queues Dir")
        _line("path", profile["queues_dir"])


def main(argv: Any = None) -> None:
    parser = argparse.ArgumentParser(description="Opus Workshop CLI (read-only by default)")
    sub = parser.add_subparsers(dest="command")

    status_cmd = sub.add_parser("status", help="Show current Brain/Swarm status (default)")
    status_cmd.add_argument("--json", action="store_true", help="Output JSON snapshot")

    sub.add_parser("launch", help="Show launch commands (does not execute)")

    profile_cmd = sub.add_parser("profile", help="Show ops profile (watch/ignore paths, entrypoints, dashboards)")
    profile_cmd.add_argument("--json", action="store_true", help="Output ops profile JSON")

    args = parser.parse_args(argv)

    if args.command in (None, "status"):
        if getattr(args, "json", False):
            render_json()
        else:
            render_status()
    elif args.command == "launch":
        render_launch()
    elif args.command == "profile":
        render_profile(as_json=getattr(args, "json", False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
