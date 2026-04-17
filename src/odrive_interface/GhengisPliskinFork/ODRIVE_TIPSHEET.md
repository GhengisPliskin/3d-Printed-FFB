# ODrive S1 Setup Scripts — Tipsheet

**GIM 8108-8 Force Feedback Joystick | ODrive S1 Firmware 0.6.11**

Config values are audit-corrected against the RMDX8 Pro V2 reference (see `MOTOR_COMPARISON.md`).

---

## Environment Setup

> Copy-paste the block below into a terminal to create the Python environment.
> Run this **once** on a fresh machine. Re-activate the venv each new terminal session.

```
:: ─── ONE-TIME INSTALL ───────────────────────────────────
:: Python 3.14 is NOT compatible with the odrive package.
:: Use Python 3.13.

winget install Python.Python.3.13

:: Create and activate virtual environment
py -3.13 -m venv C:\odrive_env
C:\odrive_env\Scripts\activate
pip install --upgrade pip
pip install --upgrade odrive

:: Verify install (should print a MotorType value)
python -c "import odrive; from odrive.enums import MotorType; print(MotorType.PMSM_CURRENT_CONTROL)"
```

```
:: ─── EVERY NEW TERMINAL ─────────────────────────────────
C:\odrive_env\Scripts\activate
:: Prompt shows (odrive_env) when active.
```

---

## Three Scripts, Three Stages

Each script handles one stage of the setup process. Run them in order.

| Script | When | Stick State |
|---|---|---|
| `odrive_setup.py` | First-time config + calibration | **Disassembled** — motor free to spin |
| `odrive_verify.py` | After setup, to validate flash | **Any** — reboots automatically |
| `odrive_center.py` | After reassembling stick | **Assembled** — stick at physical center |

---

## Stage 1 — Backup and Setup

### Back Up Current Config

Connect one ODrive via USB. Close OpenFFBoard configurator and odrivetool.

```
C:\odrive_env\Scripts\activate
odrivetool backup-config backup_pitch.json
```

Swap USB to the other ODrive:

```
odrivetool backup-config backup_roll.json
```

Label each ODrive board physically (marker or tape) with "PITCH" or "ROLL" and the serial number.

### Run Setup

Activate the venv, navigate to your scripts directory, then:

```
python odrive_setup.py --pitch
```

Swap USB cable, then:

```
python odrive_setup.py --roll
```

To include harmonic compensation and anti-cogging calibration (adds ~6 minutes per axis):

```
python odrive_setup.py --pitch --anticogging
python odrive_setup.py --roll --anticogging
```

**What happens:** The script runs three phases automatically.

1. **Phase 1** — Erases to factory defaults, writes all config (audit-corrected values from RMDX8 Pro V2 reference), saves, reboots.
2. **Phase 2** — Runs full motor+encoder calibration, sets startup behavior, saves. With `--anticogging`, Phase 2 also runs harmonic compensation followed by a full anti-cogging sweep.
3. **Phase 3** — Reconnects and verifies all values persisted to flash. Auto-retries if the S1 dropped the save during reboot.

Nothing moves until you press Enter. **Ctrl+C** at any time zeros torque and stops the motor.

---

## Stage 2 — Verify

The verify script reboots the ODrive to purge RAM, then reads exclusively from flash.

```
C:\odrive_env\Scripts\activate
python odrive_verify.py --pitch
python odrive_verify.py --roll
```

Runs 9 checks: error state, startup state, Vbus, config values (including audit-critical gains), oscillation protection, phase resistance, phase inductance, encoder stability, power protection. Optional torque symmetry test at the end (skippable).

The config check now validates the audit-corrected controller gains (`vel_gain=3.0`, `vel_integrator_gain=2.2`, `pos_gain=38.0`, `vel_limit=1000`).

---

## Stage 3 — Center

```
C:\odrive_env\Scripts\activate
python odrive_center.py --pitch
python odrive_center.py --roll
```

Hold the stick at physical center, press Enter. The script averages 10 mapped position readings, computes an incremental offset correction, saves to flash, and reboots the ODrive. The ODrive will disconnect and reconnect during reboot — this is expected.

After centering, in the **OpenFFBoard configurator**:

1. Click **"center position"** on each axis
2. Check **"save offset"** on each ODrive tab
3. Save — this persists the offset across power cycles

---

## Emergency Stop

**Ctrl+C** at any time zeros torque and forces the motor to IDLE. Works in all three scripts, including mid-calibration and mid-torque-test.

In odrivetool, the equivalent command:

```
odrv0.axis0.requested_state = AxisState.IDLE
```

---

## Audit-Corrected Values

