#!/usr/bin/env python3
"""
MODULE: odrive_setup.py
PURPOSE: ODrive S1 config + calibration for GIM 8108-8 planetary gearbox BLDC
         motors in the 3D-Printed FFB joystick system. Three-phase workflow:
           Phase 1 — Apply all configuration → save → reboot
           Phase 2 — Run FULL_CALIBRATION_SEQUENCE → set startup behavior → save
           Phase 3 — Reconnect and verify all values persisted to flash
         Center position is handled by odrive_center.py (run after stick assembly).
FMEA: FM-001 (PID tuning), FM-002 (calibration reliability), FM-006 (startup)
PHASE: 1

USAGE:
    python odrive_setup.py              # Interactive axis selection
    python odrive_setup.py --pitch      # Pitch axis (CAN node 0)
    python odrive_setup.py --roll       # Roll axis  (CAN node 1)
    python odrive_setup.py --pitch --anticogging  # Include anti-cogging cal

FIRMWARE: ODrive S1, 0.6.11 (master)
REQUIREMENTS: pip install odrive  (Python 3.13 — 3.14 is NOT compatible)

AUDIT HISTORY:
    2026-04-01  MOTOR_COMPARISON.md audit against RMDX8 Pro V2 reference config.
                12 critical/review items identified. All incorporated below.
                Primary fix: controller gains, bandwidth, and power protection
                were at near-default values — not tuned for the GIM 8108-8.
"""

import odrive
from odrive.enums import (
    AxisState,
    ControlMode,
    InputMode,
    MotorType,
)
import argparse
import atexit
import json
import math
import os
import signal
import sys
import time
from datetime import datetime

# The EncoderId enum was added in ODrive 0.6.11. Older firmware versions
# expose the onboard encoder as raw integer 1 instead of a named constant.
# This fallback prevents ImportError on mismatched odrive package versions.
try:
    from odrive.enums import EncoderId
    ONBOARD_ENC = EncoderId.ONBOARD_ENCODER0
except (ImportError, AttributeError):
    ONBOARD_ENC = 1
    print("⚠ EncoderId.ONBOARD_ENCODER0 not found — using raw value 1\n")


# ═══════════════════════════════════════════════════════════════════
#  GIM 8108-8 DATASHEET VALUES + RMDX8 PRO V2 AUDIT CORRECTIONS
# ═══════════════════════════════════════════════════════════════════
# Source: GIM 8108-8 datasheet (Chinese/English bilingual spec sheet)
# Audit:  MOTOR_COMPARISON.md — RMDX8 Pro V2 (working) vs GIM 8108-8 (broken)
#
# The original GIM config was running at near-default ODrive values.
# The RMDX8 Pro V2 had identical broken trim behavior before its ODrive S1
# was tuned. The fix is replicating the RMDX8's proven config, adjusted
# for the GIM's lower inertia (75x less), different Kt, and 48V bus.

# ── Motor core (from datasheet) ──────────────────────────────────
POLE_PAIRS              = 21        # Datasheet: 21 pole pairs
TORQUE_CONSTANT         = 1.45      # Static test: 8.27 / KV 5.7 = 1.45 Nm/A (confirmed empirically)
PHASE_RESISTANCE        = 0.439     # Datasheet: 0.439 Ω phase-to-phase
EXPECTED_PHASE_R_LTN    = 0.439     # S1 0.6.11 stores phase-to-phase value
PHASE_R_TOLERANCE       = 0.10      # Ω — measured variation tolerance

# ── Current limits ───────────────────────────────────────────────
# Datasheet nominal current is 7A. Stall current is 25A.
# current_soft_max sets the operational ceiling; current_hard_max is
# the hardware protection fault threshold.
CURRENT_SOFT_MAX        = 7.0       # Datasheet nominal: 7A
CURRENT_HARD_MAX        = 25.0      # Datasheet stall: 25A

# ── Gearbox (from datasheet) ────────────────────────────────────
# The 8:1 planetary gearbox means one output-shaft turn = 8 motor turns.
# pos_vel_mapper.scale converts motor-side units to output-shaft units.
GEARBOX_RATIO           = 8
POS_VEL_MAPPER_SCALE    = 1.0 / GEARBOX_RATIO  # = 0.125

# ── Calibration parameters ───────────────────────────────────────
# AUDIT #4 note: resistance_calib_max_voltage was 4.0V on the GIM vs
# 8.0V on the RMDX8. The GIM's low phase resistance (0.439 Ω) needs
# adequate voltage to get a clean resistance measurement.
CALIBRATION_CURRENT             = 8.3   # Sufficient for reliable cal on low-R motor
RESISTANCE_CALIB_MAX_VOLTAGE    = 8.0   # AUDIT: raised from 4.0 to match RMDX8

# Lock-in parameters control how the motor moves during encoder
# offset calibration. These must produce enough torque to overcome
# the GIM 8108-8's cogging + gearbox friction without overshooting.
LOCKIN_CURRENT                  = 8.0
LOCKIN_RAMP_TIME                = 0.4
LOCKIN_RAMP_DISTANCE            = math.pi
LOCKIN_VEL                      = 40.0
LOCKIN_ACCEL                    = 20.0

# ── Motor model / feedforward ────────────────────────────────────
# Back-EMF and dI/dt feedforward are disabled on both the RMDX8 and
# GIM configs. Flux linkage is set but not actively used.
BEMF_FF_ENABLE                  = False
DI_DT_FF_ENABLE                 = False
FLUX_LINKAGE                    = 0.14
FLUX_LINKAGE_VALID              = True
FIELD_WEAKENING_ENABLE          = False

# AUDIT #5: current_slew_rate_limit was 800 A/s on GIM vs 10,000 on
# RMDX8. At 800 A/s, the GIM takes ~8.75ms to reach full current —
# 12.5x slower than the RMDX8's 0.7ms. Force transitions feel mushy.
CURRENT_SLEW_RATE_LIMIT         = 10_000.0  # AUDIT: raised from 800

# AUDIT: power/torque reporting bandwidth was 150 Hz vs RMDX8's 8000 Hz.
# Lower bandwidth means the host (OpenFFBoard) gets stale force telemetry.
POWER_TORQUE_REPORT_FILTER_BW   = 8000.0    # AUDIT: raised from 150

# ── Controller gains ─────────────────────────────────────────────
# AUDIT #1: vel_gain was 0.02 on GIM vs 3.0 on RMDX8 (150x delta).
# This is the single largest behavioral difference. Without velocity
# damping, gravity pulls the pitch axis down unopposed and the stick
# drifts through trim forces. Starting at RMDX8's value of 3.0.
# The GIM has 75x less rotor inertia, so may need reduction to 1.5-2.0
# if oscillation appears.
POS_GAIN                = 38.0     # AUDIT #9: raised from 15.0 (RMDX8 = 38.0)
VEL_GAIN                = 3.0      # AUDIT #1: raised from 0.02 (RMDX8 = 3.0)
VEL_INTEGRATOR_GAIN     = 2.2      # AUDIT #2: raised from 0.0 (RMDX8 = 2.2)

# ── Controller tuning ────────────────────────────────────────────
# AUDIT #3: vel_limit was 1.0 turn/s (motor-side) with limit enabled.
# That caps output shaft speed at ~45°/s — far too restrictive.
# RMDX8 uses 1000 with limit disabled. We set 1000 and disable for
# safety-through-design: if vel limit is ever re-enabled, 1000 won't
# clip normal operation.
VEL_LIMIT               = 1000.0   # AUDIT #3: raised from 1.0 (RMDX8 = 1000)

