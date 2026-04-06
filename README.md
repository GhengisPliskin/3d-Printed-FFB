# 3D-Printed Force Feedback Joystick

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A 2-axis (pitch + roll) force feedback joystick built from 3D-printed structural
components. Uses GIM 8108-8 planetary gearbox BLDC motors driven by ODrive S1 motor
controllers, with an Open FFB joystick board handling USB HID input and DirectInput
force feedback effects. This project was inspired by the orginal Laser Wing FFB joystick, 
redesigned for the available and lower cost GIM 8108-8 BLDC motors.

## Hardware

| Component | Purpose |
|---|---|
| GIM 8108-8 Planetary Gearbox BLDC (x2) | Pitch and roll axis motors |
| ODrive S1 Motor Controller (x2) | Motor control via CAN bus |
| Open FFB Joystick Board | USB HID joystick + FFB effect processing |
| 3D Printed Structure | Gimbal frame, motor mounts, joystick grip mount |

## Quick Start

> Placeholder — will be populated during Phase 1 execution.

1. Print parts (see `hardware/README.md` for BOM and print settings)
2. Assemble hardware
3. Configure ODrive S1 controllers: `python src/main.py`
4. Configure Open FFB board via the Open FFB Configurator
5. Fly

## Documentation

This project is developed using AI coding assistants under human oversight.
If you are new to the project, read `ARCHITECTURE.md` first.

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System overview, data flow, component descriptions, directory structure, code comment standard |
| [`CONSTRAINTS.md`](CONSTRAINTS.md) | System constraints with FMEA traceability |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Code comment standard, contribution workflow, ground rules |
| [`KEY_DECISION_LOG.md`](KEY_DECISION_LOG.md) | Architectural decisions and rationale |
| [`CODE_DECISION_LOG.md`](CODE_DECISION_LOG.md) | Code-level decisions and debugging heuristics |
| [`docs/KANBAN_SETUP.md`](docs/KANBAN_SETUP.md) | Project board configuration |
| [`docs/FMEA.md`](docs/FMEA.md) | Failure Mode and Effects Analysis — known failure modes and mitigations |

## Ground Rules

This project uses AI coding assistants under 11 operational ground rules for
traceability and safe AI-assisted development. See [`CONTRIBUTING.md`](CONTRIBUTING.md)
for full details.

## License

[MIT](LICENSE)
