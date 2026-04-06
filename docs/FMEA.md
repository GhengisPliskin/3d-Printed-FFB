# Failure Mode and Effects Analysis (FMEA)

## Risk Priority Legend
- **RPN** = Severity (S) x Occurrence (O) x Detection (D)
- **Scale:** 1 (lowest risk) to 10 (highest risk) for each factor
- **Action threshold:** RPN >= 100 requires a mitigation plan before proceeding.

## Register

| ID | Failure Mode | Potential Effect | S | O | D | RPN | Suspected Cause | Mitigation | Status | Owner |
|---|---|---|---|---|---|---|---|---|---|---|
| FM-001 | Pitch axis oscillation around center | Unusable center feel, pilot fatigue | 8 | 7 | 4 | 224 | PID tuning too aggressive near center; insufficient deadband; encoder noise amplified at low deflection | Implement configurable deadband (C-007), tune PID with derivative filter, add low-pass on encoder feedback. Configured via Open FFB Configurator. | Open | — |
| FM-002 | Inconsistent center on power-up | Joystick drifts from neutral after startup | 7 | 5 | 5 | 175 | Calibration sequence not homing reliably; index pulse missed or offset not stored | Enforce index search at startup (C-006), store/verify offset, add center-verify step before enabling forces. Implemented in Python calibration tool. | Open | — |
| FM-003 | 3D printed component overheating | Structural failure, PLA softening, axis binding | 9 | 4 | 7 | 252 | Motor heat conducting through mounts; sustained high-torque operation; insufficient thermal breaks | Thermal monitoring with auto-throttle (C-008), PETG/ASA for thermal-critical parts, add thermal breaks to motor mounts. **Note:** Thermal monitoring is currently non-functional — see FM-005. | Open | — |
| FM-004 | Force profile mismatch across IL-2 aircraft | Centering force appropriate on spec Laser Wing but wrong on 3D-printed variant | 6 | 8 | 6 | 288 | Force scaling assumes Laser Wing geometry/gear ratio; 3D print has different compliance and backlash | Per-aircraft force profiles (C-009), geometry-aware force scaling, calibration routine that measures actual mechanical response. Configured via Open FFB Configurator. | Open | — |
| FM-005 | Non-functional thermal monitoring | Motors and 3D-printed mounts can overheat with zero automated protection; risk of PLA softening, structural failure, or motor damage | 8 | 8 | 8 | 512 | Open FFB Configurator thermal monitoring feature is not working in current setup; no alerts, no automated torque reduction | Diagnose and fix configurator thermal monitoring (C-008). Until fixed: limit session duration, manually monitor motor temperatures, use PETG/ASA for motor mounts (C-005). | Open | — |

## Scoring Rationale

### FM-001 — Pitch Axis Oscillation (RPN 224)
- **S=8**: Directly affects usability — oscillating center makes precision flying impossible.
- **O=7**: Common failure mode in PID-controlled systems, especially near zero-deflection where encoder noise dominates.
- **D=4**: Detectable during bench testing before flight — oscillation is obvious when moving through center.

### FM-002 — Inconsistent Center (RPN 175)
- **S=7**: Drift from neutral is disorienting but not catastrophic — pilot can recalibrate mid-session.
- **O=5**: Intermittent — depends on encoder index pulse reliability and power-up conditions.
- **D=5**: Not always caught before flight; small offsets may only be noticed during precision maneuvers.

### FM-003 — Component Overheating (RPN 252)
- **S=9**: Structural failure of motor mounts during operation — safety risk.
- **O=4**: Requires sustained high-torque operation (e.g., extended combat maneuvering).
- **D=7**: Detection is POOR because thermal monitoring is currently non-functional (FM-005). Without automated alerts, overheating is only noticed when physical symptoms appear (binding, softening).

### FM-004 — Force Profile Mismatch (RPN 288)
- **S=6**: Forces feel "wrong" but system still functions — immersion-breaking rather than dangerous.
- **O=8**: Affects every aircraft type — the Laser Wing force profiles don't map to 3D-printed geometry.
- **D=6**: Subjective "feel" is hard to quantify objectively; requires pilot feedback for each aircraft.

### FM-005 — Non-functional Thermal Monitoring (RPN 512)
- **S=8**: Same severity as FM-003 — overheating can damage motors and melt PLA mounts.
- **O=8**: Always occurring — the monitoring system is broken, so every session is unprotected.
- **D=8**: No automated detection whatsoever — user has no alerts, only discovers overheating when damage occurs or binding is felt.
- **CRITICAL**: Highest-RPN item. Must be resolved before sustained operation.

## Revision History

| Date | Change | Author | Amendment # |
|---|---|---|---|
| 2026-04-05 | Initial FMEA generated from project scaffolding. FM-001 through FM-004 seeded from Laser Wing prototype failure modes. FM-005 added for non-functional thermal monitoring. | Claude Opus / Pablo Larson | — |
