# Import the ODrive library
import odrive
from odrive.enums import * # This imports all enums like MotorType, EncoderId, AxisState, etc.

odrv0.axis0.requested_state = AxisState.IDLE

print("Searching for ODrive...")
# Find a connected ODrive device. This will wait until an ODrive is found.
# Ensure your ODrive is connected via USB to your computer.
odrv0 = odrive.find_any()
print("ODrive found!")

# --- 1. Motor Configuration (Initial Setup - as before) ---
# The GIM8108 is a Permanent Magnet Synchronous Motor (PMSM) [our conversation].
# It is typically controlled via current, hence PMSM_CURRENT_CONTROL [our conversation, 6].
print(f"Setting motor type to: PMSM_CURRENT_CONTROL")
odrv0.axis0.config.motor.motor_type = MotorType.PMSM_CURRENT_CONTROL # [2]

# The GIM8108 motor has 21 pole pairs.
print(f"Setting motor pole pairs to: 21")
odrv0.axis0.config.motor.pole_pairs = 21 # [3]

# The GIM8108 motor has a phase-to-phase inductance of 0.000403 mH (which is 4.03e-7 H).
# Line-to-neutral inductance of one motor phase, assuming a wye-wound motor. 
# Equivalent to the line-to-line inductance divided by two.
# Used to derive the gains and feedforward terms for the current controller.
# When using MotorType.PMSM_CURRENT_CONTROL, this is measured automatically during AxisState.MOTOR_CALIBRATION.
# print(f"Setting motor phase inductance to: 0.000000403 H")
# odrv0.axis0.config.motor.phase_inductance = 0.000000403 # [1]

# The GIM8108 motor has a torque constant of 1.00 N·m/A.
# HOWEVER: 8.27 / 6.67 rpm / v = 1.24
# If you decide that you would rather command torque in units of Amps, 
# you could simply set the torque constant to 1.
print(f"Setting motor torque constant to: 1.24 N·m/A")
odrv0.axis0.config.motor.torque_constant = 1.24 # [3]

# The GIM8108 motor has a phase-to-phase resistance of 0.439 Ohm.
# When using MotorType.PMSM_VOLTAGE_CONTROL, this must be set manually
# based on the motor’s datasheet or external measurements. 
# In this case it is the main parameter that facilitates control of current 
# and must be set accurately to ensure precise resulting current.
# Measured at 0.9 phm on 11-18-2025 -EJS
print(f"Setting motor phase resistance to: 0.439 Ohm")
odrv0.axis0.config.motor.phase_resistance = 0.439 # [1]

# If you want the controller to think in output turns with 
# the encoder on the motor shaft, scale = 1/(4096*8) = 1/32768
# That will include the 8:1 gearbox....
# otherwise 1.0 / 4096.0 is correct for encode on the end shaft.
odrv0.axis0.pos_vel_mapper.config.scale = 0.125 # 1.0 / 4096.0

# Second Tier Tuneing:    
odrv0.axis0.config.motor.bEMF_FF_enable = False
odrv0.axis0.config.motor.dI_dt_FF_enable = False   # test later if needed

odrv0.axis0.config.motor.ff_pm_flux_linkage = 0.14
odrv0.axis0.config.motor.ff_pm_flux_linkage_valid = True

# After running motor test:
#odrv0.axis0.config.motor.motor_model_l_d = #<measured_value>
#odrv0.axis0.config.motor.motor_model_l_q = #<measured_value>
#odrv0.axis0.config.motor.motor_model_l_dq_valid = True

odrv0.axis0.config.motor.current_slew_rate_limit = 800.0   # (A/s)

odrv0.axis0.config.motor.fw_enable = False

odrv0.axis0.config.motor.power_torque_report_filter_bandwidth = 150.0

# Setup some gains for position and velocity mode:
odrv0.axis0.controller.config.pos_gain = 15.0
odrv0.axis0.controller.config.vel_gain = 0.02
odrv0.axis0.controller.config.vel_integrator_gain = 0.0

