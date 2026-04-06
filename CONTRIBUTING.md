# Contributing to 3D-Printed FFB

## Code Comment Standard

All Python code in this project must follow this comment structure. This is
enforced by Ground Rule 11 and constraint C-010.

### Module Docstrings

Every `.py` file must begin with a module-level docstring:

```python
"""
MODULE: <filename>
PURPOSE: <what this module does and why it exists>
FMEA: <referenced FMEA constraint IDs, or "N/A">
PHASE: <project phase number>
"""
```

### Function Docstrings

Every public function must have a structured docstring:

```python
def configure_motor(odrive, settings):
    """
    WHAT: Applies motor configuration parameters to an ODrive S1 controller.
    WHY: The GIM 8108-8 requires specific pole pair count, KV rating, and
         current limits that differ from ODrive defaults.
    ARGS:
        odrive: Connected ODrive S1 instance.
        settings: Dict of motor parameters from odrive_settings.yaml.
    RETURNS: None. Raises ConfigurationError on failure.
    FMEA: FM-001 — PID parameters affect center oscillation behavior.
    """
```

### Block Comments

Non-trivial logic blocks must have plain-English comments explaining intent:

```python
# Retry index search up to 3 times because the GIM 8108-8 encoder
# occasionally misses the index pulse on first pass (see FM-002).
for attempt in range(max_retries):
    ...
```

### Rules

- **Never remove existing comments** (Ground Rule 11).
- Comments explain *why*, not *what* — the code shows what.
- Reference FMEA IDs when the code mitigates a known failure mode.

## Contribution Workflow

1. **Fork** the repository
2. **Create a branch** from `main` with a descriptive name
3. **Check for an Issue** — all code must be bound to an Issue (Ground Rule 1)
4. **Write code** following the comment standard above
5. **Log decisions** to `working/CODE_DECISIONS_PATCH.md` (Ground Rule 2)
6. **Update `ARCHITECTURE.md`** if your change affects structure (Ground Rule 4)
7. **Open a PR** referencing the Issue number

## Ground Rules Reference

These rules apply to all contributors, human and AI:

| # | Rule |
|---|---|
| 1 | **Issue Binding** — No code without an active Issue |
| 2 | **Decision Logging** — Code decisions → `working/CODE_DECISIONS_PATCH.md` |
| 3 | **State Sync** — Announce Kanban column changes |
| 4 | **Source Truth** — `ARCHITECTURE.md` stays current |
| 5 | **Constraint Traceability** — Reference FMEA IDs in decisions |
| 6 | **Template Adherence** — Read templates before generating docs |
| 7 | **[SPIKE] Exemption** — Spikes need formalization before Done |
| 8 | **Execution-Locked FMEA** — Constraints immutable during execution |
| 9 | **FMEA Amendment Protocol** — Halt for formal review if constraint is impossible |
| 10 | **Codebase State Sync** — Fresh repo map at session start |
| 11 | **Code Comment Standard** — Docstrings + block comments required, never remove |

See [`CONSTRAINTS.md`](CONSTRAINTS.md) for the full constraint register.
