# Hardware — 3D-Printed FFB Joystick

## Bill of Materials

| Qty | Component | Notes |
|---|---|---|
| 2 | GIM 8108-8 Planetary Gearbox BLDC Motor | Pitch and roll axes |
| 2 | ODrive S1 Motor Controller | One per axis, CAN bus connected |
| 1 | Open FFB Joystick Board | USB HID + FFB processing |
| 1 | 3D Printed Gimbal Structure | See STL files below |
| — | Fasteners, bearings, wiring | TBD — detailed BOM to follow |

## 3D Print Settings

> Placeholder — to be populated with tested settings.

- **Motor mounts and thermal-critical parts:** PETG or ASA required (C-005: must
  withstand sustained 60°C). Do NOT use PLA for parts near motors.
- **Non-structural parts:** PLA acceptable.
- **Infill:** TBD per part — structural analysis needed.
- **Layer height:** TBD.

## STL Files

Place STL files in the `stl/` directory. Technical drawings go in `drawings/`.

## Assembly Notes

> Placeholder — to be populated during Phase 1.

### Thermal Breaks

Motor mounts should include thermal breaks (air gaps or insulating washers) between
the motor housing and the 3D-printed structure to slow heat transfer. See FM-003
and FM-005 in `docs/FMEA.md`.
