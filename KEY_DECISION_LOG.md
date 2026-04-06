# Key Decision Log

Architectural, infrastructural, and tooling decisions. One entry per decision.
New decisions append; resolved decisions are updated in-place (never deleted).

---

## DECISION 1 — Total rewrite of Laser Wing Python code for ODrive S1

**Status:** RESOLVED — Rewrite selected

**Resolution:** Complete rewrite of the Laser Wing prototype Python codebase,
redesigned for the ODrive S1 motor controller platform with GIM 8108-8 motors.

**Rationale:** The original Laser Wing codebase is dead (project abandoned).
The existing code has bugs in center logic (FM-001), unreliable calibration
(FM-002), and no thermal management (FM-003, FM-005). Architectural changes
are required to support the ODrive S1 CAN bus interface and the Open FFB
Configurator-based FFB pipeline. Patching the old code is not viable.

**FMEA Impact:** FM-001, FM-002, FM-003, FM-005 — all failure modes from the
prototype are addressed in the new architecture.

**Documents updated:**
- `ARCHITECTURE.md` — Full system architecture defined
- `CONSTRAINTS.md` — Constraint register created
- `docs/FMEA.md` — Failure modes seeded from prototype experience

**Downstream impact:**
- All Python code is new — no migration path from Laser Wing codebase
- ODrive S1 Python package is a hard dependency (C-002)
- Open FFB Configurator handles FFB pipeline; Python scope limited to config/calibration

---

## DECISION 2 — Python scope limited to ODrive S1 configuration and calibration

**Status:** RESOLVED — Config/calibration tool only

**Resolution:** The Python codebase in this repository is strictly a setup and
calibration tool for the ODrive S1 controllers. All real-time FFB processing
(force calculation, effect management, telemetry parsing) is handled by the
Open FFB Configurator via CAN bus.

**Rationale:** The Open FFB Configurator already handles the full FFB pipeline:
DirectInput FFB effects from IL-2, translation to motor commands, and CAN bus
communication with the ODrive S1 controllers. Duplicating this in Python would
add complexity, latency, and a second point of failure.

**FMEA Impact:** FM-001 (center oscillation), FM-004 (force profiles) — these
are now configurator-side concerns, not Python-side. FM-002 (calibration) and
FM-005 (thermal monitoring) remain relevant to the overall system.

**Documents updated:**
- `ARCHITECTURE.md` — Scope clarified in system overview and data flow
- `CONSTRAINTS.md` — C-003 updated; C-007, C-008, C-009 marked as configurator-side

**Downstream impact:**
- `src/ffb_engine/`, `src/hid_interface/`, `src/sim_interface/` not created
- Force profile tuning happens in the Open FFB Configurator, not in YAML files consumed by Python
- Thermal monitoring fix (FM-005) must be addressed in the configurator, not Python
