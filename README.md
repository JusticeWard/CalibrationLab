# Calibration Capture — Lab Setup Guide

Automated z-stack capture: KDC101 stage moves 0–12 mm in 0.2 mm steps, Phantom camera
captures one frame per position via hardware trigger.

---

## Hardware Wiring

```
┌──────────────┐  USB   ┌──────────┐  USB   ┌─────────────────────┐
│ ThorLabs     │───────►│    PC    │◄───────│   Arduino Uno        │
│ KDC101       │        └──────────┘        │                      │
│              │                            │  D8  ───────────────►│ Camera BNC trigger
│ Rear I/O     │                            │  D13 ◄───────────────│ KDC101 rear I/O
│ "in-position"│───────────────────────────►│  GND ────────────────│ Camera GND
└──────────────┘                            └─────────────────────-┘

KDC101 rear I/O connector:  "in-position" TTL output  →  Arduino D13
Arduino D8 (output)         →  Camera BNC hardware-trigger input
Common GND between Arduino and camera is essential.
```

---

## One-Time Setup

### 1. Flash Arduino
- Open Arduino IDE
- File → Examples → Firmata → **StandardFirmata** → Upload
- Only needs doing once per Arduino

### 2. Install ThorLabs Kinesis
- Download and install Kinesis software from ThorLabs website
- DLLs land in `C:\Program Files\Thorlabs\Kinesis\`
- Connect KDC101 via USB, open Kinesis, confirm device appears
- Note the **serial number** (8 digits, on label) and the **motor config name**
  (shown in Kinesis device settings, e.g. `Z825B`)

### 3. Install Phantom PCC
- Install PCC (Phantom Camera Control) from Vision Research
- Connect camera via Gigabit Ethernet
- **Set trigger mode to External** (hardware trigger via BNC)

### 4. Install Python dependencies
```bat
pip install "C:\Users\justi\OneDrive\My Documents\Phantom\PhSDK11\Python\pyphantom-3.11.11.806-py311-none-any.whl"
pip install -r requirements.txt
```

---

## Before Each Run

Edit the CONFIGURATION block at the top of `capture_calibration.py`:

| Variable | What to set |
|---|---|
| `ARDUINO_PORT` | COM port (check Device Manager → Ports) |
| `STAGE_SERIAL` | 8-digit serial on KDC101 label (e.g. `'27500125'`) |
| `STAGE_CONFIG_NAME` | Actuator model in Kinesis GUI (e.g. `'Z825B'`) |
| `CAM_RESOLUTION` | Match your PCC capture resolution |
| `CAM_FRAME_RATE` | Match your PCC frame rate setting |

Make sure PCC is open and camera is showing live view before running.

---

## Running the Script

```bat
cd C:\Users\justi\OneDrive\Desktop\coursework\lab_capture

# Test without hardware first:
python capture_calibration.py --dry-run

# Single-position test (6mm):
python capture_calibration.py --start 6 --end 6

# Full 0–12mm run:
python capture_calibration.py
```

**Ctrl-C** will interrupt cleanly — stage parks at 6 mm, hardware disconnects, partial
CSV is saved.

---

## Output

```
captures/capture_YYYYMMDD_HHMMSS/
├── pos_000_0.0mm.tiff
├── pos_001_0.2mm.tiff
├── ...
├── pos_060_12.0mm.tiff
└── positions.csv          ← filename + stage_position_mm
```

`positions.csv` loads directly into `calibration/calibration_gui.py`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `TimeoutError: Stage did not reach position` | Check D13 wiring; KDC101 must output TTL "in-position" signal on rear I/O |
| `No Phantom camera found` | Open PCC first, confirm camera is live before running script |
| `pythonnet` import error | Run `pip install pythonnet` and confirm Kinesis is installed |
| Stage homes in wrong direction | Check actuator polarity in Kinesis GUI |
| D13 logic inverted (never HIGH) | Flip `< 0.5` to `> 0.5` in `wait_for_position_then_trigger()` |
| Images all black | Check camera exposure in PCC; confirm external trigger mode is set |