# --- 2. Current Limits (as before) ---
# Set the current soft and hard limits for the motor.
# GIM8108 Nominal Current: 7A. This is a good value for current_soft_max.
# GIM8108 Stall Current: 25A. This is a good value for current_hard_max to protect the motor.
# The ODrive S1 can handle 40A continuous, but the motor's limit (25A) is the crucial factor.
print(f"Setting current soft max to: 7A")
odrv0.axis0.config.motor.current_soft_max = 7.0 # [4, our conversation]
print(f"Setting current hard max to: 25.0A")
odrv0.axis0.config.motor.current_hard_max = 25.0 # [4, our conversation]

# --- 3. Encoder Configuration (as before) ---
# The ODrive S1 has an on-board MA702 magnetic encoder [4].
# This encoder has a 12-bit resolution [5-8].
# The ONBOARD_ENCODER0 enumeration refers to this on-board encoder [2].
# Both the load encoder and commutation encoder are set to use this on-board encoder [9].
print(f"Set load encoder to: ONBOARD_ENCODER0")
odrv0.axis0.config.load_encoder = EncoderId.ONBOARD_ENCODER0 # [2, 9]
print(f"Set commutation encoder to: ONBOARD_ENCODER0")
odrv0.axis0.config.commutation_encoder = EncoderId.ONBOARD_ENCODER0 # [2, 9]

# --- 4. Calibration Parameters Adjustment for Low Resistance Motors ---
# To address "PHASE_RESISTANCE_OUT_OF_RANGE" error [conversation], we can adjust the calibration current
# and the maximum voltage used during resistance calibration [9-11].
# The GIM8108 has a low phase resistance (0.439 Ohm) and nominal current of 7A [1].
# Setting calibration_current to a lower value (e.g., 2-3A) can be safer and more effective for low-resistance motors.
# Similarly, adjusting resistance_calib_max_voltage can fine-tune the calibration process [10, 11].
# A value like 2.0V or 3.0V is often used for low-resistance motors.
# (Note: Specific optimal values for calibration_current and resistance_calib_max_voltage for the GIM8108
# are not explicitly in the provided sources, but these are common adjustments for this type of error.)

# Default safe start: 6–8 A — almost always safe and often sufficient for 
# reliable electrical zero detect on larger motors.
# Practical tuning/calibration: 8–12 A — 
# good compromise: strong enough to settle commutation and encoder alignment, but not too destructive.
# If you must push: 15–20 A — only if:
# R_phase is small enough that heating is manageable, and
# PSU and ODrive current limits support it, and
# The motor/gearbox/fixture can safely handle the resulting shaft torque, and
# You only use short pulses and monitor temperature.
odrv0.axis0.config.motor.calibration_current = 8.3

# Measure Phase to Phase and divide by two to obtain the R_Phase value.
# resistance_calib_max_voltage ≈ 1.1 × calibration_current × R_Phase
# Datasheet: 0.439 Ohm Phase to phase, R_PhaseDatasheet = 0.2195
# Measured R_Phase for GIM8108 = __X___
print(f"Adjusting resistance calibration max voltage to 3.0V for low resistance motor.")
odrv0.axis0.config.motor.resistance_calib_max_voltage = 4.0 # V

# We may need to setup some lockin values to obtain a complete calibration:
# conservative safe values to set once (then run calibration)
odrv0.axis0.config.calibration_lockin.current = 8.0    # start here, do not exceeed 15 A.
odrv0.axis0.config.calibration_lockin.ramp_time = 0.4
odrv0.axis0.config.calibration_lockin.ramp_distance = 3.1415927
odrv0.axis0.config.calibration_lockin.vel = 40.0
odrv0.axis0.config.calibration_lockin.accel = 20.0

# --- 5. Disable Startup Calibration (to run it manually) ---
# We will explicitly request FULL_CALIBRATION_SEQUENCE later.
# Therefore, disable the automatic startup calibrations to avoid conflicts.
print(f"Disabling startup motor calibration.")
odrv0.axis0.config.startup_motor_calibration = False # [9]
print(f"Disabling startup encoder offset calibration.")
odrv0.axis0.config.startup_encoder_offset_calibration = False # [9]
print(f"Disabling startup closed loop control.")
odrv0.axis0.config.startup_closed_loop_control = False # [9]