# AUDIT: RMDX8 uses input_filter_bandwidth = 20 Hz. The GIM was at 70 Hz
# in the config dump (script had 100 Hz). Lower bandwidth smooths
# high-frequency noise that compounds velocity estimation error.
INPUT_FILTER_BW         = 20.0     # AUDIT: lowered from 100 (RMDX8 = 20)

# ── Encoder bandwidth ────────────────────────────────────────────
# AUDIT #10: encoder_bandwidth was 200 Hz on GIM vs 1000 Hz on RMDX8.
# Lower encoder bandwidth = noisier velocity estimation, which
# compounds the already-low vel_gain problem.
ENCODER_BW              = 1000     # AUDIT: raised from 700 (RMDX8 = 1000)
COMMUTATION_ENC_BW      = 1000     # Match encoder_bandwidth

# ── Current loop bandwidth ───────────────────────────────────────
# AUDIT #4: current_control_bandwidth was 150 Hz on GIM vs 1000 Hz
# on RMDX8 (6.7x). The current loop governs torque tracking accuracy.
# At 150 Hz the motor can't follow rapid force changes.
CURRENT_CONTROL_BW      = 1000     # AUDIT: raised from 200 (RMDX8 = 1000)

# ── Torque ramp and soft limits ──────────────────────────────────
# AUDIT #11: torque_ramp_rate is bypassed in PASSTHROUGH input mode.
# Setting it anyway as a safety net in case input mode changes.
TORQUE_RAMP_RATE        = 0.01     # AUDIT: RMDX8 value (bypassed in passthrough)

# AUDIT: RMDX8 has explicit torque soft limits (±31.25 Nm). The GIM
# had no limits set. Adding ±7.0 Nm based on datasheet nominal torque.
TORQUE_SOFT_MIN         = -7.0     # AUDIT: new — matches datasheet nominal
TORQUE_SOFT_MAX         = 7.0      # AUDIT: new — matches datasheet nominal

# ── CAN ──────────────────────────────────────────────────────────
CAN_BAUD                = 1_000_000  # 1 Mbps — required for 1 kHz FFB update rate
CAN_NODE_IDS            = {"pitch": 0, "roll": 1}

# ── Power / protection ───────────────────────────────────────────
BRAKE_RESISTOR_ENABLE   = True
BRAKE_RESISTANCE        = 2.0

# AUDIT #6: GIM had brake resistor DISABLED and dc_max_negative_current
# capped at -2A. When the motor decelerates, regenerative energy has
# nowhere to go → overvoltage faults. Worse on a 48V system.
DC_MAX_NEGATIVE_CURRENT = -10.0    # AUDIT #6: was -2.0 (RMDX8 = -100.0)
DC_BUS_UNDERVOLTAGE     = 40       # 48V PSU — trip below 40V
DC_BUS_OVERVOLTAGE      = 53       # 48V PSU — trip above 53V

# ── Vbus validation ──────────────────────────────────────────────
# Pre-flight check ensures PSU is delivering stable 48V before we
# attempt calibration. Unstable Vbus causes phantom errors.
VBUS_MIN_FOR_CAL        = 38.0
VBUS_STABILITY_SAMPLES  = 10
VBUS_STABILITY_TOL      = 3.0      # Widened to 3.0V for PSU ripple tolerance

# ── Anti-cogging ─────────────────────────────────────────────────
# AUDIT: RMDX8 anticogging.max_torque = 3.0 Nm vs GIM's 1.0 Nm.
# Higher max allows the compensation map to correct larger cogging forces.
ANTICOGGING_MAX_TORQUE  = 3.0      # AUDIT: raised from 1.0 (RMDX8 = 3.0)

# ── Backup ───────────────────────────────────────────────────────
BACKUP_DIR = os.path.join(os.path.expanduser("~"), "odrive_backups")


# ═══════════════════════════════════════════════════════════════════
#  SAFETY — Emergency stop handler
# ═══════════════════════════════════════════════════════════════════
# Ctrl+C at any point zeros torque and forces the motor to IDLE.
# This works mid-calibration, mid-torque-test, and during any phase.
# Previous saved calibration in flash is untouched — only RAM state
# is modified by the emergency stop.
_active_odrv = None


def _emergency_disarm(signum=None, frame=None):
    """
    WHAT: Immediately zero torque and force motor to IDLE state.
    WHY: Safety-critical interrupt handler — prevents uncontrolled motor
         behavior if the user presses Ctrl+C or the script receives SIGTERM.
         Must execute quickly and tolerate partial USB disconnection.
    ARGS:
        signum: Signal number (from signal handler) or None (from atexit).
        frame: Stack frame (unused, required by signal API).
    RETURNS: None. Exits with code 1 if called from a signal.
    FMEA: FM-006 — Startup/safety sequence integrity.
    """
    global _active_odrv
    if _active_odrv is not None:
        # Zero torque first — this is the most time-critical action.
        # If USB drops during IDLE transition, at least torque is zeroed.
        try:
            _active_odrv.axis0.controller.input_torque = 0
        except Exception:
            pass
        try:
            _active_odrv.axis0.requested_state = AxisState.IDLE
        except Exception:
            pass
        print("\n  ⛔ Emergency disarm — motor IDLE, torque zeroed.")
    if signum is not None:
        sys.exit(1)


# Register emergency disarm on Ctrl+C, SIGTERM, and normal exit.
signal.signal(signal.SIGINT, _emergency_disarm)
signal.signal(signal.SIGTERM, _emergency_disarm)
atexit.register(_emergency_disarm)


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def wait_for_idle(ax, timeout=30):
    """
    WHAT: Block until the axis returns to IDLE state or timeout expires.
    WHY: Calibration sequences transition through multiple states before
         returning to IDLE. We must wait for completion before checking
         results or proceeding to the next phase.
    ARGS:
        ax: ODrive axis object (odrv.axis0).
        timeout: Maximum seconds to wait before declaring failure.
    RETURNS: True if IDLE reached, False if timeout.
    FMEA: FM-002 — Calibration reliability.
    """
    start = time.time()
    while ax.current_state != AxisState.IDLE:
        if time.time() - start > timeout:
            print(f"  TIMEOUT waiting for IDLE (state {ax.current_state})")
            return False
        time.sleep(0.5)
    return True


def check_errors(odrv, stage_name):
    """
    WHAT: Check for active errors on the ODrive after a state transition.
    WHY: ODrive reports failures via the active_errors bitmask. If nonzero
         after calibration, the calibration data is invalid and must not
         be saved to flash.
    ARGS:
        odrv: Connected ODrive instance.
        stage_name: Human-readable label for the operation being checked.
    RETURNS: True if no errors, False if errors present.
    FMEA: FM-002 — Calibration reliability.
    """
    errs = odrv.axis0.active_errors
    if errs != 0:
        print(f"  ✘ {stage_name} FAILED — active_errors: {hex(errs)}")
        try:
            from odrive.utils import dump_errors
            dump_errors(odrv)
        except Exception:
            pass
        return False
    return True


def get_position(ax):
    """
    WHAT: Read the current relative position from the pos_vel_mapper.
    WHY: Used for drift monitoring during calibration and anti-cogging.
         The pos_vel_mapper.pos_rel gives the gear-ratio-scaled position
         (output shaft turns), not raw motor turns.
    ARGS:
        ax: ODrive axis object.
    RETURNS: Float — current position in output shaft turns.
    FMEA: N/A
    """
    return ax.pos_vel_mapper.pos_rel


