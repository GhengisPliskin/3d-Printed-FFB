# CLAUDE.md — Session Briefing

**Project:** 3D-Printed Force Feedback Joystick — GIM 8108-8 + ODrive S1 + Open FFB

## System Architecture (condensed)

- **Open FFB Configurator** handles the full FFB pipeline: IL-2 DirectInput FFB →
  CAN bus motor commands → ODrive S1 controllers. Also serves as USB HID joystick.
- **Python code (this repo)** is an ODrive S1 configuration and calibration tool only.
  Not involved in real-time FFB operation.
- **2-axis system**: pitch + roll, each with a GIM 8108-8 motor + ODrive S1.
- **Thermal monitoring** is a configurator-side feature, currently non-functional (FM-005, RPN 512).

## Project Intelligence Roster

| Tier | Models | Use |
|---|---|---|
| Tier 1 — Complex Reasoning | Claude Opus (Claude Code, Claude.ai) | Architecture, FMEA, cross-cutting, integration |
| Tier 2 — Standard Execution | Claude Sonnet (Claude Code, Claude.ai), Gemini Pro | Feature implementation, tests, docs |
| Tier 3 — Boilerplate | Gemini models (various), Claude Sonnet | Scaffolding, formatting, linting |

Context window binding constraint: 200k tokens. Optimize prompt headers accordingly.

## Session Types

### Execution Session (write code)
1. Read `ARCHITECTURE.md`
2. Run Repomix or ingest repo map
3. Identify active issue (Ground Rule 1 — no code without an issue)
4. Load prompt header if one exists for the task
5. Write code. Log all code decisions to `working/CODE_DECISIONS_PATCH.md`
6. Two-phase commit for Tier 1/2 tasks: generate code → HALT → await human approval → update docs

### Housekeeping Session (no code)
1. Process `working/ISSUE_QUEUE.md` — create GitHub Issues
2. Process `working/DOCUMENT_DRIFT_LOG.md` — fix stale references
3. Merge approved `working/CODE_DECISIONS_PATCH.md` entries into `CODE_DECISION_LOG.md`
4. No code changes allowed in housekeeping sessions

## Startup Sequence (every session)

1. Read `ARCHITECTURE.md` for current system state
2. Run Repomix or ingest repo map (Ground Rule 10)
3. Identify the active issue for this session
4. Load the relevant prompt header from `docs/templates/` if applicable

## Ground Rules

1. **Issue Binding** — No code generated without an active, assigned Issue.
2. **Decision Logging** — Code decisions → `working/CODE_DECISIONS_PATCH.md`. Merged to `CODE_DECISION_LOG.md` at human gate. Architectural decisions → `KEY_DECISION_LOG.md`.
3. **State Sync** — State Kanban column changes at start/end of every action.
4. **Source Truth** — `ARCHITECTURE.md` updated with any structural change.
5. **Constraint Traceability** — Decisions impacting FMEA constraints reference the FMEA ID.
6. **Template Adherence** — Read template files before generating structured documents. No reconstruction from memory.
7. **[SPIKE] Exemption** — Spike issues suspend formatting rules. Cannot reach "Done" without a linked formalization issue.
8. **Execution-Locked FMEA** — FMEA constraints are immutable during execution. Do not relax constraints.
9. **FMEA Amendment Protocol** — If a constraint is impossible, halt and propose formal amendment.
10. **Codebase State Sync** — Ingest repo map (Repomix) at session start.
11. **Code Comment Standard** — Module docstrings, function docstrings, block comments required. Never remove existing comments.

## File Write Locations

| What | Where |
|---|---|
| Code decisions (provisional) | `working/CODE_DECISIONS_PATCH.md` |
| New issues to create | `working/ISSUE_QUEUE.md` |
| Stale document references | `working/DOCUMENT_DRIFT_LOG.md` |
| Architectural decisions | `KEY_DECISION_LOG.md` |
| Code decisions (merged, at human gate) | `CODE_DECISION_LOG.md` |

## Drift Detection

If any session changes a project fact (architecture, constraints, component behavior),
log stale references to `working/DOCUMENT_DRIFT_LOG.md` with:
- The stale fact
- Which documents reference it
- The corrected value
- Session date

## Key Constraints (quick reference)

- C-001: Python 3.10+, no C extensions
- C-002: ODrive S1 via odrive Python package
- C-003: Open FFB board is USB HID device; Configurator handles FFB pipeline
- C-006: Calibration must verify center before enabling forces
- C-010: All modules need docstrings and block comments

See `CONSTRAINTS.md` for the full register.
