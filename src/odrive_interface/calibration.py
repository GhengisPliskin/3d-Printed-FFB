"""
MODULE: odrive_interface/calibration.py
PURPOSE: Startup calibration sequence for ODrive S1 controllers. Executes
         motor calibration, encoder index search, and center position
         verification before enabling force output.
FMEA: FM-002 (index pulse reliability, center offset verification)
PHASE: 1
CONSTRAINT: C-006 — Calibration must complete index search and center
            verification before enabling force output.
"""
