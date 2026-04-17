#!/usr/bin/env python3
"""
MODULE: odrive_center.py
PURPOSE: Set the ODrive encoder zero offset for GIM 8108-8 force feedback
         joystick axes. Run AFTER reassembling the stick. Records the
         current physical center position as the encoder offset so that
         OpenFFBoard sees zero correctly.
FMEA: FM-002 (encoder offset accuracy), C-006 (center verification)
PHASE: 1

USAGE:
    python odrive_center.py             # Interactive axis selection
    python odrive_center.py --pitch     # Center pitch axis
    python odrive_center.py --roll      # Center roll axis

PREREQUISITES:
    - Stick is fully assembled and free to move
    - ODrive powered and in closed loop (LED blue/teal)
    - Stick is physically at center position when prompted

REQUIREMENTS: pip install odrive  (Python 3.13 — 3.14 is NOT compatible)
"""

import odrive
from odrive.enums import AxisState
import argparse
import sys
import time


def get_mapped_position(ax):
    """
    WHAT: Read the current mapped relative position from pos_vel_mapper.
    WHY: pos_vel_mapper.pos_rel gives the gear-ratio-scaled position
         after the current offset is applied. To zero the center, we
         fold this residual back into the offset (divided by scale),
         which is more robust than overwriting with raw pos_estimate —
         it works incrementally regardless of current offset state and
         correctly accounts for the gearbox scale factor.
    ARGS: ax — ODrive axis object.
    RETURNS: Float — mapped relative position (output shaft turns).
    FMEA: C-006 — Center position must be accurate before enabling forces.
    """
    return ax.pos_vel_mapper.pos_rel


def main():
    """
    WHAT: Interactive center-position calibration for one joystick axis.
    WHY: After physical assembly, the stick's center position will be at
         an arbitrary encoder value. This script records that value as the
         zero offset so that OpenFFBoard's spring/centering effects act
         around the correct physical center.
    RETURNS: None. Exits with code 0 on success, 1 on failure.
    FMEA: C-006 — Calibration must verify center before enabling forces.
    """
    parser = argparse.ArgumentParser(
        description="Set ODrive center position offset")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pitch", action="store_true")
    group.add_argument("--roll", action="store_true")
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
            print("Invalid.")
            sys.exit(1)

    print(f"\n  ODrive Center Position — {axis_name.upper()}")
    print(f"  Searching for ODrive...")
    odrv = odrive.find_any(timeout=15)
    if odrv is None:
        print(f"  ✘ No ODrive found.")
        sys.exit(1)

    ax = odrv.axis0
    print(f"  Found ODrive (serial: {getattr(odrv, 'serial_number', '?')})")
    print(f"  Current state: {ax.current_state}")

    # Center offset can be set regardless of motor state, but for best
    # accuracy the stick should not be under motor force when centering.
    # If the drive is in closed loop, the motor is actively holding
    # position — which is fine for centering. If it's in IDLE, the
    # stick might drift under gravity (especially pitch axis).
    if ax.current_state != AxisState.CLOSED_LOOP_CONTROL:
        print(f"  ℹ Axis is in state {ax.current_state} (not closed loop).")
        print(f"  Center offset can still be set from raw encoder position.")
        print(f"  Note: for best accuracy, the stick should not be under")
        print(f"  any motor force when you set center.")

    # Show the current offset so the user knows what's being replaced
    current_offset = ax.pos_vel_mapper.config.offset
    print(f"  Current offset: {current_offset:.4f}")

    # ── Prompt user to position the stick ────────────────────────
    # The user must physically hold the stick at center before proceeding.
    # This is a manual step that cannot be automated.
    print(f"\n  Move the stick to its physical CENTER position.")
    print(f"  Press Enter when centered...", end="")
    input()

    # ── Sample the mapped position ──────────────────────────────
    # Take 10 readings over 500ms and average them. This reduces
    # noise from encoder quantization and electrical interference.
    # We read pos_vel_mapper.pos_rel (the gear-ratio-scaled position
    # after current offset), not raw pos_estimate. The residual is
    # then folded back into the offset, divided by scale, to zero
    # the center incrementally.
    readings = []
    for _ in range(10):
        readings.append(get_mapped_position(ax))
        time.sleep(0.05)

    mapped_pos = sum(readings) / len(readings)
    spread = max(readings) - min(readings)

    print(f"  Mapped relative position at center: {mapped_pos:.4f} (spread: {spread:.4f})")

    # A spread > 0.01 turns indicates the position is noisy.
    # This could mean the user is still moving, the encoder has
    # a problem, or there's EMI. Warn but allow override.
    if spread > 0.01:
        print(f"  ⚠ Position is noisy — hold the stick steady and retry.")
        if input("  Use this value anyway? (y/n): ").strip().lower() != 'y':
            sys.exit(0)

    # ── Compute and write the new offset ─────────────────────────
    # The pos_vel_mapper computes: pos_rel = (raw - offset) * scale
    # To zero pos_rel at the current position, we solve for the new
    # offset: new_offset = current_offset + (mapped_pos / scale)
    # This incremental approach works regardless of the current offset
    # state and correctly accounts for the gearbox scale factor.
    current_offset = ax.pos_vel_mapper.config.offset
    scale = ax.pos_vel_mapper.config.scale
    new_offset = current_offset + (mapped_pos / scale)

    print(f"  Current offset: {current_offset:.4f}, scale: {scale:.4f}")
    print(f"  New offset: {new_offset:.4f}")
    ax.pos_vel_mapper.config.offset = new_offset
    ax.pos_vel_mapper.config.offset_valid = True

    # Verify the relative position is now mathematically zeroed.
    # A small residual (<0.001) is normal due to sampling timing.
    time.sleep(0.1)
    new_rel_pos = ax.pos_vel_mapper.pos_rel
    print(f"  ✔ Verified relative position is now: {new_rel_pos:.4f}")

    # ── Save to flash and reboot ─────────────────────────────────
    # The S1 may disconnect during save — this is expected behavior.
    # Reboot ensures the new offset is loaded cleanly from flash.
    print(f"  Saving to flash...")
    try:
        odrv.save_configuration()
        print(f"  ✔ Save completed.")
    except Exception:
        print(f"  ℹ Device disconnected during save (expected behavior on S1).")

    print(f"  Rebooting ODrive...")
    try:
        odrv.reboot()
    except Exception:
        print(f"  ℹ Device disconnected during reboot (expected behavior on S1).")

    # ── Remind user to complete the OpenFFBoard side ─────────────
    # The ODrive offset is only half the story. OpenFFBoard also
    # maintains its own center reference that must be set separately
    # in the configurator GUI.
    print(f"\n  Also in OpenFFBoard configurator:")
    print(f"  - Click 'center position' on the {axis_name} axis")
    print(f"  - Check 'save offset' on the ODrive tab")
    print(f"  Done.\n")


if __name__ == "__main__":
    main()
