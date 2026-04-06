# Constraints Register

All constraints are binding. Decisions that impact a constraint must reference its ID
in the decision log entry and any relevant prompt headers.

| ID | Constraint | Type | Source | Applies To |
|---|---|---|---|---|
| C-001 | Python 3.10+ only, no C extensions | Tech Stack | Project decision | Python code |
| C-002 | Must support ODrive S1 via odrive Python package | Tech Stack | Hardware | Python code |
| C-003 | Open FFB board is the USB HID device, not the host PC. The Open FFB Configurator handles DirectInput FFB effects and CAN bus motor commands. | Architecture | Hardware | System |
| C-004 | 2-axis only (pitch + roll), no yaw | Scope | Phase 1 | System |
| C-005 | All 3D printed structural parts must withstand sustained 60°C without deformation | Thermal | FM-003 | Hardware |
| C-006 | Startup calibration must complete index search and center verification before enabling force output | Safety | FM-002 | Python code |
| C-007 | Center spring must implement configurable deadband (minimum ±0.5° configurable) | Functional | FM-001 | Open FFB Configurator |
| C-008 | Thermal monitoring must auto-reduce torque at configurable temperature threshold | Safety | FM-003, FM-005 | Open FFB Configurator (currently non-functional — see FM-005) |
| C-009 | Force profiles must be per-aircraft configurable via YAML | Functional | FM-004 | Open FFB Configurator |
| C-010 | All modules must include module docstrings, function docstrings, and block comments | Code Quality | Ground Rule 11 | Python code |

## Notes

- **C-003**: The Python codebase is a configuration/calibration tool only. The Open FFB
  Configurator handles the full FFB pipeline (IL-2 telemetry → force effects → CAN bus
  motor commands → ODrive S1 controllers).
- **C-007, C-008, C-009**: These constraints apply to the Open FFB Configurator
  configuration, not to the Python codebase. They are tracked here for system-level
  traceability.
- **C-008**: Thermal monitoring is currently non-functional in the user's setup.
  See FM-005 for details. This is the highest-priority open issue.
