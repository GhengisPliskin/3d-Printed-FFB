#!/usr/bin/env python3
"""
MODULE: odrive_verify.py
PURPOSE: Post-setup validation for ODrive S1 controllers driving GIM 8108-8
         motors. Runs after odrive_setup.py to confirm that configuration,
         calibration data, oscillation protection, and power settings all
         persisted to flash correctly. Includes optional torque symmetry test.
FMEA: FM-001 (PID tuning validation), FM-002 (calibration data integrity),
      FM-006 (startup state verification)
PHASE: 1

USAGE:
    python odrive_verify.py             # Interactive axis selection
    python odrive_verify.py --pitch     # Verify pitch axis
    python odrive_verify.py --roll      # Verify roll axis
    python odrive_verify.py --skip-torque      # Skip torque symmetry test
    python odrive_verify.py --skip-deflection  # Skip encoder deflection sweep

REQUIREMENTS: pip install odrive  (Python 3.13 — 3.14 is NOT compatible)

AUDIT HISTORY:
    2026-04-01  Expected values updated to match MOTOR_COMPARISON.md audit
                corrections. All controller gains, bandwidths, and power
                protection thresholds now reflect the RMDX8 Pro V2 reference.
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
import math
import signal
import sys
import time
from contextlib import contextmanager

# Fallback for EncoderId — see odrive_setup.py for rationale.
try:
    from odrive.enums import EncoderId
    ONBOARD_ENC = EncoderId.ONBOARD_ENCODER0
except (ImportError, AttributeError):
    ONBOARD_ENC = 1


# ═══════════════════════════════════════════════════════════════════
#  EXPECTED VALUES
# ═══════════════════════════════════════════════════════════════════
# These MUST match the constants in odrive_setup.py. If you change a
# value in setup, update it here too. The audit corrections from
# MOTOR_COMPARISON.md are marked with "AUDIT:" comments.

EXPECTED = {
    # Motor core (datasheet)
    "pole_pairs": 21,
    "torque_constant": 1.45,
    "current_soft_max": 7.0,
    "current_hard_max": 25.0,
    "phase_r_ltn": 0.439,          # Datasheet phase-to-phase resistance
    "phase_r_tol": 0.10,           # Tolerance for measured vs datasheet

    # Gearbox — 8:1 planetary
    "scale": 1.0,                  # Motor turns — OpenFFB prescaler handles gearbox

    # Controller gains — AUDIT-corrected from RMDX8 Pro V2 reference
    "vel_gain": 3.0,               # AUDIT: was 0.02
    "vel_integrator_gain": 2.2,    # AUDIT: was 0.0
    "pos_gain": 38.0,              # AUDIT: was 15.0
    "vel_limit": 1000.0,           # AUDIT: was 1.0 (motor-side)

    # Bandwidths — confirmed through testing
    "current_ctrl_bw": 150,        # FIX: confirmed 150 eliminates chatter on GIM
    "encoder_bw": 1000,            # AUDIT: confirmed — lower causes lag oscillation

    # Torque soft limits — FIX: attribute path is axis0.config, not
    # axis0.controller.config. Confirmed via backup-config JSON diff.
    "torque_soft_min": -7.0,       # Datasheet nominal torque bound
    "torque_soft_max": 7.0,        # Datasheet nominal torque bound

    # Oscillation protection
    "watchdog_timeout": 0.05,
    "torque_ramp_rate": 50.0,      # FIX: confirmed — trim works, no chatter
}

CAN_NODE_IDS = {"pitch": 0, "roll": 1}

# Torque symmetry test parameters.
# 0.5 Nm is low enough to be safe on the GIM 8108-8 (datasheet nominal
# torque is 7.5 Nm) but high enough to produce measurable displacement.
TORQUE_TEST_NM = 0.5
TORQUE_HOLD_SEC = 2.0
POSITION_DRIFT_TOL = 0.02

# Encoder deflection test parameters.
# The user manually moves the stick through full travel while the script
# samples positions. We check for monotonicity, gap-free continuity,
# and reasonable total travel range.
DEFLECTION_SAMPLE_HZ = 50         # Sampling rate during sweep
DEFLECTION_TIMEOUT_SEC = 15.0     # Max time for user to complete sweep
DEFLECTION_MIN_TRAVEL = 0.05      # Minimum total travel (output-shaft turns)
DEFLECTION_MAX_GAP = 0.02         # Max allowed position jump between samples
DEFLECTION_REVERSAL_TOL = 0.005   # Ignore reversals smaller than this (noise)


# ═══════════════════════════════════════════════════════════════════
#  SAFETY — Emergency stop handler
# ═══════════════════════════════════════════════════════════════════
# Identical pattern to odrive_setup.py. Ctrl+C zeros torque immediately.
_active_odrv = None


def _emergency_disarm(signum=None, frame=None):
    """
    WHAT: Zero torque and force motor to IDLE on interrupt.
    WHY: The torque symmetry test applies real force to the motor.
         If the user presses Ctrl+C, we must stop immediately.
    ARGS:
        signum: Signal number or None.
        frame: Stack frame (unused).
    RETURNS: None. Exits with code 1 if called from signal.
    FMEA: FM-006 — Safety sequence integrity.
    """
    global _active_odrv
    if _active_odrv is not None:
        try:
            _active_odrv.axis0.controller.input_torque = 0
        except Exception:
            pass
        try:
            _active_odrv.axis0.requested_state = AxisState.IDLE
        except Exception:
            pass
        print("\n  ⛔ Emergency disarm.")
    if signum is not None:
        sys.exit(1)


signal.signal(signal.SIGINT, _emergency_disarm)
signal.signal(signal.SIGTERM, _emergency_disarm)
atexit.register(_emergency_disarm)


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def get_position(ax):
    """
    WHAT: Read current position from pos_vel_mapper (output-shaft turns).
    WHY: Used by torque symmetry test to measure displacement.
    ARGS: ax — ODrive axis object.
    RETURNS: Float — position in output shaft turns.
    FMEA: N/A
    """
    return ax.pos_vel_mapper.pos_rel


def result(name, passed, msg):
    """
    WHAT: Format and print a single test result, return as dict.
    WHY: Standardizes output format across all tests and enables
         aggregation for the final pass/fail/warn summary.
    ARGS:
        name: Test name string.
        passed: True (pass), False (fail), or None (warning).
        msg: Human-readable result detail.
    RETURNS: Dict with name, passed, and msg keys.
    FMEA: N/A
    """
    icon = "✔" if passed else ("⚠" if passed is None else "✘")
    print(f"  {icon} {name}: {msg}")
    return {"name": name, "passed": passed, "msg": msg}


@contextmanager
def safe_torque(ax):
    """
    WHAT: Context manager that guarantees torque is zeroed and motor
          returns to IDLE on exit, even if an exception occurs.
    WHY: The torque symmetry test must never leave the motor in an
         active torque state if an error or interrupt occurs mid-test.
    ARGS: ax — ODrive axis object.
    RETURNS: Yields the axis object for use in the with block.
    FMEA: FM-006 — Safety sequence integrity.
    """
    try:
        yield ax
    finally:
        try:
            ax.controller.input_torque = 0
        except Exception:
            pass
        try:
            ax.requested_state = AxisState.IDLE
        except Exception:
            pass
        time.sleep(0.3)


def timed_sleep(ax, duration, interval=0.1):
    """
    WHAT: Sleep for a duration while monitoring for ODrive faults.
    WHY: During the torque hold period, a fault (overcurrent, overvoltage)
         should immediately stop the test rather than continuing blindly.
    ARGS:
        ax: ODrive axis object.
        duration: Total sleep time in seconds.
        interval: Check interval in seconds.
    RETURNS: None. Raises RuntimeError if a fault occurs during sleep.
    FMEA: FM-006 — Fault detection during active motor test.
    """
    elapsed = 0
    while elapsed < duration:
        time.sleep(interval)
        elapsed += interval
        if ax.active_errors != 0:
            ax.controller.input_torque = 0
            raise RuntimeError(f"Fault: {hex(ax.active_errors)}")


# ═══════════════════════════════════════════════════════════════════
#  TESTS
# ═══════════════════════════════════════════════════════════════════

def test_vbus(odrv):
    """
    WHAT: Check that the bus voltage is in the expected range for 48V PSU.
    WHY: Low Vbus indicates PSU issues that will cause false test failures.
    ARGS: odrv — Connected ODrive instance.
    RETURNS: Test result dict.
    FMEA: FM-006 — Pre-condition for valid test results.
    """
    v = odrv.vbus_voltage
    if v >= 44:
        return result("Vbus", True, f"{v:.1f} V")
    if v >= 38:
        return result("Vbus", None, f"{v:.1f} V — below 48V nominal")
    return result("Vbus", False, f"{v:.1f} V — below minimum")


def test_config(ax, odrv, axis_name):
    """
    WHAT: Verify all critical configuration values match expected constants.
    WHY: Catches partial saves, config corruption, or setup script bugs.
         Every value checked here was identified as critical by the
         MOTOR_COMPARISON.md audit.
    ARGS:
        ax: ODrive axis object.
        odrv: Connected ODrive instance.
        axis_name: "pitch" or "roll" — determines expected CAN node ID.
    RETURNS: Test result dict.
    FMEA: FM-001 — PID parameter validation.
    """
    errors = []
    E = EXPECTED
    node = CAN_NODE_IDS[axis_name]

    # Motor identity
    if ax.config.motor.pole_pairs != E["pole_pairs"]:
        errors.append(f"pole_pairs={ax.config.motor.pole_pairs}")
    if abs(ax.config.motor.torque_constant - E["torque_constant"]) > 0.01:
        errors.append(f"torque_constant={ax.config.motor.torque_constant}")
    if ax.config.motor.motor_type != MotorType.PMSM_CURRENT_CONTROL:
        errors.append("motor_type wrong")
    if abs(ax.config.motor.current_soft_max - E["current_soft_max"]) > 0.1:
        errors.append(f"current_soft_max={ax.config.motor.current_soft_max}")
    if abs(ax.config.motor.current_hard_max - E["current_hard_max"]) > 0.1:
        errors.append(f"current_hard_max={ax.config.motor.current_hard_max}")

    # Controller — these are the AUDIT-critical values
    if ax.controller.config.control_mode != ControlMode.TORQUE_CONTROL:
        errors.append("not TORQUE_CONTROL")
    if abs(ax.controller.config.vel_gain - E["vel_gain"]) > 0.1:
        errors.append(f"vel_gain={ax.controller.config.vel_gain} (expected {E['vel_gain']})")
    if abs(ax.controller.config.vel_integrator_gain - E["vel_integrator_gain"]) > 0.1:
        errors.append(f"vel_integrator_gain={ax.controller.config.vel_integrator_gain}")
    if abs(ax.controller.config.pos_gain - E["pos_gain"]) > 1.0:
        errors.append(f"pos_gain={ax.controller.config.pos_gain} (expected {E['pos_gain']})")
    if abs(ax.controller.config.vel_limit - E["vel_limit"]) > 10.0:
        errors.append(f"vel_limit={ax.controller.config.vel_limit} (expected {E['vel_limit']})")

    # Encoder
    if ax.config.load_encoder != ONBOARD_ENC:
        errors.append(f"load_encoder={ax.config.load_encoder}")

    # Gearbox scaling
    if abs(ax.pos_vel_mapper.config.scale - E["scale"]) > 0.001:
        errors.append(f"scale={ax.pos_vel_mapper.config.scale}")

    # CAN
    if ax.config.can.node_id != node:
        errors.append(f"CAN node={ax.config.can.node_id} (expected {node})")

    # Brake resistor — AUDIT #6 critical
    if not odrv.config.brake_resistor0.enable:
        errors.append("brake_resistor OFF")

    # Torque soft limits — attribute lives at axis0.config, not
    # axis0.controller.config. If still at ±∞, the setup script
    # wrote to the wrong path or firmware doesn't support them.
    try:
        tsmin = ax.config.torque_soft_min
        tsmax = ax.config.torque_soft_max
        if math.isinf(tsmin) or math.isinf(tsmax):
            errors.append(f"torque_soft limits at default (±∞) — not set")
        else:
            if abs(tsmin - E["torque_soft_min"]) > 0.1:
                errors.append(f"torque_soft_min={tsmin} (expected {E['torque_soft_min']})")
            if abs(tsmax - E["torque_soft_max"]) > 0.1:
                errors.append(f"torque_soft_max={tsmax} (expected {E['torque_soft_max']})")
    except AttributeError:
        pass  # Firmware doesn't expose these — not an error

    # Startup behavior — most common failure mode
    if not ax.config.startup_closed_loop_control:
        errors.append("startup_closed_loop=False")
    if ax.config.startup_motor_calibration:
        errors.append("startup_motor_cal=True (should be False)")

    if errors:
        return result("Config", False, "; ".join(errors))
    return result("Config", True, "All values match")


def test_oscillation_protection(ax):
    """
    WHAT: Verify bandwidth and protection parameters are within safe ranges.
    WHY: The AUDIT raised current_control_bandwidth from 150→1000 Hz and
         encoder_bandwidth from 200→1000 Hz. This test confirms those
         changes persisted and flags if values are dangerously high.
    ARGS: ax — ODrive axis object.
    RETURNS: Test result dict.
    FMEA: FM-001 — Oscillation/stability protection.
    """
    issues = []
    info = []

    # Current control bandwidth — target: 150 Hz
    # 1000 causes whine, 500 reduces whine but chatter persists,
    # 150 eliminates chatter. Acts as natural low-pass on torque output.
    try:
        bw = ax.config.motor.current_control_bandwidth
        info.append(f"current_bw={bw}")
        if bw < 100:
            issues.append(f"current_ctrl_bw={bw} (should be ≥100, target 150)")
        elif bw > 1000:
            issues.append(f"current_ctrl_bw={bw} (causes whine/chatter on GIM, target 150)")
    except AttributeError:
        info.append("current_bw=N/A")

    # Encoder bandwidth — AUDIT target: 1000 Hz
    try:
        ebw = ax.config.encoder_bandwidth
        info.append(f"enc_bw={ebw}")
        if ebw < 500:
            issues.append(f"encoder_bw={ebw} (should be ≥500, target 1000)")
        elif ebw > 2000:
            issues.append(f"encoder_bw={ebw} (dangerously high)")
    except AttributeError:
        info.append("enc_bw=N/A")

    # Watchdog — optional but recommended
    try:
        wdt = ax.config.watchdog_timeout
        wde = ax.controller.config.enable_watchdog
        info.append(f"watchdog={'on' if wde else 'OFF'} @ {wdt}s")
        if not wde:
            issues.append("watchdog DISABLED")
        elif wdt > 0.1:
            issues.append(f"watchdog_timeout={wdt}s (should be ≤0.05s)")
    except AttributeError:
        info.append("watchdog=N/A")

    # Torque ramp rate — informational
    try:
        ramp = ax.controller.config.torque_ramp_rate
        info.append(f"ramp={ramp}")
    except AttributeError:
        pass

    if issues:
        return result("Oscillation protection", False, "; ".join(issues))
    return result("Oscillation protection", True, ", ".join(info))


def test_phase_resistance(ax):
    """
    WHAT: Verify calibrated phase resistance matches the GIM 8108-8 datasheet.
    WHY: A large deviation from 0.439 Ω indicates wiring issues, wrong motor,
         or a failed calibration run.
    ARGS: ax — ODrive axis object.
    RETURNS: Test result dict.
    FMEA: FM-002 — Calibration data integrity.
    """
    r = ax.config.motor.phase_resistance
    E = EXPECTED
    if r is None or r == 0:
        return result("Phase resistance", False, "Not calibrated")
    if abs(r - E["phase_r_ltn"]) <= E["phase_r_tol"]:
        return result("Phase resistance", True, f"{r:.4f} Ω")
    return result("Phase resistance", False,
                  f"{r:.4f} Ω — outside {E['phase_r_ltn']} ±{E['phase_r_tol']}")


def test_phase_inductance(ax):
    """
    WHAT: Verify calibrated phase inductance is within plausible range.
    WHY: Phase inductance should be positive and within the range typical
         for BLDC motors (~10 µH to 1 mH). Values outside this range
         indicate calibration failure or measurement noise.
    ARGS: ax — ODrive axis object.
    RETURNS: Test result dict.
    FMEA: FM-002 — Calibration data integrity.
    """
    l = ax.config.motor.phase_inductance
    if l is None or l <= 0:
        return result("Phase inductance", False, f"Invalid: {l}")
    if l < 1e-8 or l > 1e-3:
        return result("Phase inductance", None, f"{l:.6e} H — unusual")
    return result("Phase inductance", True, f"{l:.6e} H")


def test_encoder_stability(ax):
    """
    WHAT: Sample encoder position over 2 seconds and measure drift.
    WHY: Excessive position drift at idle indicates a loose encoder,
         EMI coupling, or bad encoder configuration. This compounds
         velocity estimation error and degrades force feedback quality.
    ARGS: ax — ODrive axis object.
    RETURNS: Test result dict.
    FMEA: FM-002 — Encoder reliability.
    """
    positions = []
    for _ in range(20):
        positions.append(get_position(ax))
        time.sleep(0.1)
    drift = max(positions) - min(positions)
    if drift < POSITION_DRIFT_TOL:
        return result("Encoder stability", True, f"Drift {drift:.4f} t / 2s")
    return result("Encoder stability", False, f"Drift {drift:.4f} t")


def test_encoder_deflection(ax):
    """
    WHAT: Verify the encoder tracks position continuously through full
          stick travel. The user manually sweeps the stick from one
          physical stop to the other while the script samples position.
    WHY: A bad encoder, loose magnet, or corrupted calibration can
         produce correct readings at idle but introduce gaps, dropouts,
         or reversals under movement. This test catches those failures
         before OpenFFBoard starts sending torque commands against a
         broken position signal.
    ARGS: ax — ODrive axis object (must be in closed-loop torque mode
          with zero input so the stick is free to move by hand).
    RETURNS: Test result dict. Failure recommends recalibration.
    FMEA: FM-002 — Encoder reliability under movement.
          C-006 — Position accuracy prerequisite for centering.
    """
    # ── Pre-check: motor must be in closed loop with zero torque ──
    # In TORQUE_CONTROL mode with input_torque=0, the motor offers
    # no resistance and the stick moves freely while the encoder
    # still tracks position.
    if ax.current_state != AxisState.CLOSED_LOOP_CONTROL:
        return result("Encoder deflection", False,
                      f"Not in closed loop (state={ax.current_state})")

    try:
        ax.controller.input_torque = 0
    except Exception:
        pass

    # ── Prompt user ──────────────────────────────────────────────
    print(f"\n  ── Encoder Deflection Sweep ──")
    print(f"  Slowly move the stick from one physical stop to the other.")
    print(f"  You have {DEFLECTION_TIMEOUT_SEC:.0f} seconds. Sampling starts")
    print(f"  when movement is detected.")
    print(f"  Press Enter to begin...", end="")
    input()

    # ── Wait for movement to start ───────────────────────────────
    # Sit at idle and watch for the position to change beyond noise.
    # This avoids recording a bunch of stationary samples at the start.
    baseline = get_position(ax)
    interval = 1.0 / DEFLECTION_SAMPLE_HZ
    started = False
    start_time = time.monotonic()
    positions = []
    timestamps = []

    print(f"  Waiting for movement...", end="", flush=True)

    while (time.monotonic() - start_time) < DEFLECTION_TIMEOUT_SEC:
        pos = get_position(ax)
        time.sleep(interval)

        if not started:
            # Detect movement start: position moved beyond noise floor
            if abs(pos - baseline) > DEFLECTION_REVERSAL_TOL * 3:
                started = True
                positions.append(baseline)
                timestamps.append(0.0)
                positions.append(pos)
                timestamps.append(time.monotonic() - start_time)
                print(f" recording.", flush=True)
            continue

        positions.append(pos)
        timestamps.append(time.monotonic() - start_time)

        # Detect movement stop: last 10 samples are all within noise
        if len(positions) >= 15:
            recent = positions[-10:]
            recent_spread = max(recent) - min(recent)
            if recent_spread < DEFLECTION_REVERSAL_TOL:
                print(f"  Movement stopped — sweep complete.")
                break
    else:
        if not started:
            return result("Encoder deflection", False,
                          "No movement detected — timed out")
        print(f"  Timeout reached — analyzing what was recorded.")

    # ── Analyze the sweep ────────────────────────────────────────
    n = len(positions)
    if n < 5:
        return result("Encoder deflection", False,
                      f"Only {n} samples — insufficient data")

    total_travel = abs(positions[-1] - positions[0])
    issues = []
    info = []

    # Check 1: minimum total travel
    if total_travel < DEFLECTION_MIN_TRAVEL:
        issues.append(f"travel={total_travel:.4f}t (min {DEFLECTION_MIN_TRAVEL})")

    # Check 2: gaps between consecutive samples
    # A gap indicates the encoder lost track or skipped counts.
    max_gap = 0.0
    gap_count = 0
    for i in range(1, n):
        gap = abs(positions[i] - positions[i-1])
        if gap > max_gap:
            max_gap = gap
        if gap > DEFLECTION_MAX_GAP:
            gap_count += 1

    if gap_count > 0:
        issues.append(f"{gap_count} gap(s) > {DEFLECTION_MAX_GAP}t "
                      f"(worst={max_gap:.4f}t)")

    # Check 3: monotonicity — no large reversals
    # Determine sweep direction from overall movement, then count
    # samples that reverse against that direction beyond noise.
    sweep_positive = positions[-1] > positions[0]
    reversal_count = 0
    worst_reversal = 0.0
    for i in range(1, n):
        delta = positions[i] - positions[i-1]
        if sweep_positive and delta < -DEFLECTION_REVERSAL_TOL:
            reversal_count += 1
            if abs(delta) > worst_reversal:
                worst_reversal = abs(delta)
        elif not sweep_positive and delta > DEFLECTION_REVERSAL_TOL:
            reversal_count += 1
            if abs(delta) > worst_reversal:
                worst_reversal = abs(delta)

    if reversal_count > 3:
        issues.append(f"{reversal_count} reversals "
                      f"(worst={worst_reversal:.4f}t)")

    info.append(f"{n} samples")
    info.append(f"travel={total_travel:.4f}t")
    info.append(f"max_gap={max_gap:.4f}t")
    info.append(f"reversals={reversal_count}")

    detail = ", ".join(info)

    if issues:
        return result("Encoder deflection", False,
                      f"RECALIBRATE — {'; '.join(issues)} [{detail}]")

    # Mild warning if any reversals at all (could be user hesitation)
    if reversal_count > 0:
        return result("Encoder deflection", None,
                      f"Minor reversals (user hesitation?) — {detail}")

    return result("Encoder deflection", True, detail)


def test_power(odrv):
    """
    WHAT: Verify power protection settings are configured for 48V operation.
    WHY: AUDIT #6 identified that the GIM had brake resistor disabled and
         regen current capped at -2A. These settings risk overvoltage faults
         during motor deceleration on a 48V bus.
    ARGS: odrv — Connected ODrive instance.
    RETURNS: Test result dict.
    FMEA: FM-006 — Power protection.
    """
    ov = odrv.config.dc_bus_overvoltage_trip_level
    uv = odrv.config.dc_bus_undervoltage_trip_level
    br = odrv.config.brake_resistor0.enable
    issues = []
    if ov > 55:
        issues.append(f"OV={ov}V (too high for 48V bus)")
    if uv < 35:
        issues.append(f"UV={uv}V (too low)")
    if not br:
        issues.append("brake resistor OFF — AUDIT #6 critical")

    # Check dc_max_negative_current if available
    try:
        neg_i = odrv.config.dc_max_negative_current
        if neg_i > -5.0:
            issues.append(f"dc_max_negative_current={neg_i}A (should be ≤-10A)")
    except AttributeError:
        pass

    if issues:
        return result("Power protection", None, "; ".join(issues))
    return result("Power protection", True, f"UV={uv}V OV={ov}V brake={br}")


def test_torque_symmetry(ax):
    """
    WHAT: Apply equal positive and negative torque and compare displacement.
    WHY: Asymmetric displacement indicates gravitational bias (expected on
         pitch axis), friction asymmetry, or incorrect motor direction.
         The MOTOR_COMPARISON.md audit identified gravitational bias on
         the pitch axis as a leading hypothesis for force errors.
    ARGS: ax — ODrive axis object.
    RETURNS: Test result dict.
    FMEA: FM-001 — Force profile symmetry validation.
    """
    with safe_torque(ax):
        # Enter closed loop — required for torque commands
        ax.requested_state = AxisState.CLOSED_LOOP_CONTROL
        time.sleep(0.5)
        if ax.current_state != AxisState.CLOSED_LOOP_CONTROL:
            return result("Torque symmetry", False,
                          f"Closed loop failed: {hex(ax.active_errors)}")

        # Positive torque: measure displacement from baseline
        baseline = get_position(ax)
        ax.controller.input_torque = TORQUE_TEST_NM
        try:
            timed_sleep(ax, TORQUE_HOLD_SEC)
        except RuntimeError as e:
            return result("Torque symmetry", False, str(e))
        disp_pos = abs(get_position(ax) - baseline)

        # Return to neutral before negative test
        ax.controller.input_torque = 0
        time.sleep(1.0)

        # Negative torque: measure displacement from new position
        mid = get_position(ax)
        ax.controller.input_torque = -TORQUE_TEST_NM
        try:
            timed_sleep(ax, TORQUE_HOLD_SEC)
        except RuntimeError as e:
            return result("Torque symmetry", False, str(e))
        disp_neg = abs(get_position(ax) - mid)

        # Calculate symmetry ratio — 1.0 = perfect symmetry
        if disp_neg == 0 and disp_pos == 0:
            return result("Torque symmetry", None, "No displacement")
        ratio = disp_pos / disp_neg if disp_neg != 0 else float('inf')
        d = f"+→{disp_pos:.4f}t, -→{disp_neg:.4f}t, ratio:{ratio:.2f}"

        if 0.8 <= ratio <= 1.2:
            return result("Torque symmetry", True, d)
        elif 0.6 <= ratio <= 1.4:
            return result("Torque symmetry", None, f"Mild asymmetry — {d}")
        else:
            return result("Torque symmetry", False, f"Severe — {d}")


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

def run_tests(axis_name, skip_torque=False, skip_deflection=False):
    """
    WHAT: Execute the full verification test suite for one axis.
    WHY: Validates that odrive_setup.py produced a correctly configured
         and calibrated ODrive. Reboots first to purge RAM and read
         exclusively from flash.
    ARGS:
        axis_name: "pitch" or "roll".
        skip_torque: If True, skip the torque symmetry test.
        skip_deflection: If True, skip the encoder deflection sweep test.
    RETURNS: True if no failures, False if any test failed.
    FMEA: FM-002, FM-006 — Post-setup validation.
    """
    global _active_odrv

    # ── Reboot to purge RAM and read from flash ──────────────────
    # This ensures we're testing what's actually saved, not what's
    # left over in RAM from the setup script.
    print(f"\n  Connecting to ODrive for reboot...")
    odrv = odrive.find_any(timeout=15)
    if odrv is None:
        print(f"  ✘ No ODrive found.")
        return False

    print(f"  Found ODrive (serial: {getattr(odrv, 'serial_number', '?')})")
    print(f"  Rebooting to purge RAM and read from flash...")
    try:
        odrv.reboot()
    except Exception:
        pass  # Connection drops on reboot — expected
    time.sleep(5)

    # ── Reconnect after reboot ───────────────────────────────────
    print(f"  Reconnecting after reboot...")
    odrv = odrive.find_any(timeout=20)
    if odrv is None:
        print(f"  ✘ Could not reconnect after reboot.")
        print(f"    Check USB cable and power supply.")
        return False
    _active_odrv = odrv
    ax = odrv.axis0

    print(f"\n{'='*60}")
    print(f"  Verify — {axis_name.upper()} axis (reading from flash)")
    print(f"  Serial: {getattr(odrv, 'serial_number', '?')}")
    print(f"  Config: RMDX8 Pro V2 audit-corrected values")
    print(f"{'='*60}\n")

    results = []

    # Wrap each test to prevent one failure from crashing the suite
    def run_test(name, func, *args):
        """Execute a single test with exception handling."""
        try:
            return func(*args)
        except AttributeError as e:
            return result(name, False, f"Attribute not found: {e}")
        except Exception as e:
            return result(name, False, f"Unexpected error: {e}")

    # ── Error state — should be clean after reboot ───────────────
    errs = ax.active_errors
    if errs == 0:
        results.append(result("Error state", True, "No errors"))
    else:
        results.append(result("Error state", False,
            f"active_errors={hex(errs)}, disarm_reason={ax.disarm_reason}"))
        try:
            from odrive.utils import dump_errors
            dump_errors(odrv)
        except Exception:
            pass

    # ── Startup state — did the drive auto-enter closed loop? ────
    # This is the single most important check. If startup_closed_loop
    # didn't save to flash, the drive stays in IDLE on power-up and
    # OpenFFBoard can't send torque commands.
    state = ax.current_state
    try:
        startup_cl = ax.config.startup_closed_loop_control
    except AttributeError:
        startup_cl = None

    if startup_cl is None:
        results.append(result("Startup state", False,
            "startup_closed_loop_control attribute not found"))
    elif startup_cl and state == AxisState.CLOSED_LOOP_CONTROL:
        results.append(result("Startup state", True,
            "Entered closed loop on boot"))
    elif startup_cl and state != AxisState.CLOSED_LOOP_CONTROL:
        results.append(result("Startup state", False,
            f"startup_closed_loop=True but state={state}. "
            f"disarm_reason={ax.disarm_reason}"))
    elif not startup_cl:
        results.append(result("Startup state", False,
            "startup_closed_loop_control=False — Phase 2 save likely failed"))

    # ── Run all tests ────────────────────────────────────────────
    results.append(run_test("Vbus", test_vbus, odrv))
    results.append(run_test("Config", test_config, ax, odrv, axis_name))
    results.append(run_test("Oscillation protection",
                            test_oscillation_protection, ax))
    results.append(run_test("Phase resistance", test_phase_resistance, ax))
    results.append(run_test("Phase inductance", test_phase_inductance, ax))
    results.append(run_test("Encoder stability", test_encoder_stability, ax))
    results.append(run_test("Power protection", test_power, odrv))

    # Anti-cogging status (informational — not a pass/fail test)
    try:
        ac = ax.config.anticogging.enabled
        print(f"  ℹ Anti-cogging: {'enabled' if ac else 'disabled'}")
    except AttributeError:
        print(f"  ℹ Anti-cogging: not available on this firmware")

    # ── Encoder deflection sweep — requires user interaction ─────
    # This test asks the user to physically move the stick through
    # full travel. If the encoder loses track, it recommends
    # recalibrating the motor/encoder.
    if not skip_deflection:
        print(f"\n  Deflection sweep: manually move stick through full travel.")
        print(f"  Enter to run, 's' to skip: ", end="")
        if input().strip().lower() != 's':
            results.append(run_test("Encoder deflection",
                                    test_encoder_deflection, ax))
    else:
        print(f"\n  Encoder deflection test skipped.")

    # ── Optional torque symmetry test ────────────────────────────
    if not skip_torque:
        print(f"\n  Torque test applies {TORQUE_TEST_NM} Nm to motor. Ctrl+C = stop.")
        print(f"  Enter to run, 's' to skip: ", end="")
        if input().strip().lower() != 's':
            results.append(run_test("Torque symmetry",
                                    test_torque_symmetry, ax))
    else:
        print(f"\n  Torque test skipped.")

    _active_odrv = None

    # ── Summary ──────────────────────────────────────────────────
    p = sum(1 for r in results if r["passed"] is True)
    w = sum(1 for r in results if r["passed"] is None)
    f = sum(1 for r in results if r["passed"] is False)

    print(f"\n{'='*60}")
    print(f"  {p} passed, {w} warnings, {f} failed")
    if f == 0:
        print(f"  STATUS: {'PASS' if w == 0 else 'PASS WITH WARNINGS'}")
    else:
        print(f"  STATUS: FAIL")
        for r in results:
            if r["passed"] is False:
                print(f"    ✘ {r['name']}: {r['msg']}")

        # If encoder deflection failed, recommend recalibration
        deflection_failed = any(
            r["passed"] is False and r["name"] == "Encoder deflection"
            for r in results
        )
        if deflection_failed:
            print(f"\n  ⚠ Encoder deflection failure detected.")
            print(f"    Recommended action: re-run odrive_setup.py to")
            print(f"    recalibrate motor and encoder.")
    print(f"{'='*60}\n")
    return f == 0


def main():
    """
    WHAT: CLI entry point — parse arguments and run verification.
    WHY: Provides both interactive and command-line axis selection.
    RETURNS: None. Exits with code 0 on success, 1 on failure.
    FMEA: N/A
    """
    parser = argparse.ArgumentParser(description="Verify ODrive S1 (GIM 8108-8)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pitch", action="store_true")
    group.add_argument("--roll", action="store_true")
    parser.add_argument("--skip-torque", action="store_true",
                        help="Skip the torque symmetry test")
    parser.add_argument("--skip-deflection", action="store_true",
                        help="Skip the encoder deflection sweep test")
    args = parser.parse_args()

    if args.pitch:
        axis_name = "pitch"
    elif args.roll:
        axis_name = "roll"
    else:
        print("Which axis?  [1] Pitch  [2] Roll")
        choice = input("> ").strip()
        axis_name = {"1": "pitch", "2": "roll"}.get(choice)
        if not axis_name:
            sys.exit(1)

    sys.exit(0 if run_tests(axis_name, args.skip_torque,
                            args.skip_deflection) else 1)


if __name__ == "__main__":
    main()
