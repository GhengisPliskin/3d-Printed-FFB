#!/usr/bin/env python3
"""
MODULE: odrive_backup.py
PURPOSE: Create a full ODrive config backup with auto-dated filename.
         Wrapper around odrivetool backup-config that handles directory
         creation and date formatting cross-platform.
FMEA: N/A — defensive measure, not safety-critical.

USAGE:
    python odrive_backup.py --pitch          # Backup pitch axis
    python odrive_backup.py --roll           # Backup roll axis
    python odrive_backup.py --pitch --label hotfix   # Custom label

REQUIREMENTS: pip install odrive  (Python 3.13 — 3.14 is NOT compatible)
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime


# All backups go to ~/odrive_backups/ — same location as the setup
# and centering scripts so everything is in one directory.
BACKUP_DIR = os.path.join(os.path.expanduser("~"), "odrive_backups")


def find_odrivetool():
    """
    WHAT: Locate the odrivetool executable across platforms.
    WHY: On Windows, subprocess can't always find venv scripts via PATH
         alone. This function checks PATH first, then falls back to the
         Scripts directory alongside the current Python executable.
    RETURNS: Full path to odrivetool, or None if not found.
    """
    # Try PATH first (works on Linux/macOS, sometimes Windows)
    path = shutil.which("odrivetool")
    if path:
        return path

    # Fall back to the directory containing the Python executable.
    # In a venv, both python.exe and odrivetool live in Scripts/.
    scripts_dir = os.path.dirname(sys.executable)
    for name in ["odrivetool", "odrivetool.exe"]:
        candidate = os.path.join(scripts_dir, name)
        if os.path.exists(candidate):
            return candidate

    return None


def main():
    """
    WHAT: Create a dated full config backup of one ODrive.
    WHY: odrivetool backup-config requires a full filepath and doesn't
         auto-generate dates. This script handles the boilerplate so
         backups are one command with consistent naming.
    RETURNS: None. Exits with code 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        description="Back up ODrive config with auto-dated filename")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pitch", action="store_true")
    group.add_argument("--roll", action="store_true")
    parser.add_argument("--label", type=str, default="manual",
                        help="Custom label for the backup (default: manual)")
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

    os.makedirs(BACKUP_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{axis_name}_{date_str}_{args.label}.json"
    filepath = os.path.join(BACKUP_DIR, filename)

    print(f"\n  ODrive Backup — {axis_name.upper()}")
    print(f"  Target: {filepath}")
    print(f"  Waiting for ODrive...")

    odrivetool = find_odrivetool()
    if odrivetool is None:
        print(f"  ✘ odrivetool not found. Is the venv active?")
        print(f"    C:\\odrive_env\\Scripts\\activate")
        sys.exit(1)

    try:
        result = subprocess.run(
            [odrivetool, "backup-config", filepath],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  ✔ Backup saved ({size:,} bytes)")
            print(f"  Restore with:")
            print(f"    odrivetool restore-config {filepath}")
        else:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            print(f"  ✘ Backup failed: {stderr}")
            sys.exit(1)
    except FileNotFoundError:
        print(f"  ✘ odrivetool not found. Is the venv active?")
        print(f"    C:\\odrive_env\\Scripts\\activate")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"  ✘ Timed out — no ODrive found.")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
