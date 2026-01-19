# Opus Workshop Commands

Read-only operational surface for Opus. Nothing here edits Brain by default.

## Quickstart
- Status (human): `python workshop/cli.py status`
- Status (JSON): `python workshop/cli.py status --json`
- Launch hints: `python workshop/cli.py launch`
- Ops profile: `python workshop/cli.py profile` (or `--json`)

Run these from the repo root (`C:\\Users\\bulli\\brain`).

## What you get
- Config: shows `brain_path`, `server_port`, and whether `brain_config.json` was parsed.
- Brain Server: online/offline, latency, commander/hands/thinker/swarm models, Ollama state, available models.
- Memory: task counters and learned pattern count from `/memory`.
- Swarm Hive: active task, discoveries, solutions, consensus, top votes from `swarm/hive_memory.json`.
- Queues: file count + sample from `system/queues/from_claude_code`.
- Dashboards: paths and commands to open `swarm/dashboard.html`, `scripts/JAW_DROPPER.py`, `agent_dashboard.html`.
- Ops Profile: shows `config/ops_profile.json` (watch/ignore paths, entrypoints, dashboards, docs, queues_dir) so Opus can tune what to monitor or ask EAI to rearrange.

## Notes
- Default mode never executes subprocesses; `launch` only prints the commands.
- All paths derive from `brain_config.json` (no hardcoded `/home/user/brain`).
- Outputs are ASCII so Opus can copy/paste into other tools easily.
- Customize ops profile by editing `config/ops_profile.json` (add/remove watch paths, dashboards, entrypoints). Opus will see it live via `workshop/cli.py profile`.
