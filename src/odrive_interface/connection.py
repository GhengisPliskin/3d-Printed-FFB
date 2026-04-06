"""
MODULE: odrive_interface/connection.py
PURPOSE: ODrive S1 discovery and connection management. Handles USB and CAN bus
         enumeration, connection lifecycle, and reconnection logic for both
         pitch and roll axis controllers.
FMEA: FM-002 (connection reliability affects calibration sequence)
PHASE: 1
"""
