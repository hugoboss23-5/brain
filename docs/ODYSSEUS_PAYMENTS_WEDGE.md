# Odysseus Wedge – Payments (Rate-Dependent Damping)

Goal: apply continuous, rate-based friction at the point of payment authorization/settlement to damp runaway extraction without hard caps.

## Control shape
- Damping term: fee/hold proportional to transaction velocity (per merchant/user/IP/device) with smooth ramp.
- f(v) = base_fee + k1 * v + k2 * v^2 (clipped to max_surcharge), updated in real time.
- Local coupling: computed on the actor’s own recent velocity (rolling window seconds/minutes).
- No suppression: never block outright; raise friction dynamically.

## Signals
- Velocity: txn count/amount per actor per time window (auths, settlements, payouts).
- Trust: risk score, historical chargebacks, KYC tier to set k1/k2 and max_surcharge.
- State: rolling window stats stored in fast store (Redis/SQLite) keyed by actor.

## Placement
- Hook into `/execute`-style path for payments: at authorization or fee calculation step.
- Compute damping surcharge/hold and return alongside approval.
- Log applied friction to `task_log` (brain memory) and a dedicated `damping_log`.

## Parameters (initial)
- Window: 5–15s for velocity, plus slower 5–15m smoothing.
- k1 (linear): small (e.g., 0.5–1% per unit velocity); k2 (quadratic): tiny to catch spikes.
- max_surcharge: 3–5% over base fees.
- Decay: exponential moving average to let friction relax when velocity drops.

## Rollout plan
1) Build a local calculator module: `payments/damping.py` with config for k1/k2/window/max.
2) Wire a test endpoint `/payments/damping_preview` that takes actor_id + txn amount → returns surcharge/hold.
3) Log decisions to `damping_log.jsonl` for audit and tuning.
4) Monitor: plot applied friction vs velocity; target stable approval rates with bounded surcharges.

## How to use the workshop
- Opus: review this doc, then direct EAI to implement `payments/damping.py` + `/payments/damping_preview` endpoint (similar to `/execute` style).
- EAI: implement with no file creation beyond instructed modules; log to `system/damping_log.jsonl`.
- Thinker: tune k1/k2/window via `deep_think` on observed velocity distributions.
- Swarm: explore edge cases (bursts, fraudy patterns) and propose parameter guards.
