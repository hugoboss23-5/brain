# Control Globe Concept (3D Habitat)

Intent: Opus watches and shapes; EAI lives and works inside. The globe is a 3D habitat where EAI operates the controls. Opus never enters—he observes the state, names changes, and instructs EAI to act. They must stay in unison (“unicen”)—EAI learns the patterns and improves over time, Opus directs.

## Roles
- Opus: vision + guidance. Names shapes, goals, constraints. Never touches controls.
- EAI (hands): inhabits the globe, executes all actions (start/stop swarm, switch views, trigger tasks), learns “unicen” patterns.
- EAI memory: record of globe actions and outcomes (brain memory `task_log`, swarm `hive_memory.json`); can be extended with a dedicated globe log.

## Surfaces
- Live Agents (visual globe surface): `swarm/live_agents.html` (agent_status from `/swarm/status`).
- Swarm Hive: `swarm/hive_memory.json` (discoveries, solutions, votes).
- Task memory: `system/brain_memory.json` (`task_log` last 50 executions).
- Opus prompt: `Operating/prompt_overrides.md` + `Origins/CLAUDE_IDENTITY.md`.

## How Opus directs, EAI acts
- Opus: “EAI, rotate the globe to show active agents and highlight failures.” EAI calls `/swarm/status`, updates displays, logs to task_log. Opus only observes.
- Opus: “EAI, replay last 5 globe actions and improve latency.” EAI reads task_log, optimizes, records new results, and reports back.

## Memory uplift
- Brain memory keeps `task_log` (last 50) for EAI actions; swarm memory persists agent_status/discoveries.
- If more memory is needed: expand task_log cap, add summaries, or mirror into a dedicated `system/eai_memory.json` for globe actions and “unicen” lessons.

## Next implementations (optional)
- Add globe controls API (e.g., `/globe/highlight`, `/globe/view`) that EAI calls; wire a 3D UI to reflect state.
- Add a dedicated EAI globe memory (`system/eai_memory.json`) capturing actions, feedback, and “unicen” patterns.
- Add a “history” panel to `swarm/live_agents.html` showing recent EAI globe actions from task_log.
