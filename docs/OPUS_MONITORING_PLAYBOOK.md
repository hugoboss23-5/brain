# Opus Monitoring & Arrangement Playbook

Goal: make it trivial for Opus to see what matters and tell EAI how to arrange it—without restarts or guessing paths.

## Read the live picture
- Status: `python workshop/cli.py status` (or `--json`) for server/memory/hive/queues/dashboards.
- Ops profile: `python workshop/cli.py profile` (or `--json`) to see watch/ignore paths, entrypoints, dashboards, docs, queues dir.

## Tune what Opus watches
Edit `config/ops_profile.json`:
- `watch_paths`: add/remove folders/files Opus should pay attention to.
- `ignore`: add noisy dirs (e.g., large data dumps) to hide from monitors.
- `entrypoints`: add commands for new apps or scripts; include `name`, `path`, `command`, `purpose`.
- `dashboards`: add your own dashboards with `name`, `path`, `launch`.
- `docs`: link runbooks or protocols Opus should surface.
- `queues_dir`: change if you relocate Claude Code queues.

These edits are read live by the workshop CLI; no restart required.

## Instruct EAI to arrange using the profile
Tell Opus something like:
- “Use the ops profile and move non-core utilities into a `tools/` folder, respecting ignore paths. Report moves and update imports.”
- “Using entrypoints from the ops profile, generate a README section that documents how to run each app.”
- “Scan watch_paths, flag files missing docstrings, and open PR-ready diffs to add them.”

## Add new monitors
- Drop extra paths in `watch_paths` to fold them into the Jaw Dropper and status sweeps.
- If you add a new dashboard, record it under `dashboards` so `workshop/cli.py profile` shows the launch instructions.

## Safety
- Workshop commands are read-only.
- Prompt changes auto-reload in the orchestrator via `Operating/prompt_overrides.md` and `Origins/CLAUDE_IDENTITY.md`.

## Performance knobs (current defaults)
- Hands (/execute): timeout 45s, num_predict 2000 via Ollama.
- Thinker (/think): timeout 120s, num_predict 2000.
- Swarm: 12 workers, 90s round timeout, 15s per-agent future, TinyLlama num_predict 256, 30s request timeout.
- Opus: max_tokens 3000, history window 15 messages, tool loop cap 10.

## Memory knobs
- Brain memory tracks task_log (last 50 executions) with actions/files_created; view via `/memory`.
- Conversation memory persists in `system/conversation_memory.json`; prompt overrides in `Operating/prompt_overrides.md`.
- Swarm memory persists in `swarm/hive_memory.json` (discoveries, solutions, votes, agent_status).