These parameters were changed based on `MOTOR_COMPARISON.md` (RMDX8 Pro V2 reference). The prior GIM config was running at near-default ODrive values — identical to the broken state the RMDX8 was in before tuning.

| Parameter | Old (Broken) | New (Corrected) | Audit Item |
|---|---|---|---|
| vel_gain | 0.02 | 3.0 | #1 — 150x delta, primary trim fix |
| vel_integrator_gain | 0.0 | 2.2 | #2 — was zero, couldn't fight gravity |
| vel_limit | 1.0 | 1000.0 | #3 — was capping at ~45°/s output |
| enable_torque_mode_vel_limit | true | false | #3 — disable velocity clipping |
| current_control_bandwidth | 150 Hz | 1000 Hz | #4 — torque tracking too slow |
| current_slew_rate_limit | 800 A/s | 10,000 A/s | #5 — force transitions 12.5x too slow |
| brake_resistor0.enable | false | true | #6 — no regen dump on 48V bus |
| dc_max_negative_current | −2 A | −10 A | #6 — regen absorption was capped |
| pos_gain | 15.0 | 38.0 | #9 — spring stiffness 2.5x too weak |
| encoder_bandwidth | 200 Hz | 1000 Hz | #10 — noisy velocity estimation |
| resistance_calib_max_voltage | 4.0 V | 8.0 V | — RMDX8 uses 8V for low-R motor |
| input_filter_bandwidth | 100 Hz | 20 Hz | — match RMDX8 noise filter |
| power_torque_report_filter_BW | 150 Hz | 8000 Hz | — telemetry bandwidth |
| torque_constant | 1.00 Nm/A | 1.45 Nm/A | — static test: 8.27 / KV 5.7 |

---

## Troubleshooting

### Calibration Fails: PHASE_RESISTANCE_OUT_OF_RANGE

Open `odrive_setup.py`, find `RESISTANCE_CALIB_MAX_VOLTAGE = 8.0`, raise by 0.5V increments (try 8.5, then 9.0). Re-run. For other errors, use `dump_errors(odrv0)` in odrivetool.

### Forces Reversed on One Axis

OpenFFBoard's "invert axis" checkbox is unreliable in some firmware versions.

1. Power off the ODrive
2. Swap any two of the three motor phase wires (A↔B, B↔C, or A↔C) at the ODrive screw terminals
3. Re-run `python odrive_setup.py` for that axis (recalibration required)
4. Re-run `python odrive_center.py` for that axis
5. Re-center and save offset in OpenFFBoard configurator

### Drive Won't Enter Closed Loop on Power-Up

Check in odrivetool:

```
odrv0.axis0.active_errors
odrv0.axis0.disarm_reason
```

If `disarm_reason` shows `INITIALIZING` with no other errors, the Phase 2 save dropped. Fix manually:

```
odrv0.clear_errors()
odrv0.axis0.config.startup_closed_loop_control = True
odrv0.save_configuration()
```

Power cycle and confirm blue/teal LED (closed loop).

### Forces Feel Sluggish or Asymmetric

The audit-corrected bandwidths may need per-build tuning. Start from the corrected values and adjust one at a time in odrivetool:

```
odrv0.axis0.config.motor.current_control_bandwidth = 1000
odrv0.save_configuration()
```

If oscillation appears, lower `vel_gain` from 3.0 toward 1.5 (GIM has 75x less rotor inertia than RMDX8).

### Oscillation Persists

Lower in this order: `vel_gain` → `vel_integrator_gain` → `input_filter_bandwidth`. The GIM's low inertia means it responds faster than the RMDX8 — gains that work on the heavier motor may overshoot on the lighter one.

---

## OpenFFBoard Integration Checklist

1. Power cycle ODrive — should auto-enter closed loop (blue/teal LED)
2. Open OpenFFBoard configurator
3. Verify CAN comms: pitch = node 0, roll = node 1, 1 Mbps
4. Set max torque range for GIM 8108-8 (nominal 7.5 Nm output)
5. Center each axis and check "save offset" on each ODrive tab
6. If drive goes to standby immediately — check configurator error logs, re-center
7. If forces reversed — swap two motor phase wires (see above)

---

## File Reference

| File | Purpose |
|---|---|
| `odrive_setup.py` | Config + calibration + flash verify (motor disassembled) |
| `odrive_verify.py` | Post-setup validation + torque symmetry test |
| `odrive_center.py` | Set zero offset (stick assembled) |
| `MOTOR_COMPARISON.md` | RMDX8 Pro V2 vs GIM 8108-8 config audit |
| `~/odrive_backups/*.json` | Pre-change config snapshots |
