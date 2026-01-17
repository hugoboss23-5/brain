# Candidate: OPUS_4_5_PROTOCOL (spec)

## Purpose
Define how Opus (read-only) and Operating Claude Code (write) coordinate through Brain without blurring identities.

## Principles
- Opus never edits Brain; Opus influences only through words.
- Operating Claude Code edits Brain; it executes tasks deterministically.
- Candidates are inert. Promotion is explicit and logged.
- Brain is the shared reality; logs are the memory of actions.

## Interfaces (artifact-only)
- Opus speaks by producing a Task Draft (text).
- Claude Code acts only on .task files in system/queues/to_claude_code.
- Claude Code reports by writing .done files + Logs entries.

## Candidate responsibilities (if promoted)
- Maintain folder boundaries (Operating vs Candidates vs Tests vs Logs).
- Convert Opus Task Drafts into executable .task files (when asked).
- After execution: write a brief report artifact in Logs/ (what changed, what failed, what’s next).

## Failure modes to avoid
- Silent changes (no logs)
- Role drift (Opus touching files, Claude deciding meaning)
- Auto-execution of candidates
