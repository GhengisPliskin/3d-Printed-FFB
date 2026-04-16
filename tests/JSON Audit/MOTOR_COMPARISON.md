# ODrive S1 Config Comparison: RMDX8 Pro V2 vs GIM 8108-8

> **RMDX8 Pro V2** (trim working, CAN node 1) vs **GIM 8108-8** (trim broken, CAN node 0)  
> Both are pitch-axis ODrive S1 config dumps.  
> Sources: `pitch_RMDX8_Pro_V2_final.json` | `pitch_GIM8108-8_ezyman_4-1-2026.json`

**Legend:** 🟢 Match | 🟡 Review | 🔴 Critical | 🔵 Info

---

## Key Context

> **The RMDX8 Pro had the same broken trim behavior before switching from the original driver to the ODrive S1.** The issues were corrected by the S1 migration and subsequent tuning. This confirms the problem is **controller tuning, not motor hardware.** The GIM's ODrive S1 is essentially running at near-default/untuned values — the same state the RMDX8 was in before its config was dialed in.
>
> **Implication:** The fix path is not "investigate what's wrong" — it's **"replicate the known fix."** Bring the GIM's S1 controller gains in line with the RMDX8's proven values, adjusted for hardware differences (lower inertia, different Kt, 48V vs 24V bus).

---

## Action Items (Priority Order)

> Items #1–#5 are almost certainly responsible for broken trim on the GIM.  
> Questions marked with **❓** need answers before changes.

### 🔴 #1 — vel_gain: 0.02 vs 3.0 (150× delta)

The GIM has essentially zero velocity damping. The RMDX8 uses 3.0. This is the single largest behavioral difference. Without velocity gain, the stick drifts through trim forces because nothing resists movement. Gravity on the pitch axis pulls the stick down and the controller doesn't push back.

- **Action:** Start at `vel_gain = 3.0`. Scale down if oscillation occurs (GIM has 75× less rotor inertia, so may need 1.5–2.0 instead).
- **❓ Ask:** Was `vel_gain` ever tuned on the GIM, or is 0.02 the value it shipped with? (Given the RMDX8 had the same issue pre-S1 tuning, this is likely an untouched default.)

### 🔴 #2 — vel_integrator_gain: 0.0 vs 2.2

Zero integrator = no mechanism to eliminate steady-state position error. Gravity pulls pitch down, nothing accumulates correction force to fight back. The RMDX8's 2.2 is aggressive but works.

- **Action:** Set to `2.2` initially. Tune down if overshoot or integrator windup occurs. Watch for slow oscillation — that's the integrator hunting.

### 🔴 #3 — vel_limit: 1.0 (enabled) vs 1000.0 (disabled)

GIM motor is hard-capped at 1 turn/s with `enable_vel_limit=true`. That's ~45°/s at the output shaft. Any force command requiring faster motion gets clipped. The RMDX8 has vel_limit disabled entirely.

- **Action:** Set `enable_vel_limit = false`. Or increase `vel_limit` to 1000 and keep enabled for safety. Either way, 1.0 is far too restrictive.

### 🔴 #4 — current_control_bandwidth: 150 Hz vs 1000 Hz (6.7×)

The current loop governs how accurately the motor tracks torque commands. At 150 Hz the GIM can't follow rapid force changes — everything is sluggish.

- **Action:** Increase to `1000` Hz. If audible noise appears, step down to 500 Hz.
- **❓ Ask:** Was 150 Hz deliberately set, or is this the value the GIM's ODrive shipped with? (ODrive S1 default is 1000 Hz — 150 Hz is non-standard.)

### 🔴 #5 — current_slew_rate_limit: 800 vs 10,000 A/s (12.5×)

GIM takes ~8.75 ms to reach full current. RMDX8 takes ~0.7 ms. Force transitions are an order of magnitude slower.

- **Action:** Increase to `10000` A/s.

### 🔴 #6 — Brake resistor disabled + regen current capped at −2A

RMDX8 has brake resistor ENABLED and allows −100A regen. GIM has resistor DISABLED and limits regen to −2A. When the GIM motor decelerates, regenerative energy has nowhere to go → overvoltage faults. Worse on a 48V system.

- **Action:** Set `brake_resistor0.enable = true`. Increase `dc_max_negative_current` to at least −10A. Verify a physical 2Ω brake resistor is wired to the ODrive.
- **❓ Ask:** Is there a brake resistor physically connected to the GIM's ODrive S1?

### 🔴 #7 — Bus voltage: 48V (GIM) vs 24V (RMDX8)

Completely different operating points. At 48V, back-EMF is higher and regen risk is higher. Not necessarily wrong — but makes #6 even more critical.

- **❓ Ask:** Why 48V for GIM vs 24V for RMDX8? PSU or performance choice?

### 🔴 #8 — pos_vel_mapper.scale: 0.125 vs 1.0 — unit mismatch

