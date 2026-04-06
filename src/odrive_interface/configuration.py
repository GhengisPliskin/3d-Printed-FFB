"""
MODULE: odrive_interface/configuration.py
PURPOSE: Motor, encoder, and controller configuration for ODrive S1 with
         GIM 8108-8 planetary gearbox BLDC motors. Reads hardware parameters
         from config/odrive_settings.yaml and applies them to the controller.
FMEA: FM-001 (PID tuning parameters), FM-002 (encoder configuration)
PHASE: 1
"""