def connect_odrive(timeout=15):
    """
    WHAT: Discover and connect to an ODrive S1 via USB.
    WHY: Each script phase requires a fresh USB connection because the
         ODrive S1 reboots (dropping USB) after save_configuration.
    ARGS:
        timeout: Seconds to wait for USB enumeration.
    RETURNS: ODrive instance, or None if not found.
    FMEA: N/A
    """
    print(f"  Searching for ODrive...")
    odrv = odrive.find_any(timeout=timeout)
    if odrv is None:
        print(f"  ✘ No ODrive found.")
        return None
    sn = getattr(odrv, 'serial_number', 'unknown')
    fw = getattr(odrv, 'fw_version_major', '?')
    fw_min = getattr(odrv, 'fw_version_minor', '?')
    fw_rev = getattr(odrv, 'fw_version_revision', '?')
    print(f"  Found ODrive — serial: {sn}, fw: {fw}.{fw_min}.{fw_rev}")
    print(f"  Vbus: {odrv.vbus_voltage:.1f} V")
    return odrv


def safe_set(obj, attr, value, label=None):
    """
    WHAT: Attempt to set an attribute, printing a warning if it doesn't exist.
    WHY: ODrive firmware versions expose different attribute sets. Some
         parameters (watchdog, current_control_bandwidth) may not exist
         on all S1 firmware builds. This prevents a missing attribute
         from crashing the entire setup sequence.
    ARGS:
        obj: Object to set the attribute on.
        attr: Attribute name string.
        value: Value to assign.
        label: Optional human-readable name for the warning message.
    RETURNS: True if set succeeded, False if attribute missing.
    FMEA: N/A
    """
    name = label or attr
    try:
        setattr(obj, attr, value)
        return True
    except AttributeError:
        print(f"  ⚠ {name} not available on this firmware — skipped")
        return False


# ═══════════════════════════════════════════════════════════════════
#  VBUS VALIDATION
# ═══════════════════════════════════════════════════════════════════

def validate_vbus(odrv):
    """
    WHAT: Pre-flight check that the 48V PSU is delivering stable voltage.
    WHY: Running calibration on an unstable or under-voltage bus produces
         phantom errors (PHASE_RESISTANCE_OUT_OF_RANGE, DC_BUS_UNDER_VOLTAGE).
         Checking upfront saves time and prevents confusing failures.
    ARGS:
        odrv: Connected ODrive instance.
    RETURNS: True if Vbus is stable and above minimum, False otherwise.
    FMEA: FM-006 — Startup sequence integrity.
    """
    print(f"  Checking Vbus stability (1s)...")
    readings = []
    for _ in range(VBUS_STABILITY_SAMPLES):
        readings.append(odrv.vbus_voltage)
        time.sleep(0.1)
    v_mean = sum(readings) / len(readings)
    v_spread = max(readings) - min(readings)
    print(f"  Vbus: {v_mean:.1f} V avg (spread: {v_spread:.2f} V)")
    if v_mean < VBUS_MIN_FOR_CAL:
        print(f"  ✘ Vbus too low ({v_mean:.1f}V < {VBUS_MIN_FOR_CAL}V).")
        return False
    if v_spread > VBUS_STABILITY_TOL:
        print(f"  ⚠ Vbus unstable ({v_spread:.2f}V spread).")
        if input("  Continue? (y/n): ").strip().lower() != 'y':
            return False
    return True


# ═══════════════════════════════════════════════════════════════════
#  CONFIG BACKUP
# ═══════════════════════════════════════════════════════════════════