GIM uses 0.125 (1/8 for gear ratio). RMDX8 uses 1.0. Position/velocity units mean different things to each ODrive. If OpenFFBoard sends identical commands to both, the GIM interprets them in a different coordinate frame.

- **Action:** Determine how OpenFFBoard handles per-motor scaling.
- **❓ Ask:** Does OpenFFBoard send the same numerical torque/position commands to both motors, or does it scale per-motor?

### 🟡 #9 — pos_gain: 15 vs 38 (2.5×)

If OpenFFBoard uses position mode for spring/centering effects, GIM stiffness is 2.5× weaker.

- **Action:** Increase to `38` after vel_gain and integrator are tuned.

### 🟡 #10 — encoder_bandwidth: 200 Hz vs 1000 Hz (5×)

Lower encoder bandwidth = noisier velocity estimation, which compounds the already-low vel_gain.

- **Action:** Increase to `1000` Hz.

### 🟡 #11 — torque_ramp_rate: 105 vs 0.01 N.m/s

RMDX8's 0.01 N.m/s seems impossibly low. In PASSTHROUGH input_mode, torque ramp rate should be bypassed.

- **Action:** Verify that PASSTHROUGH mode bypasses `torque_ramp_rate`. If it does, no change needed.

### 🔵 #12 — RMDX8 torque_constant 3.126 vs datasheet Kt 2.60

3.126 / 2.60 = 1.20. Not the 9:1 gear ratio. May be empirically tuned. GIM Kt of 1.0 matches its datasheet motor Kt with no gear ratio included.

- **❓ Ask:** How was the RMDX8 `torque_constant` of 3.126 determined? Datasheet, calculation, or empirical tuning?

---

## Motor Configuration

`axis0.config.motor.*`

| Parameter | RMDX8 Pro (working) | GIM 8108-8 (broken) | Delta | Status | Notes |
|---|---|---|---|---|---|
| motor_type | 0 (HIGH_CURRENT) | 0 (HIGH_CURRENT) | — | 🟢 | |
| pole_pairs | 21 | 21 | — | 🟢 | |
| **torque_constant** | **3.126** | **1.0** | **3.1×** | **🔴** | RMDX8 Kt includes gear ratio factor. GIM is motor-only. |
| phase_resistance | 0.550 Ω | 0.393 Ω | — | 🟢 | Both auto-measured |
| phase_inductance | 0.265 mH | 0.178 mH | — | 🟢 | Both auto-measured |
| direction | -1 | -1 | — | 🟢 | |
| **current_control_bandwidth** | **1000 Hz** | **150 Hz** | **6.7×** | **🔴** | GIM current loop far too slow |
| current_soft_max | 10.0 A | 7.0 A | 1.4× | 🟡 | Max torque: RMDX8=31.3 Nm, GIM=7.0 Nm |
| current_hard_max | 23.0 A | 25.0 A | — | 🟢 | |
| **current_slew_rate_limit** | **10,000 A/s** | **800 A/s** | **12.5×** | **🔴** | GIM torque ramp 12.5× slower |
| calibration_current | 10.0 A | 8.3 A | — | 🟢 | |
| resistance_calib_max_voltage | 8.0 V | 4.0 V | 2× | 🟡 | GIM uses half voltage for R cal |
| ff_pm_flux_linkage | 0.0 (unused) | 0.14 (set) | — | 🟡 | GIM has flux linkage set but all FF disabled |
| bEMF_FF_enable | false | false | — | 🔵 | Neither uses back-EMF feedforward |
| wL_FF_enable | false | false | — | 🔵 | |
| power_torque_report_BW | 8000 Hz | 150 Hz | 53× | 🟡 | GIM torque telemetry BW much lower |

---

## Controller / PID Configuration

`axis0.controller.config.*` — **Primary source of the trim behavior difference.**

| Parameter | RMDX8 Pro (working) | GIM 8108-8 (broken) | Delta | Status | Notes |
|---|---|---|---|---|---|
| control_mode | 1 (TORQUE) | 1 (TORQUE) | — | 🟢 | |
| input_mode | 1 (PASSTHROUGH) | 1 (PASSTHROUGH) | — | 🟢 | |
| **vel_gain** | **3.0** | **0.02** | **150×** | **🔴** | Near-zero damping on GIM. #1 suspect. |
| **vel_integrator_gain** | **2.2** | **0.0** | **∞** | **🔴** | GIM has NO integrator. Cannot fight gravity. |
| **pos_gain** | **38.0** | **15.0** | **2.5×** | **🔴** | GIM spring stiffness 2.5× weaker |
| **vel_limit** | **1000.0** | **1.0** | **1000×** | **🔴** | GIM capped at 1 turn/s motor-side |
| **enable_vel_limit** | **false** | **true** | **bool** | **🔴** | RMDX8 limit OFF. GIM limit ON. |
| torque_ramp_rate | 0.01 Nm/s | 105 Nm/s | 10500× | 🟡 | RMDX8 value seems bypassed in passthrough |
| input_filter_bandwidth | 20 Hz | 70 Hz | 3.5× | 🔵 | GIM passes more high-freq noise |
| inertia | 0.0 | 0.0 | — | 🟡 | Neither compensates. GIM has 75× less physical inertia. |
| torque_soft_min | -31.25 Nm | -∞ | — | 🟡 | RMDX8 has explicit bounds |
| torque_soft_max | 31.25 Nm | ∞ | — | 🟡 | Consider ±7.0 on GIM |
| enable_overspeed_error | true | true | — | 🟢 | |

