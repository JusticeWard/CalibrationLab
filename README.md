# Calibration Capture — Lab Setup Guide

Automated z-stack capture: KDC101 stage moves 0–12 mm in 0.2 mm steps, Phantom camera
captures one frame per position via hardware trigger.

---

## Scripts in this folder

| Script | Purpose |
|---|---|
| `capture_calibration.py` | Main capture script — runs the full z-stack |
| `check_arduino.py` | Pre-flight check — verify firmware, blink D8, read D13 |
| `setup_lab_env.bat` | One-click Python 3.11 environment setup for lab PC |

> **Note on Python 3.11 compatibility:** pyfirmata 1.1.0 uses `inspect.getargspec`, which was
> removed in Python 3.11. All scripts in this folder patch this automatically at startup — no
> manual fix is needed.

---

## Trigger Modes

The script has two modes for confirming the stage has settled before firing the camera trigger.
Set `TRIGGER_MODE` at the top of `capture_calibration.py`.

| Mode | How it works | D13 wiring needed? |
|---|---|---|
| **1** (recommended) | Polls Arduino D13 for the KDC101 hardware "in-position" TTL signal. Most robust — the controller confirms the position has been held within tolerance for a settling time. | Yes |
| **2** | Relies on `MoveTo()` being a blocking call — it returns only when the encoder confirms the stage has entered the target position window. A short `SETTLE_S` sleep (default 0.1 s) then waits for any residual mechanical oscillation to damp before triggering. | No |

Start with Mode 2 if D13 wiring is awkward. Switch to Mode 1 if images show motion blur.

---

## Hardware Wiring

**Both modes** — always required:
```
Arduino D8  →  Camera BNC hardware-trigger input
Arduino GND →  Camera GND  (common ground)
KDC101 USB  →  PC
```

**Mode 1 only** — additional connection:
```
KDC101 rear I/O "in-position" TTL output  →  Arduino D13
```

Full diagram:
```
┌──────────────┐  USB   ┌──────────┐  USB   ┌─────────────────────┐
│ ThorLabs     │───────►│    PC    │◄───────│   Arduino Uno        │
│ KDC101       │        └──────────┘        │                      │
│              │                            │  D8  ───────────────►│ Camera BNC trigger
│ Rear I/O     │· · · · · · · · · · · · · ►│  D13 (Mode 1 only)   │
│ "in-position"│                            │  GND ────────────────│ Camera GND
└──────────────┘                            └─────────────────────-┘
```

> **WARNING — Check voltage before connecting D13.**
> The KDC101 rear I/O outputs 5 V TTL. The Arduino Uno also runs at 5 V — direct connection
> is safe. If unsure, ask your supervisor before wiring.

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

### 4. Set up Python environment (lab PC)

Run the setup script once — it creates the `phantom_env` virtual environment and installs
all dependencies including pyphantom from the local Phantom SDK wheel:

```bat
cd C:\Users\justi\OneDrive\Desktop\coursework\lab_capture
setup_lab_env.bat
```

Or manually:
```bat
pip install "C:\Users\justi\OneDrive\My Documents\Phantom\PhSDK11\Python\pyphantom-3.11.11.806-py311-none-any.whl"
pip install -r requirements.txt
```

---

## Before Each Run

### 1. Update script configuration

Edit the CONFIGURATION block at the top of `capture_calibration.py`:

| Variable | What to set |
|---|---|
| `TRIGGER_MODE` | `1` = D13 hardware signal (needs wiring), `2` = SDK settling (no wiring) |
| `SETTLE_S` | Mode 2 only: seconds to wait after `MoveTo()` before triggering (default `0.1`) |
| `ARDUINO_PORT` | COM port (check Device Manager → Ports — Arduino clone shows as "USB-SERIAL CH340") |
| `STAGE_SERIAL` | 8-digit serial on KDC101 label (e.g. `'27500125'`) |
| `STAGE_CONFIG_NAME` | Actuator model in Kinesis GUI (e.g. `'Z825B'`) |
| `CAM_RESOLUTION` | Match your PCC capture resolution |
| `CAM_FRAME_RATE` | Match your PCC frame rate setting |

Make sure PCC is open and camera is showing live view before running.

### 2. Run Arduino pre-flight check

```bat
phantom_env\Scripts\activate
python check_arduino.py
```

This confirms StandardFirmata is loaded and blinks D8 five times. In Mode 1, it also reads
D13 for 10 seconds — jog the stage in Kinesis during this time to verify the signal goes HIGH.
See `check_arduino.py --help` for options.

---

## Running the Script

```bat
cd C:\Users\justi\OneDrive\Desktop\coursework\lab_capture
phantom_env\Scripts\activate

# Step 1 — Logic test (no hardware moves):
python capture_calibration.py --dry-run

# Step 2 — Single-position hardware test (6 mm):
python capture_calibration.py --start 6 --end 6

# Step 3 — Full 0–12 mm run:
python capture_calibration.py
```

The startup banner always shows the active trigger mode so you can confirm before the run starts.

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
| `TimeoutError: Stage did not reach position` | Mode 1 only — check D13 wiring from KDC101 rear I/O to Arduino D13. Or switch to `TRIGGER_MODE = 2`. |
| D13 never goes HIGH (timeout every position) | Mode 1 only — signal polarity may be inverted. Flip `< 0.5` to `> 0.5` in `wait_for_position_then_trigger()`. |
| Images are motion-blurred (Mode 2) | Stage still oscillating when triggered. Increase `SETTLE_S` (try `0.3`) or switch to `TRIGGER_MODE = 1`. |
| `No Phantom camera found` | Open PCC first, confirm camera is live before running script |
| `pythonnet` import error | Run `pip install pythonnet` inside `phantom_env` and confirm Kinesis DLLs are installed |
| Stage homes in wrong direction | Check actuator polarity in Kinesis GUI |
| Images all black | Check camera exposure in PCC; confirm external trigger mode is set |
| Arduino not found by `check_arduino.py` | Look for "USB-SERIAL CH340" in Device Manager → Ports, not "USB Serial Device" |