def backup_config(odrv, axis_name):
    """
    WHAT: Save the current ODrive configuration to a JSON file.
    WHY: Before erasing to factory defaults, preserve the existing config
         so it can be manually restored if the new config causes problems.
         Backups are not auto-restorable — they serve as reference.
    ARGS:
        odrv: Connected ODrive instance.
        axis_name: "pitch" or "roll" — used in the backup filename.
    RETURNS: None. Prints the backup filepath on success.
    FMEA: N/A
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    sn = getattr(odrv, 'serial_number', 'unknown')
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(BACKUP_DIR, f"odrive_{axis_name}_{sn}_{ts}.json")
    try:
        ax = odrv.axis0
        m = ax.config.motor
        c = ax.controller.config
        backup = {
            "serial_number": str(sn), "axis_name": axis_name, "timestamp": ts,
            "vbus_voltage": float(odrv.vbus_voltage),
            "motor": {
                "pole_pairs": int(m.pole_pairs),
                "torque_constant": float(m.torque_constant),
                "current_soft_max": float(m.current_soft_max),
                "current_hard_max": float(m.current_hard_max),
                "phase_resistance": float(m.phase_resistance) if m.phase_resistance else None,
            },
            "controller": {
                "control_mode": int(c.control_mode),
                "pos_gain": float(c.pos_gain),
                "vel_gain": float(c.vel_gain),
                "vel_integrator_gain": float(c.vel_integrator_gain),
            },
            "can": {
                "baud_rate": int(odrv.can.config.baud_rate),
                "node_id": int(ax.config.can.node_id),
            },
        }
        with open(filepath, 'w') as f:
            json.dump(backup, f, indent=2)
        print(f"  ✔ Backup: {filepath}")
    except Exception as e:
        print(f"  ⚠ Backup failed: {e}")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 1: CONFIGURE + SAVE + REBOOT
# ═══════════════════════════════════════════════════════════════════

def phase1_configure(odrv, axis_name):
    """
    WHAT: Apply all motor, encoder, controller, and power configuration
          to the ODrive, then save to flash and reboot.
    WHY: The ODrive S1 ships with default values unsuitable for the
         GIM 8108-8 + OpenFFBoard force feedback application. Every
         parameter here was validated against the RMDX8 Pro V2 reference
         config (MOTOR_COMPARISON.md audit).
    ARGS:
        odrv: Connected ODrive instance (freshly erased to factory defaults).
        axis_name: "pitch" or "roll" — determines CAN node ID.
    RETURNS: True if config saved successfully, False on failure.
    FMEA: FM-001 — PID tuning parameters affect center oscillation behavior.
    """
    ax = odrv.axis0
    node_id = CAN_NODE_IDS[axis_name]
    print(f"\n{'─'*60}")
    print(f"  PHASE 1: Configure [{axis_name.upper()}] (CAN node {node_id})")
    print(f"{'─'*60}")

    # ── Motor (datasheet values + audit corrections) ─────────────
    ax.config.motor.motor_type                = MotorType.PMSM_CURRENT_CONTROL
    ax.config.motor.pole_pairs                = POLE_PAIRS
    ax.config.motor.torque_constant           = TORQUE_CONSTANT
    ax.config.motor.phase_resistance          = PHASE_RESISTANCE
    ax.config.motor.current_soft_max          = CURRENT_SOFT_MAX
    ax.config.motor.current_hard_max          = CURRENT_HARD_MAX

    # Motor model — feedforward is disabled on both reference configs.
    # Flux linkage is set for potential future use but not active.
    ax.config.motor.bEMF_FF_enable            = BEMF_FF_ENABLE
    ax.config.motor.dI_dt_FF_enable           = DI_DT_FF_ENABLE
    ax.config.motor.ff_pm_flux_linkage        = FLUX_LINKAGE
    ax.config.motor.ff_pm_flux_linkage_valid  = FLUX_LINKAGE_VALID
    ax.config.motor.current_slew_rate_limit   = CURRENT_SLEW_RATE_LIMIT
    ax.config.motor.fw_enable                 = FIELD_WEAKENING_ENABLE
    ax.config.motor.power_torque_report_filter_bandwidth = POWER_TORQUE_REPORT_FILTER_BW

    # ── Calibration (tuned for low-R GIM 8108-8) ────────────────
    ax.config.motor.calibration_current          = CALIBRATION_CURRENT
    ax.config.motor.resistance_calib_max_voltage = RESISTANCE_CALIB_MAX_VOLTAGE
    ax.config.calibration_lockin.current         = LOCKIN_CURRENT
    ax.config.calibration_lockin.ramp_time       = LOCKIN_RAMP_TIME
    ax.config.calibration_lockin.ramp_distance   = LOCKIN_RAMP_DISTANCE
    ax.config.calibration_lockin.vel             = LOCKIN_VEL
    ax.config.calibration_lockin.accel           = LOCKIN_ACCEL

    # ── Encoder (confirmed on 0.6.11 S1) ────────────────────────
    ax.config.load_encoder                    = ONBOARD_ENC
    ax.config.commutation_encoder             = ONBOARD_ENC
    ax.config.encoder_bandwidth               = ENCODER_BW
    ax.config.commutation_encoder_bandwidth   = COMMUTATION_ENC_BW

    # ── Gearbox — 8:1 planetary reducer ─────────────────────────
    # AUDIT #8: pos_vel_mapper.scale = 0.125 on GIM vs 1.0 on RMDX8.
    # This is correct for the GIM's 8:1 gearbox — it converts motor-side
    # units to output-shaft units. The RMDX8 uses 1.0 because its
    # ODrive config already accounts for the 9:1 ratio elsewhere.
    ax.pos_vel_mapper.config.scale            = POS_VEL_MAPPER_SCALE

    # ── Controller (AUDIT: primary source of broken trim) ────────
    # These gains were the largest behavioral difference between the
    # working RMDX8 and broken GIM configs. See MOTOR_COMPARISON.md
    # action items #1, #2, #3, #9 for full rationale.
    ax.controller.config.control_mode                 = ControlMode.TORQUE_CONTROL
    ax.controller.config.input_mode                   = InputMode.PASSTHROUGH
    ax.controller.config.vel_limit                    = VEL_LIMIT
    ax.controller.config.input_filter_bandwidth       = INPUT_FILTER_BW
    ax.controller.config.pos_gain                     = POS_GAIN
    ax.controller.config.vel_gain                     = VEL_GAIN
    ax.controller.config.vel_integrator_gain          = VEL_INTEGRATOR_GAIN

    # AUDIT #3: Disable the velocity limit. The GIM was capped at 1 turn/s
    # motor-side (~45°/s output), clipping any force command requiring
    # faster motion. RMDX8 has this disabled entirely.
    ax.controller.config.enable_torque_mode_vel_limit = False

    # AUDIT: torque soft limits — RMDX8 has ±31.25 Nm, GIM had none.
    # Setting ±7.0 Nm based on datasheet nominal torque as a safety bound.
    safe_set(ax.controller.config, 'torque_soft_min', TORQUE_SOFT_MIN,
             "controller.config.torque_soft_min")
    safe_set(ax.controller.config, 'torque_soft_max', TORQUE_SOFT_MAX,
             "controller.config.torque_soft_max")

    # ── Current loop and oscillation protection ──────────────────
    # AUDIT #4: current_control_bandwidth was 150 Hz vs RMDX8's 1000 Hz.
    # At 150 Hz the motor can't track rapid torque commands — forces
    # feel sluggish and lag behind stick movement.
    safe_set(ax.config.motor, 'current_control_bandwidth', CURRENT_CONTROL_BW,
             "motor.current_control_bandwidth")

    # AUDIT #11: torque_ramp_rate is bypassed in PASSTHROUGH input mode.
    # Setting to RMDX8 value as safety net.
    safe_set(ax.controller.config, 'torque_ramp_rate', TORQUE_RAMP_RATE,
             "controller.config.torque_ramp_rate")

    # Watchdog: set timeout + enable as a pair. Setting timeout alone
    # can auto-enable the watchdog and fault the drive during save.
    if safe_set(ax.controller.config, 'enable_watchdog', True,
                "controller.config.enable_watchdog"):
        safe_set(ax.config, 'watchdog_timeout', 0.05,
                 "config.watchdog_timeout")
    else:
        print(f"  ℹ Watchdog not available — skipping timeout too")

    # ── OpenFFBoard integration flags ────────────────────────────
    # These tell the ODrive to trust the external position reference
    # from OpenFFBoard rather than requiring its own index search.
    ax.pos_vel_mapper.config.offset_valid          = True
    ax.pos_vel_mapper.config.approx_init_pos_valid = True
    ax.controller.config.absolute_setpoints        = True

    # ── CAN bus ──────────────────────────────────────────────────
    ax.config.can.node_id     = node_id
    odrv.can.config.baud_rate = CAN_BAUD

    # ── Power protection ─────────────────────────────────────────
    # AUDIT #6: Brake resistor was DISABLED and regen current capped
    # at -2A on the GIM. Regenerative energy from motor deceleration
    # had nowhere to go, risking overvoltage faults. Critical on 48V.
    odrv.config.brake_resistor0.enable            = BRAKE_RESISTOR_ENABLE
    odrv.config.brake_resistor0.resistance        = BRAKE_RESISTANCE
    odrv.config.dc_bus_undervoltage_trip_level    = DC_BUS_UNDERVOLTAGE
    odrv.config.dc_bus_overvoltage_trip_level     = DC_BUS_OVERVOLTAGE

    # AUDIT #6: Allow sufficient regenerative current absorption.
    # GIM was at -2A, RMDX8 at -100A. Setting -10A as conservative start.
    safe_set(odrv.config, 'dc_max_negative_current', DC_MAX_NEGATIVE_CURRENT,
             "dc_max_negative_current")

    # ── Disable startup actions before calibration ───────────────
    # Calibration hasn't run yet, so we must prevent the ODrive from
    # attempting closed-loop control on the next reboot (it would fault
    # immediately without calibration data).
    ax.config.startup_motor_calibration          = False
    ax.config.startup_encoder_offset_calibration = False
    ax.config.startup_closed_loop_control        = False

    print(f"  ✔ Configuration written")

    # ── Verify critical values in RAM before saving ──────────────
    # The ODrive sometimes silently drops writes if the attribute path
    # is wrong or the value is out of range. Catching this before save
    # prevents flashing a partially-configured board.
    print(f"  Verifying config in RAM before save...")
    ram_errors = []
    if ax.config.motor.pole_pairs != POLE_PAIRS:
        ram_errors.append(f"pole_pairs={ax.config.motor.pole_pairs} (expected {POLE_PAIRS})")
    if abs(ax.config.motor.torque_constant - TORQUE_CONSTANT) > 0.01:
        ram_errors.append(f"torque_constant={ax.config.motor.torque_constant}")
    if int(ax.controller.config.control_mode) != int(ControlMode.TORQUE_CONTROL):
        ram_errors.append(f"control_mode={ax.controller.config.control_mode}")
    if int(ax.config.load_encoder) != int(ONBOARD_ENC):
        ram_errors.append(f"load_encoder={ax.config.load_encoder}")
    if abs(ax.pos_vel_mapper.config.scale - POS_VEL_MAPPER_SCALE) > 0.001:
        ram_errors.append(f"scale={ax.pos_vel_mapper.config.scale}")
    if ax.config.can.node_id != node_id:
        ram_errors.append(f"CAN node_id={ax.config.can.node_id}")
    if not odrv.config.brake_resistor0.enable:
        ram_errors.append("brake_resistor not enabled")

    # AUDIT: also verify the critical gain values that caused the
    # broken trim behavior.
    if abs(ax.controller.config.vel_gain - VEL_GAIN) > 0.01:
        ram_errors.append(f"vel_gain={ax.controller.config.vel_gain} (expected {VEL_GAIN})")
    if abs(ax.controller.config.vel_integrator_gain - VEL_INTEGRATOR_GAIN) > 0.01:
        ram_errors.append(f"vel_integrator_gain={ax.controller.config.vel_integrator_gain}")

    if ram_errors:
        print(f"  ✘ RAM verification FAILED — config did not apply:")
        for err in ram_errors:
            print(f"    ✘ {err}")
        print(f"  Aborting. Do not save corrupt config.")
        return False
    print(f"  ✔ RAM verification passed ({9 - len(ram_errors)}/9 critical values)")

    # ── Save to flash ────────────────────────────────────────────
    # The ODrive S1 reboots during save, dropping the USB connection.
    # This is normal behavior — Phase 3 will verify persistence.
    print(f"  Saving to flash (ODrive may reboot automatically)...")
    try:
        odrv.save_configuration()
        print(f"  ✔ Saved to flash.")
        time.sleep(1)
        try:
            odrv.reboot()
        except Exception:
            pass
    except Exception as e:
        print(f"  ℹ Device disconnected during save (common on S1).")
        print(f"    Phase 3 will verify if values persisted to flash.")
    print(f"  Waiting for reboot (5s)...")
    time.sleep(5)
    return True


# ═══════════════════════════════════════════════════════════════════
#  ANTI-COGGING CALIBRATION
# ═══════════════════════════════════════════════════════════════════

def _run_anticogging_sequence(odrv, ax):
    """
    WHAT: Run harmonic compensation + anticogging calibration sweep.
    WHY: The GIM 8108-8's planetary gearbox introduces cogging torque
         that creates force ripple during FFB operation. Anti-cogging
         calibration maps this ripple and applies compensation.
         Non-fatal — failures skip anticogging without aborting setup.
    ARGS:
        odrv: Connected ODrive instance.
        ax: ODrive axis object.
    RETURNS: None. Enables anticogging on success, prints warning on failure.
    FMEA: FM-001 — Cogging compensation affects force profile quality.
    """
    print(f"\n  ── Anti-cogging calibration ──")
    print(f"  Sequence: closed loop → harmonic comp → anticogging sweep")
    print(f"  Total time: ~8 minutes. Motor must NOT stop during sweep.")
    print(f"  Ctrl+C to abort at any point.\n")

    # Step 1: Enter closed loop — required before any motion commands
    print(f"  Step 1: Entering closed loop control...")
    ax.requested_state = AxisState.CLOSED_LOOP_CONTROL
    time.sleep(1)
    if ax.current_state != AxisState.CLOSED_LOOP_CONTROL:
        print(f"  ✘ FAILED to enter closed loop.")
        print(f"    active_errors: {hex(ax.active_errors)}")
        print(f"    disarm_reason: {ax.disarm_reason}")
        print(f"    procedure_result: {ax.procedure_result}")
        try:
            from odrive.utils import dump_errors
            dump_errors(odrv)
        except Exception:
            pass
        print(f"  Skipping anti-cogging.")
        return
    print(f"  ✔ Closed loop active (state: {ax.current_state})")

    # Step 2: Harmonic compensation corrects magnet eccentricity,
    # which is a precondition for accurate anti-cogging measurement.
    print(f"\n  Step 2: Running harmonic compensation...")
    print(f"    (Corrects magnet eccentricity — takes ~10 seconds)")
    try:
        ax.requested_state = AxisState.HARMONIC_CALIBRATION
    except AttributeError:
        print(f"  ✘ AxisState.HARMONIC_CALIBRATION not available on this firmware.")
        print(f"  Skipping anti-cogging.")
        ax.requested_state = AxisState.IDLE
        return

    time.sleep(0.5)
    if ax.current_state == AxisState.IDLE:
        print(f"  ✘ Harmonic calibration rejected.")
        print(f"    active_errors: {hex(ax.active_errors)}")
        print(f"    procedure_result: {ax.procedure_result}")
        print(f"  Skipping anti-cogging.")
        return

    if not wait_for_idle(ax, timeout=30):
        print(f"  ✘ Harmonic calibration timed out.")
        print(f"  Skipping anti-cogging.")
        ax.requested_state = AxisState.IDLE
        return

    if not check_errors(odrv, "Harmonic calibration"):
        print(f"  ✘ Harmonic calibration failed.")
        print(f"  Skipping anti-cogging.")
        return

    # Verify harmonic compensation produced correction coefficients.
    try:
        cosx = ax.config.harmonic_compensation.cosx_coef
        sinx = ax.config.harmonic_compensation.sinx_coef
        print(f"  ✔ Harmonic compensation complete")
        print(f"    cosx_coef={cosx:.6f}, sinx_coef={sinx:.6f}")
    except AttributeError:
        print(f"  ⚠ Could not read harmonic coefficients (continuing anyway)")

    # Step 3: Set temporary high-stiffness velocity gains for the
    # anticogging sweep. The sweep requires the motor to track a slow
    # velocity profile precisely — the FFB gains (high vel_gain but
    # optimized for force feel) may not be ideal for this.
    print(f"\n  Step 3: Setting calibration velocity gains...")
    original_vel_gain = ax.controller.config.vel_gain
    original_vel_int_gain = ax.controller.config.vel_integrator_gain
    ax.controller.config.vel_gain = 0.5
    ax.controller.config.vel_integrator_gain = 1.0
    print(f"    Calibration gains: vel_gain=0.5, integrator=1.0")
    print(f"    (FFB gains: vel_gain={original_vel_gain},"
          f" integrator={original_vel_int_gain})")

    # Step 4: Re-enter closed loop with the new gains
    print(f"\n  Step 4: Re-entering closed loop for anticogging...")
    ax.requested_state = AxisState.CLOSED_LOOP_CONTROL
    time.sleep(1)
    if ax.current_state != AxisState.CLOSED_LOOP_CONTROL:
        print(f"  ✘ FAILED to re-enter closed loop.")
        print(f"    active_errors: {hex(ax.active_errors)}")
        print(f"    procedure_result: {ax.procedure_result}")
        print(f"  Skipping anti-cogging.")
        _restore_gains(ax, original_vel_gain, original_vel_int_gain)
        return

    # Step 5: Set anticogging max torque before starting the sweep.
    # AUDIT: RMDX8 uses 3.0 Nm vs GIM's default 1.0 Nm.
    try:
        ax.config.anticogging.max_torque = ANTICOGGING_MAX_TORQUE
        print(f"  ✔ anticogging.max_torque set to {ANTICOGGING_MAX_TORQUE}")
    except AttributeError:
        print(f"  ⚠ anticogging.max_torque not available — using default")

    # Step 6: Run the anticogging sweep
    print(f"\n  Step 5: Starting anticogging sweep...")
    print(f"    Motor will spin fast→slow in each direction.")
    print(f"    Expected duration: ~6 minutes.\n")
    ax.requested_state = AxisState.ANTICOGGING_CALIBRATION
    time.sleep(0.5)

    if ax.current_state == AxisState.IDLE:
        pr = ax.procedure_result
        print(f"  ✘ FAILED to start anticogging.")
        print(f"    State fell back to IDLE immediately.")
        print(f"    active_errors: {hex(ax.active_errors)}")
        print(f"    procedure_result: {pr}")
        if pr == 14:  # POLE_PAIR_CPR_MISMATCH
            print(f"    POLE_PAIR_CPR_MISMATCH — harmonic comp may not have"
                  f" fully corrected magnet wobble.")
            try:
                scale = ax.observed_encoder_scale_factor
                print(f"    observed_encoder_scale_factor: {scale}")
            except AttributeError:
                pass
        print(f"  Skipping anti-cogging.")
        _restore_gains(ax, original_vel_gain, original_vel_int_gain)
        return

    print(f"  ✔ Anticogging running (state: {ax.current_state})")

    # Monitor the sweep — detect stalls and timeout conditions
    start_time = time.time()
    last_pos = get_position(ax)
    stall_count = 0
    STALL_THRESHOLD = 8

    while ax.current_state != AxisState.IDLE:
        elapsed = time.time() - start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        current_pos = get_position(ax)
        if abs(current_pos - last_pos) < 0.0005:
            stall_count += 1
        else:
            stall_count = 0
        last_pos = current_pos

        status = "MOVING"
        if stall_count >= 3:
            status = f"SLOW ({stall_count}s)"
        if stall_count >= STALL_THRESHOLD:
            status = "STALLED"

        print(f"  [{mins}m {secs:02d}s] pos={current_pos:.4f}"
              f" | {status}         ", end="\r")

        if stall_count >= STALL_THRESHOLD:
            print(f"\n  ✘ Motor STALLED for {STALL_THRESHOLD}s.")
            print(f"    Position stuck at {current_pos:.4f}")
            print(f"    vel_gain may need to be higher.")
            print(f"    Aborting anti-cogging.")
            ax.requested_state = AxisState.IDLE
            time.sleep(1)
            break

        if elapsed > 600:
            print(f"\n  ✘ Exceeded 10 minutes. Aborting.")
            ax.requested_state = AxisState.IDLE
            time.sleep(1)
            break

        time.sleep(1)

    print()

    # Check results and enable anticogging if the map has data
    errs = ax.active_errors
    pr = ax.procedure_result

    if errs != 0:
        print(f"  ✘ Anticogging FAILED.")
        print(f"    active_errors: {hex(errs)}")
        print(f"    procedure_result: {pr}")
        try:
            from odrive.utils import dump_errors
            dump_errors(odrv)
        except Exception:
            pass
        print(f"  Continuing without anti-cogging.")
    elif stall_count >= STALL_THRESHOLD:
        print(f"  ✘ Anticogging aborted (motor stall).")
        print(f"  Continuing without anti-cogging.")
    else:
        # Spot-check four map entries to confirm the sweep produced data
        m0 = ax.config.anticogging.get_map(0)
        m100 = ax.config.anticogging.get_map(100)
        m200 = ax.config.anticogging.get_map(200)
        m300 = ax.config.anticogging.get_map(300)
        has_data = any(abs(v) > 0.0001 for v in [m0, m100, m200, m300])

        if has_data:
            ax.config.anticogging.enabled = True
            print(f"  ✔ Anti-cogging complete and enabled")
            print(f"    Map samples: [0]={m0:.4f}, [100]={m100:.4f},"
                  f" [200]={m200:.4f}, [300]={m300:.4f}")
        else:
            print(f"  ✘ Anticogging map is empty (all zeros).")
            print(f"    Calibration ran but produced no data.")
            print(f"  Continuing without anti-cogging.")

    # Always restore FFB gains and return to IDLE regardless of outcome
    _restore_gains(ax, original_vel_gain, original_vel_int_gain)
    ax.requested_state = AxisState.IDLE
    time.sleep(0.5)


def _restore_gains(ax, vel_gain, vel_int_gain):
    """
    WHAT: Restore the FFB velocity gains after anticogging calibration.
    WHY: Anticogging temporarily sets high-stiffness gains for the sweep.
         These must be restored to the FFB-tuned values before the motor
         is used for force feedback.
    ARGS:
        ax: ODrive axis object.
        vel_gain: Original vel_gain to restore.
        vel_int_gain: Original vel_integrator_gain to restore.
    RETURNS: None.
    FMEA: FM-001 — Incorrect gains after cal would affect FFB behavior.
    """
    ax.controller.config.vel_gain = vel_gain
    ax.controller.config.vel_integrator_gain = vel_int_gain
    print(f"\n  ✔ Velocity gains restored:"
          f" vel_gain={vel_gain}, integrator={vel_int_gain}")


# ═══════════════════════════════════════════════════════════════════
#  PHASE 2: CALIBRATE + SET STARTUP + SAVE
# ═══════════════════════════════════════════════════════════════════

def phase2_calibrate(odrv, axis_name, run_anticogging=False):
    """
    WHAT: Run full motor+encoder calibration, optionally run anti-cogging,
          then set startup behavior and save to flash.
    WHY: The ODrive must measure phase resistance, phase inductance, and
         encoder offset before it can enter closed-loop control. These
         values are hardware-specific and must be measured on each board.
    ARGS:
        odrv: Connected ODrive instance (post-Phase 1 reboot).
        axis_name: "pitch" or "roll".
        run_anticogging: If True, run the anti-cogging sweep after cal.
    RETURNS: True if calibration succeeded and was saved, False on failure.
    FMEA: FM-002 — Calibration must complete successfully before the board
          can be trusted for force feedback.
    """
    ax = odrv.axis0
    print(f"\n{'─'*60}")
    print(f"  PHASE 2: Calibrate [{axis_name.upper()}]")
    if run_anticogging:
        print(f"  (includes anti-cogging — will take ~8 minutes total)")
    print(f"{'─'*60}")
    print(f"  Motor must be FREE TO SPIN, no biased load.")
    print(f"  Press Enter to start...", end="")
    input()

    # FULL_CALIBRATION_SEQUENCE runs motor calibration (resistance +
    # inductance measurement) followed by encoder offset calibration.
    # The motor will beep, then spin slowly in one direction.
    print(f"  Running FULL_CALIBRATION_SEQUENCE...")
    print(f"  (Beep → slow spin → done)")
    ax.requested_state = AxisState.FULL_CALIBRATION_SEQUENCE
    time.sleep(0.5)

    # Verify calibration actually started — if it was rejected, the
    # axis immediately returns to IDLE with an error code.
    if ax.current_state == AxisState.IDLE:
        errs = ax.active_errors
        print(f"  ✘ FULL_CALIBRATION_SEQUENCE was rejected.")
        print(f"    State remained IDLE.")
        print(f"    active_errors: {hex(errs)}")
        print(f"    procedure_result: {ax.procedure_result}")
        try:
            from odrive.utils import dump_errors
            dump_errors(odrv)
        except Exception:
            pass
        return False
    print(f"  ✔ Calibration started (state: {ax.current_state})")

    if not wait_for_idle(ax, timeout=60):
        return False
    if not check_errors(odrv, "Full calibration"):
        print(f"\n  Tip: if PHASE_RESISTANCE_OUT_OF_RANGE, raise")
        print(f"  RESISTANCE_CALIB_MAX_VOLTAGE by 0.5V and retry.")
        return False

    # Verify measured resistance is within expected range.
    # A large deviation suggests wiring issues or wrong motor.
    r = ax.config.motor.phase_resistance
    r_ok = abs(r - EXPECTED_PHASE_R_LTN) <= PHASE_R_TOLERANCE
    print(f"  {'✔' if r_ok else '⚠'} Phase resistance: {r:.4f} Ω"
          f" (expected ~{EXPECTED_PHASE_R_LTN} ±{PHASE_R_TOLERANCE})")
    print(f"  ℹ Phase inductance: {ax.config.motor.phase_inductance:.6e} H")

    if not r_ok:
        if input("  Continue anyway? (y/n): ").strip().lower() != 'y':
            return False

    # Encoder stability check — ensure position readings are not noisy.
    # Excessive drift (>0.02 turns) suggests a loose encoder or EMI.
    print(f"  Checking encoder stability (2s)...")
    positions = []
    for _ in range(20):
        positions.append(get_position(ax))
        time.sleep(0.1)
    drift = max(positions) - min(positions)
    print(f"  {'✔' if drift < 0.02 else '⚠'} Position drift: {drift:.4f} turns")

    # Initialize position estimate from raw encoder. This must happen
    # before anticogging because anticogging needs a stable position frame.
    try:
        ax.pos_estimate = odrv.onboard_encoder0.raw
        print(f"  ✔ pos_estimate initialized from raw encoder")
    except Exception as e:
        print(f"  ⚠ Could not init pos_estimate: {e}")

    # ── Anti-cogging calibration (optional, ~8 min) ──────────────
    if run_anticogging:
        _run_anticogging_sequence(odrv, ax)

    # ── Commit calibration to flash ──────────────────────────────
    # Mark the calibration data as valid so the ODrive trusts it on
    # subsequent boots without re-running calibration.
    print(f"\n  Validating calibration parameters for flash...")
    ax.config.motor.phase_resistance_valid = True
    ax.config.motor.phase_inductance_valid = True
    ax.commutation_mapper.config.offset_valid = True

    # Set startup behavior: skip calibration, go straight to closed loop.
    # This is the critical setting — if this doesn't save to flash,
    # the drive won't auto-enter closed loop on power-up.
    print(f"  Setting startup behavior...")
    ax.config.startup_motor_calibration          = False
    ax.config.startup_encoder_offset_calibration = False
    ax.config.startup_closed_loop_control        = True

    # Readback verify in RAM before saving — catches silent write failures
    v1 = ax.config.startup_motor_calibration
    v2 = ax.config.startup_encoder_offset_calibration
    v3 = ax.config.startup_closed_loop_control
    startup_ok = (v1 == False and v2 == False and v3 == True)
    if startup_ok:
        print(f"  ✔ Startup config verified in RAM:")
        print(f"    motor_cal={v1}, encoder_cal={v2}, closed_loop={v3}")
    else:
        print(f"  ✘ Startup config readback MISMATCH:")
        print(f"    motor_cal={v1} (expected False)")
        print(f"    encoder_cal={v2} (expected False)")
        print(f"    closed_loop={v3} (expected True)")
        print(f"  ⚠ Will attempt save anyway — Phase 3 will re-verify.")

    print(f"  Saving to flash...")
    try:
        odrv.save_configuration()
        print(f"  ✔ Save completed")
    except Exception:
        print(f"  ℹ Device disconnected during save (common on S1).")
        print(f"    Phase 3 will verify if values persisted to flash.")
    return True


# ═══════════════════════════════════════════════════════════════════
#  PHASE 3: VERIFY FLASH (reconnect and read back everything)
# ═══════════════════════════════════════════════════════════════════

def phase3_verify_flash(odrv, axis_name):
    """
    WHAT: Reconnect to the ODrive after save/reboot and verify that all
          critical configuration values persisted to flash.
    WHY: The S1 frequently drops USB during save_configuration, making it
         impossible to confirm persistence at save time. This phase reads
         back every critical value from flash. If startup_closed_loop_control
         didn't save, the drive won't auto-enter closed loop — the most
         common post-setup failure mode.
    ARGS:
        odrv: Freshly reconnected ODrive instance (post-Phase 2 reboot).
        axis_name: "pitch" or "roll".
    RETURNS: True if all values verified, False with manual fix instructions.
    FMEA: FM-002, FM-006 — Flash verification catches the most common
          failure (dropped save during USB disconnect).
    """
    ax = odrv.axis0
    node_id = CAN_NODE_IDS[axis_name]
    print(f"\n{'─'*60}")
    print(f"  PHASE 3: Verify flash [{axis_name.upper()}]")
    print(f"{'─'*60}")
    print(f"  Reading back saved config from flash...")

    checks = []

    def chk(name, actual, expected, tol=None):
        """Compare a saved value against expected, with optional tolerance."""
        if tol is not None:
            ok = abs(actual - expected) <= tol
        else:
            ok = actual == expected
        icon = "✔" if ok else "✘"
        print(f"  {icon} {name}: {actual} (expected {expected})")
        checks.append((name, ok))
        return ok

    # Motor — core identity values
    chk("motor_type", int(ax.config.motor.motor_type),
        int(MotorType.PMSM_CURRENT_CONTROL))
    chk("pole_pairs", ax.config.motor.pole_pairs, POLE_PAIRS)
    chk("torque_constant", ax.config.motor.torque_constant,
        TORQUE_CONSTANT, tol=0.01)
    chk("current_soft_max", ax.config.motor.current_soft_max,
        CURRENT_SOFT_MAX, tol=0.1)
    chk("current_hard_max", ax.config.motor.current_hard_max,
        CURRENT_HARD_MAX, tol=0.1)

    # Encoder
    chk("load_encoder", int(ax.config.load_encoder), int(ONBOARD_ENC))
    chk("commutation_encoder", int(ax.config.commutation_encoder),
        int(ONBOARD_ENC))

    # Controller — AUDIT-critical gains
    chk("control_mode", int(ax.controller.config.control_mode),
        int(ControlMode.TORQUE_CONTROL))
    chk("vel_gain", ax.controller.config.vel_gain, VEL_GAIN, tol=0.01)
    chk("vel_integrator_gain", ax.controller.config.vel_integrator_gain,
        VEL_INTEGRATOR_GAIN, tol=0.01)
    chk("pos_gain", ax.controller.config.pos_gain, POS_GAIN, tol=0.1)
    chk("vel_limit", ax.controller.config.vel_limit, VEL_LIMIT, tol=1.0)

    # Gearbox
    chk("pos_vel_mapper scale", ax.pos_vel_mapper.config.scale,
        POS_VEL_MAPPER_SCALE, tol=0.001)

    # CAN
    chk("CAN node_id", ax.config.can.node_id, node_id)
    chk("CAN baud_rate", odrv.can.config.baud_rate, CAN_BAUD)

    # Power protection
    chk("brake_resistor", odrv.config.brake_resistor0.enable, True)
    chk("dc_bus_undervoltage", odrv.config.dc_bus_undervoltage_trip_level,
        DC_BUS_UNDERVOLTAGE, tol=1)
    chk("dc_bus_overvoltage", odrv.config.dc_bus_overvoltage_trip_level,
        DC_BUS_OVERVOLTAGE, tol=1)

    # Startup — CRITICAL: if this didn't save, the drive won't auto-enter
    # closed loop on power-up. This is the most common S1 failure mode.
    chk("startup_motor_calibration",
        ax.config.startup_motor_calibration, False)
    chk("startup_encoder_offset_calibration",
        ax.config.startup_encoder_offset_calibration, False)
    chk("startup_closed_loop_control",
        ax.config.startup_closed_loop_control, True)

    # Calibration data — should be nonzero after successful calibration
    r = ax.config.motor.phase_resistance
    r_ok = r is not None and r > 0.1
    icon = "✔" if r_ok else "✘"
    print(f"  {icon} phase_resistance: {r:.4f} (should be >0.1)")
    checks.append(("phase_resistance", r_ok))

    l = ax.config.motor.phase_inductance
    l_ok = l is not None and l > 0
    icon = "✔" if l_ok else "✘"
    print(f"  {icon} phase_inductance: {l:.6e} (should be >0)")
    checks.append(("phase_inductance", l_ok))

    # Error state — drive should be clean after setup
    errs = ax.active_errors
    errs_ok = errs == 0
    icon = "✔" if errs_ok else "✘"
    print(f"  {icon} active_errors: {hex(errs)}"
          f" {'(clean)' if errs_ok else '(ERRORS PRESENT)'}")
    if not errs_ok:
        try:
            from odrive.utils import dump_errors
            dump_errors(odrv)
        except Exception:
            pass
    checks.append(("active_errors", errs_ok))

    # Anti-cogging state (informational — not a failure if disabled)
    try:
        ac = ax.config.anticogging.enabled
        print(f"  ℹ anticogging.enabled: {ac}")
    except AttributeError:
        print(f"  ℹ anticogging: not available on this firmware")

    # ── Summary ──────────────────────────────────────────────────
    failed = [(name, ok) for name, ok in checks if not ok]
    print()
    if not failed:
        print(f"  ✔ All {len(checks)} values verified in flash")
        return True
    else:
        print(f"  ✘ {len(failed)} value(s) FAILED flash verification:")
        for name, _ in failed:
            print(f"    ✘ {name}")
        print(f"\n  The save likely dropped during reboot.")
        print(f"  Attempting manual re-save...")

        # Retry: set the failed startup values and save again.
        # This is the most common fix for S1 save failures.
        try:
            odrv.clear_errors()
            ax.config.startup_motor_calibration = False
            ax.config.startup_encoder_offset_calibration = False
            ax.config.startup_closed_loop_control = True
            try:
                odrv.save_configuration()
            except Exception:
                pass
            time.sleep(3)

            # Reconnect and re-check the single most critical value
            odrv2 = connect_odrive(timeout=15)
            if odrv2 is not None:
                val = odrv2.axis0.config.startup_closed_loop_control
                if val:
                    print(f"  ✔ Re-save successful — startup_closed_loop_control = True")
                    return True
                else:
                    print(f"  ✘ Re-save failed. Set manually in odrivetool:")
                    print(f"    odrv0.clear_errors()")
                    print(f"    odrv0.axis0.config.startup_closed_loop_control = True")
                    print(f"    odrv0.save_configuration()")
                    return False
        except Exception as e:
            print(f"  ✘ Re-save failed: {e}")
            print(f"  Set manually in odrivetool (see above)")
            return False


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

def setup_axis(axis_name, run_anticogging=False):
    """
    WHAT: Orchestrate the full three-phase setup sequence for one axis.
    WHY: Wraps the erase → configure → calibrate → verify pipeline into
         a single callable that handles reconnection between phases.
    ARGS:
        axis_name: "pitch" or "roll".
        run_anticogging: If True, include anti-cogging calibration.
    RETURNS: True if all three phases passed, False on any failure.
    FMEA: FM-002, FM-006 — Full sequence integrity.
    """
    global _active_odrv

    print(f"\n{'='*60}")
    print(f"  ODrive S1 Setup — {axis_name.upper()} (GIM 8108-8)")
    print(f"  Firmware 0.6.11 | PMSM_CURRENT_CONTROL")
    print(f"  Config: RMDX8 Pro V2 audit-corrected values")
    if run_anticogging:
        print(f"  Anti-cogging: ENABLED")
    print(f"{'='*60}")
    print(f"  Connect the {axis_name} ODrive via USB. PSU on at 48V.")
    print(f"  Press Enter...", end="")
    input()

    odrv = connect_odrive()
    if odrv is None:
        return False
    _active_odrv = odrv

    if not validate_vbus(odrv):
        _active_odrv = None
        return False

    backup_config(odrv, axis_name)

    # ── Erase to factory defaults ────────────────────────────────
    # Starting from a clean slate prevents stale config values from
    # interfering with the new audit-corrected configuration.
    print(f"\n  Erasing config to factory defaults...")
    try:
        odrv.erase_configuration()
        print(f"  ✔ Erase command accepted.")
    except Exception as e:
        # Device reboots on erase, dropping USB — this is expected
        print(f"  ℹ Device disconnected during erase (expected on S1).")
    print(f"  Waiting for reboot (5s)...")
    time.sleep(5)

    print(f"  Reconnecting after erase...")
    odrv = connect_odrive(timeout=20)
    if odrv is None:
        print(f"  ✘ Could not reconnect after erase.")
        print(f"    Check USB cable and power supply.")
        _active_odrv = None
        return False
    _active_odrv = odrv

    # Verify erase by checking pole_pairs — ODrive default is 7
    if odrv.axis0.config.motor.pole_pairs != 7:
        print(f"  ⚠ Erase may not have completed — pole_pairs not at"
              f" default. Continuing anyway.")
    else:
        print(f"  ✔ Erase confirmed (config at factory defaults)")

    if not phase1_configure(odrv, axis_name):
        _active_odrv = None
        print(f"\n  ✘ Phase 1 configuration failed. See errors above.")
        return False

    print(f"\n  Reconnecting after Phase 1 save...")
    odrv = connect_odrive(timeout=20)
    if odrv is None:
        print(f"  ✘ Could not reconnect after Phase 1.")
        print(f"    Check USB cable and power supply.")
        _active_odrv = None
        return False
    _active_odrv = odrv

    success = phase2_calibrate(odrv, axis_name, run_anticogging)

    if not success:
        _active_odrv = None
        print(f"\n  ✘ Calibration failed. Backup in: {BACKUP_DIR}")
        return False

    # ── Phase 3: Reconnect and verify flash ─────────────────────
    print(f"\n  Reconnecting for flash verification...")
    time.sleep(3)
    odrv = connect_odrive(timeout=20)
    if odrv is None:
        print(f"  ⚠ Could not reconnect for verification.")
        print(f"    Calibration likely saved — verify manually in odrivetool.")
        _active_odrv = None
        return True  # Calibration passed, just can't verify
    _active_odrv = odrv
    verified = phase3_verify_flash(odrv, axis_name)
    _active_odrv = None

    if not verified:
        print(f"\n  ✘ Flash verification failed. See above for manual fix.")
    return verified


def main():
    """
    WHAT: CLI entry point — parse arguments and run setup for one axis.
    WHY: Provides both interactive and command-line axis selection.
    RETURNS: None. Exits with code 0 on success, 1 on failure.
    FMEA: N/A
    """
    parser = argparse.ArgumentParser(
        description="ODrive S1 setup for GIM 8108-8 FFB joystick")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pitch", action="store_true")
    group.add_argument("--roll", action="store_true")
    parser.add_argument("--anticogging", action="store_true",
                        help="Run anti-cogging calibration (~6 extra minutes)")
    args = parser.parse_args()

    if args.pitch:
        axis_name = "pitch"
    elif args.roll:
        axis_name = "roll"
    else:
        print("Which axis?  [1] Pitch (CAN 0)  [2] Roll (CAN 1)")
        choice = input("> ").strip()
        axis_name = {"1": "pitch", "2": "roll"}.get(choice)
        if not axis_name:
            sys.exit(1)

    success = setup_axis(axis_name, run_anticogging=args.anticogging)

    print(f"\n{'='*60}")
    print(f"  {axis_name.upper()}: {'✔ PASS' if success else '✘ FAIL'}")
    if success:
        print(f"\n  NEXT STEPS:")
        print(f"  1. Reassemble the stick")
        print(f"  2. Run: python odrive_center.py --{axis_name}")
        print(f"  3. Connect OpenFFBoard and verify CAN comms")
    print(f"{'='*60}\n")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
