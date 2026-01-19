# Opus Workshop Blueprint

Purpose: give Opus a single, safe ops surface over Brain. No existing files are touched; this is a read-only map plus build plan.

## Current moving parts
- Commander: `brain_orchestrator.py` (Opus CLI, conversation memory).
- Hands/Thinker/Swarm: `brain_server.py` with /execute, /think, /pluribus, /view, /memory.
- Swarm memory: `swarm/hive_mind.py` (`swarm/hive_memory.json`) and `swarm_commander.py`.
- Dashboards: `swarm/dashboard.html`; `scripts/JAW_DROPPER.py` (Dash monitor, needs fixes).
- Safety/logs/config: `brain_config.json`, `system/brain_memory.json`, queues under `system/queues/`.

## Pain points to solve
- No single status board (server health, memory, swarm state, queues, dashboards).
- Config is duplicated/hardcoded (paths, ports, model names).
- Observability gaps (no quick view of errors, latest executions, swarm consensus).
- Launch friction (remembering commands/ports/paths).

## Workshop goals (Opus-facing)
1) Instant situational awareness: one command to print health of server, memory, queues, swarm, dashboards.
2) Launchpad: shortcuts to start/attach to Brain services and open dashboards.
3) Safe visibility: read-only by default; explicit flags to run disruptive actions.
4) Extensible: thin modules so new probes/commands drop in without touching core.

## Proposed components (non-invasive)
- `workshop/config.py`: centralized loader for `brain_config.json`, env overrides, and sensible defaults.
- `workshop/status.py`: probes for server `/status`, `/memory`, swarm hive, queues, dashboards; all read-only.
- `workshop/cli.py`: Rich-powered CLI (`python workshop/cli.py status|launch|swarm|queues`) that only reads unless `--do` is passed for future actions.
- `workshop/plugins/`: optional probes (e.g., lint drift, dash health, port conflicts) kept isolated.
- `config/ops_profile.json`: editable profile for Opus/EAI with watch/ignore paths, entrypoints, dashboards, docs, queues dir.

## Initial commands (safe defaults)
- `status`: ping server; report commander/hands/thinker/swarm models; show memory counts; show hive consensus, discoveries, votes; list latest queue files; highlight dashboards and where to open them.
- `launch --what brain|orchestrator|jaw|swarmdash`: print the exact command and path (no auto-run by default).
- `queues`: read `system/queues/from_claude_code` and summarize pending/done items.
- `hive`: summarize `swarm/hive_memory.json` (task, discoveries, votes, consensus).
- `profile`: surface `config/ops_profile.json` so Opus can tweak monitoring/arrangement targets and direct EAI accordingly.

## Guardrails
- Default mode is read-only (no writes, no subprocesses).
- Config always read from `brain_config.json`; no hardcoded `/home/user/brain`.
- Clear separation: workshop tools sit under `workshop/` so core stays untouched.

## Next steps to implement
- Add `workshop/config.py` (safe loader) and `workshop/cli.py` (status + launch hints).
- Wire Jaw Dropper to use the same config loader and avoid `exec` for code quality.
- Add a short `docs/WORKSHOP_COMMANDS.md` once the CLI is in place.