---

## Encoder & Position/Velocity Mapper

| Parameter | RMDX8 Pro (working) | GIM 8108-8 (broken) | Delta | Status | Notes |
|---|---|---|---|---|---|
| load_encoder | 13 (ONBOARD) | 13 (ONBOARD) | — | 🟢 | |
| commutation_encoder | 13 (ONBOARD) | 13 (ONBOARD) | — | 🟢 | |
| **encoder_bandwidth** | **1000 Hz** | **200 Hz** | **5×** | **🟡** | GIM encoder BW 5× lower |
| **pos_vel_mapper.scale** | **1.0** | **0.125** | **8×** | **🔴** | Different position unit scaling (gear ratio) |
| pos_vel_mapper.offset | 0.197 | 0.0 | — | 🔵 | RMDX8 has position offset |
| pos_vel_mapper.index_offset_valid | true | false | bool | 🟡 | GIM has no validated index offset |
| commutation_mapper.scale | -21.0 | -21.0 | — | 🟢 | |
| commutation_mapper.offset | -5.011 | 10.675 | — | 🔵 | Calibration-derived, expected to differ |
| commutation_mapper.index_offset_valid | true | false | bool | 🟡 | |

---

## Bus Voltage & Power

| Parameter | RMDX8 Pro (working) | GIM 8108-8 (broken) | Delta | Status | Notes |
|---|---|---|---|---|---|
| **dc_bus_undervoltage_trip** | **15.0 V** | **40.0 V** | — | **🔴** | RMDX8 = 24V PSU. GIM = 48V PSU. |
| **dc_bus_overvoltage_trip** | **26.0 V** | **54.0 V** | — | **🔴** | Confirms different operating voltages |
| **dc_max_negative_current** | **-100.0 A** | **-2.0 A** | **50×** | **🔴** | GIM barely absorbs regen |
| **brake_resistor0.enable** | **true** | **false** | **bool** | **🔴** | GIM has no regen dump |
| brake_resistor0.resistance | 2.0 Ω | 2.0 Ω | — | 🔵 | Same value but GIM disabled |
| CAN node_id | 1 | 0 | — | 🔵 | Expected |
| CAN encoder_msg_rate_ms | 0 (off) | 10 ms | — | 🔵 | GIM streams encoder at 100 Hz |
| CAN baud_rate | 1,000,000 | 1,000,000 | — | 🟢 | |

---

## Anticogging

| Parameter | RMDX8 Pro (working) | GIM 8108-8 (broken) | Delta | Status | Notes |
|---|---|---|---|---|---|
| anticogging.enabled | true | true | — | 🟡 | Verify calibration was run on each |
| anticogging.max_torque | 3.0 Nm | 1.0 Nm | 3× | 🟡 | GIM allows less correction |
| calib_coarse_integrator_gain | 25.0 | 250.0 | 10× | 🟡 | GIM 10× more aggressive in coarse cal |
| calib_start_vel | 0.5 | 0.25 | 2× | 🔵 | |
| calib_end_vel | 0.01 | 0.09 | 9× | 🔵 | RMDX8 more thorough |

---

## Datasheet Hardware Comparison

| Parameter | Unit | RMDX8 Pro | GIM 8108-8 | Delta | Status |
|---|---|---|---|---|---|
| Nominal Voltage | V | 24–48 | 48 (24–56) | — | 🔵 |
| Nominal Power | W | 166 | 80 | 2.1× | 🔴 |
| Nominal Torque (output) | N.m | 13 | 7.5 | 1.7× | 🔴 |
| Gear Ratio | — | 9:1 | 8:1 | — | 🔵 |
| Torque Constant (Kt) | N.m/A | 2.60 | 1.00 | 2.6× | 🔴 |
| Speed Constant (KV) | rpm/V | 30 | 5.7 | 5.3× | 🔵 |
| **Rotor Inertia** | **g·cm²** | **3400** | **45.5** | **75×** | **🔴** |
| Phase Resistance | Ω | 0.54 | 0.439 | — | 🟢 |
| Phase Inductance | mH | 0.28 | ~0.40 | — | 🟢 |
| Pole Pairs | — | 21 | 21 | — | 🟢 |
| Weight | g | 710 | 378 | 1.9× | 🔵 |
| Backlash | arcmin | 5 | <6 | — | 🟢 |
