# Architecture — 3D-Printed Force Feedback Joystick

## System Overview

This is a 2-axis (pitch + roll) force feedback joystick built from 3D-printed
structural components, GIM 8108-8 planetary gearbox BLDC motors, ODrive S1 motor
controllers, and an Open FFB joystick board.

The system has three major subsystems:

1. **Open FFB Board + Configurator** — The brain. Receives DirectInput FFB effects
   from IL-2 Great Battles (or other sims), translates them into motor commands,
   and sends torque/position commands to the ODrive S1 controllers via CAN bus.
   Also serves as the USB HID joystick device (axis position input to the PC).

2. **ODrive S1 Controllers (x2)** — One per axis. Receive CAN bus commands from
   the Open FFB board and drive the GIM 8108-8 motors in torque control mode.
   Configured and calibrated via the Python tool in this repository.

3. **Python Configuration Tool** (this repository) — A setup/calibration utility
   that programs the ODrive S1 controllers for the GIM 8108-8 motors. Not involved
   in real-time FFB operation. Run once during initial setup and after hardware changes.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        REAL-TIME OPERATION                       │
│         (Handled entirely by Open FFB Board + ODrive S1)         │
│                                                                  │
│  IL-2 Great Battles                                              │
│       │                                                          │
│       │ DirectInput FFB effects                                  │
│       ▼                                                          │
│  Open FFB Board (USB HID device)                                 │
│       │                                                          │
│       │ CAN bus motor commands (torque setpoints)                │
│       ▼                                                          │
│  ODrive S1 (pitch)  ◄──►  GIM 8108-8 motor  ──►  Pitch axis     │
│  ODrive S1 (roll)   ◄──►  GIM 8108-8 motor  ──►  Roll axis      │
│       │                                                          │
│       │ Encoder feedback (position → Open FFB → USB HID → sim)   │
│       ▼                                                          │
│  IL-2 receives joystick position via USB HID                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     SETUP / CALIBRATION                          │
│              (Python tool — this repository)                     │
│                                                                  │
│  User runs: python src/main.py                                   │
│       │                                                          │
│       │ USB connection to ODrive S1                               │
│       ▼                                                          │
│  1. Discover ODrive S1 controllers                               │
│  2. Apply motor config (pole pairs, KV, current limits)          │
│  3. Apply encoder config (CPR, index pulse)                      │
│  4. Apply controller config (torque mode, bandwidth, CAN IDs)    │
│  5. Run motor calibration                                        │
│  6. Run encoder index search                                     │
│  7. Verify center position (C-006)                               │
│  8. Save configuration to ODrive flash                           │
└─────────────────────────────────────────────────────────────────┘
```

## Component Descriptions

### src/main.py
Entry point for the configuration/calibration CLI tool. Orchestrates the full
setup sequence: discover → configure → calibrate → verify → save.

### src/odrive_interface/connection.py
ODrive S1 discovery and connection management. Handles USB enumeration, connection
lifecycle, and reconnection logic for both pitch and roll axis controllers.

### src/odrive_interface/configuration.py
Reads hardware parameters from `config/odrive_settings.yaml` and applies them to
the ODrive S1 controllers. Covers motor parameters (pole pairs, KV, current limits),
encoder settings (CPR, index pulse), and controller configuration (torque mode,
bandwidth, CAN node IDs).

### src/odrive_interface/calibration.py
Executes the startup calibration sequence: motor calibration, encoder index search,
and center position verification. Enforces C-006 (no force output before
calibration completes).

### src/utils/logging_config.py
Centralized logging configuration with structured output and configurable verbosity.

### config/odrive_settings.yaml
Hardware configuration parameters for the GIM 8108-8 motors and ODrive S1
controllers. Source of truth for motor, encoder, controller, and CAN bus settings.

### config/default_config.yaml
Operational parameters for the calibration tool: retry counts, timeouts,
tolerances, and logging configuration.

## Directory Structure

```
3D-Printed-FFB/
├── README.md                        # Project overview and quick start
├── CLAUDE.md                        # AI session briefing (read at session start)
├── CONTRIBUTING.md                  # Code comment standard and contribution workflow
├── ARCHITECTURE.md                  # This file
├── CONSTRAINTS.md                   # System constraints with FMEA traceability
├── LICENSE                          # MIT
├── KEY_DECISION_LOG.md              # Architectural decisions
├── CODE_DECISION_LOG.md             # Code-level decisions (merged from patches)
├── .repomixignore                   # Repomix exclusions
├── repomix.config.json              # Repomix configuration
├── .github/
│   └── workflows/
│       └── spike-check.yml          # Ground Rule 7 enforcement
├── docs/
│   ├── FMEA.md                      # Failure Mode and Effects Analysis
│   ├── KANBAN_SETUP.md              # Project board configuration
│   ├── templates/                   # Document templates (read-only after scaffolding)
│   └── proposals/                   # Scope change proposals
├── working/                         # Ephemeral per-session scratch space
│   ├── CODE_DECISIONS_PATCH.md      # Provisional code decisions
│   ├── ISSUE_QUEUE.md               # GitHub Issue creation queue
│   └── DOCUMENT_DRIFT_LOG.md        # Stale-fact registry
├── src/
│   ├── main.py                      # CLI entry point
│   ├── odrive_interface/            # ODrive S1 communication
│   │   ├── connection.py            # Discovery + connection
│   │   ├── configuration.py         # Motor/encoder/controller config
│   │   └── calibration.py           # Calibration sequence
│   └── utils/
│       └── logging_config.py        # Logging setup
├── tests/
│   └── test_odrive_interface.py     # ODrive interface tests
├── hardware/
│   ├── README.md                    # BOM, print settings, assembly notes
│   ├── stl/                         # STL files for 3D printing
│   └── drawings/                    # Technical drawings
└── config/
    ├── default_config.yaml          # Calibration parameters
    └── odrive_settings.yaml         # ODrive S1 hardware config
```

## Code Comment Standard

All Python files in this project must follow this comment structure:

### Module Docstrings (required on every .py file)
```python
"""
MODULE: <filename>
PURPOSE: <what this module does and why it exists>
FMEA: <referenced FMEA constraint IDs, or "N/A">
PHASE: <project phase number>
"""
```

### Function Docstrings (required on all public functions)
```python
def example_function(param):
    """
    WHAT: <what the function does>
    WHY: <why this function exists — the problem it solves>
    ARGS: <parameter descriptions>
    RETURNS: <return value description>
    FMEA: <referenced FMEA constraint IDs, or "N/A">
    """
```

### Block Comments (required on non-trivial logic)
```python
# Retry index search up to 3 times because the GIM 8108-8 encoder
# occasionally misses the index pulse on first pass (see FM-002).
for attempt in range(max_retries):
    ...
```

## Phase Status

| Phase | Description | Status |
|---|---|---|
| Phase 0 | Planning and scaffolding | COMPLETE |
| Phase 1 | ODrive S1 configuration and calibration tool | IN PROGRESS |
| Phase 2 | Open FFB Configurator integration and tuning | NOT STARTED |