#OpenFFB specifics:
odrv0.axis0.pos_estimate = odrv0.onboard_encoder0.raw
odrv0.axis0.pos_vel_mapper.config.offset_valid = True
odrv0.axis0.pos_vel_mapper.config.approx_init_pos_valid = True
odrv0.axis0.controller.config.absolute_setpoints = True
#set resistor value:
odrv0.config.brake_resistor0.resistance = 2.0
odrv0.config.brake_resistor0.enable = True
#set CAN bus nodeID
odrv0.axis0.config.can.node_id = 1
odrv0.can. config.baud_rate = 1000000
#fix bus voltages:
odrv0.config.dc_bus_undervoltage_trip_level = 40
odrv0.config.dc_bus_overvoltage_trip_level = 53
#fix the torque mode:
odrv0.axis0.controller.config.enable_torque_mode_vel_limit = False

# --- 6. Save Configuration (intermediate save before calibration) ---
# Save the adjusted calibration parameters and disabled startup sequence.
print("Saving initial configuration to ODrive...")
odrv0.save_configuration() # [9]
print("Rebooting ODrive to apply initial configuration...")
odrv0 = odrive.find_any() # Re-find ODrive after reboot
odrv0.reboot() # [9]


# -- PART TWO ---

import odrive
from odrive.enums import * # This line already imports AxisState and ProcedureResult
import time

print("Finding ODrive...")
odrv0 = odrive.find_any()

print("Starting full calibration sequence...")
odrv0.axis0.requested_state = AxisState.FULL_CALIBRATION_SEQUENCE

print("Waiting for calibration to complete...")
while odrv0.axis0.current_state != AxisState.IDLE:
    time.sleep(0.1) # Wait a bit before checking state again

# Check calibration result
if odrv0.axis0.procedure_result == ProcedureResult.SUCCESS:
    print("Calibration successful!")
else:
    # Corrected line: Access the name attribute of the ProcedureResult enum
    print(f"Calibration failed!") [2]
    # You might want to dump errors here for more detailed troubleshooting
    odrive.utils.dump_errors(odrv0, True)

print(f"Disabling startup motor calibration.")
odrv0.axis0.config.startup_motor_calibration = False # [9]
print(f"disable startup encoder offset calibration to keep from moving.")
odrv0.axis0.config.startup_encoder_offset_calibration = False # [9]

odrv0.axis0.config.startup_closed_loop_control = True # [9]

# Save configuration (important after successful calibration)
odrv0.save_configuration()
print("Script finished.")


# Oscilation specifics

# 2a) Slow the inner current loop a bit (adds inherent damping for big, low-R gimbals)
##odrv0.axis0.motor.config.current_control_bandwidth = 200   # start 150–300; raise later if stable
# 2b) Low-pass filter the commanded torque to cut CAN jitter/high-freq content
# This parameter filters the incoming commands (like torque commands from your OpenFFBoard via CAN) 
# before they are processed by the ODrive's internal controller:
##odrv0.axis0.controller.config.input_filter_bandwidth = 80  # try 50–120 Hz
# Try to lower the bandwidth on the odrv0.axis0.config.commutation_encoder_bandwidth
##odrv0.axis0.config.commutation_encoder_bandwidth = 700


# 2c) Gentle torque ramp so step changes don’t excite the mechanics
##odrv0.axis0.controller.config.torque_ramp_rate = 100.0     # Nm/s equivalent; tune 50–300 as needed
# 2d) Tighten watchdog so stale CAN doesn’t leave stale torque
##odrv0.axis0.config.watchdog_timeout = 0.05   # 50 ms
##odrv0.axis0.controller.config.enable_watchdog = True

# also consider lowering encoder bandwidth about 20-30%.
##odrv0.axis0.encoder.config.bandwidth = 700


# CLass ODrive.Can.Config
# tx_brs = false

#init_torque
#calib_range = 0.02 #2%
#calib_scan_distance
#input_torque_scale = 1000

#encoder_msg_rate_ms


### PART 3.0 Center the stick #####
# If the motor does not start in the desired center...
# check this reading when stick is at center: 
odrv0.axis0.pos_estimate
odrv0.axis0.pos_vel_mapper.config.offset = 0.0 # Set this to that number
odrv0.save_configuration()