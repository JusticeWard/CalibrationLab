# Calibration Data Capture — Lab Guide

**Experiment:** Automated z-stack image capture for defocus depth estimation
**Equipment:** ThorLabs KDC101 stage · Phantom high-speed camera · Arduino Uno · Lab PC
**Script:** `capture_calibration.py`
**Time:** ~20 min setup, ~5 min capture

---

## What This Experiment Does

The stage moves a target object from **0 mm to 12 mm** in **0.2 mm steps** (61 positions).
At each position, the camera captures one image. The result is a z-stack — a set of images
at known depths — used to calibrate the blur-to-depth model.

The Arduino acts as the hardware bridge between the computer and the instruments:

| Pin | Direction | Purpose |
|-----|-----------|---------|
| **D8** | Output → Camera | Sends a trigger pulse to tell the camera to take a picture |
| **D13** | Input ← Stage | Receives a signal confirming the stage has physically stopped moving |

> **Why do we need D13?** The computer tells the stage to move, but the stage takes a moment
> to physically arrive and settle. D13 ensures the camera only fires once the stage is truly
> stationary — otherwise images would be blurred by motion.

---

## Equipment Checklist

Before starting, confirm everything is present:

- [ ] KDC101 motor controller (small silver/black box, USB cable to PC)
- [ ] Linear translation stage (attached to KDC101)
- [ ] Phantom high-speed camera (connected via Ethernet cable to lab PC)
- [ ] Arduino Uno + USB cable
- [ ] BNC cable (camera trigger connection)
- [ ] 3× jumper wires (for D8, D13, GND)
- [ ] Lab PC with Kinesis, PCC, and Python 3.11 (`phantom_env`) installed

---

## Part 1 — One-Time Hardware Setup

> **Note:** If this setup has already been done by a previous user, skip to Part 2.

### 1.1 Flash the Arduino

The Arduino needs **StandardFirmata** firmware installed. This is a small program that
lets Python control the Arduino's pins directly from the computer.

1. Plug the Arduino into the lab PC via USB
2. Open **Arduino IDE** (search the Start menu)
3. Navigate to: **File → Examples → Firmata → StandardFirmata**
4. Click the **Upload** button (the right-arrow icon in the toolbar)
5. Wait for the message "Done uploading" at the bottom of the screen

This only needs to be done once — the firmware stays on the Arduino permanently.

### 1.2 Wire the Hardware

Using jumper wires and the BNC cable, make the following three connections:

```
Arduino Pin  │  Connect to
─────────────┼──────────────────────────────────────────────
D8           │  Camera BNC trigger input  (via BNC cable)
D13          │  KDC101 rear I/O "in-position" output pin
GND          │  Camera GND  AND  KDC101 GND (common ground)
```

> **WARNING — Check voltage before connecting D13.**
> The KDC101 rear I/O connector outputs **5 V TTL** signals. The Arduino Uno also runs at
> 5 V, so direct connection is safe. If you are uncertain, ask your supervisor before wiring.

> **TIP — Which pin on the KDC101 rear I/O?**
> The KDC101 has a 15-pin D-sub connector on the rear panel. Your supervisor can confirm
> which pin carries the "in-position" (motion complete) TTL output for your specific setup.

---

## Part 2 — Before Each Capture Session

### 2.1 Collect your hardware identifiers

**From Kinesis software** (ThorLabs stage control):

1. Open **Kinesis** (search the Start menu)
2. Your KDC101 will appear in the device list — note its **serial number** (8 digits, e.g. `27503986`)
3. Click into device settings — note the **stage/actuator name** (e.g. `Z825B`)

**From Device Manager** (Arduino COM port):

1. Right-click the Start button → **Device Manager**
2. Expand **Ports (COM & LPT)**
3. Find **USB Serial Device** — note the COM number (e.g. `COM4`)

### 2.2 Set up PCC (Phantom Camera Control)

1. Open **PCC** from the Start menu
2. Confirm the camera appears and shows a **live image**
3. Set the trigger mode to **External** — this means the camera waits for the hardware
   trigger from Arduino D8, rather than triggering itself
4. Note the current **resolution** and **frame rate** settings (you will enter these in the script)

### 2.3 Update the script configuration

Open `capture_calibration.py` in any text editor and update the five values at the top:

```python
ARDUINO_PORT      = 'COM4'       # ← your COM port from Device Manager
STAGE_SERIAL      = '27503986'   # ← your 8-digit serial number from Kinesis
STAGE_CONFIG_NAME = 'Z825B'      # ← your stage name from Kinesis device settings
CAM_RESOLUTION    = (1024, 1024) # ← match the resolution shown in PCC
CAM_FRAME_RATE    = 100          # ← match the frame rate shown in PCC
```

> **TIP:** Everything else in the script is pre-configured. The scan range (0–12 mm,
> 0.2 mm steps, 61 images) does not need to be changed.

---

## Part 3 — Running the Capture

Open a terminal (search **Command Prompt** or **PowerShell** in the Start menu) and run:

```bat
cd C:\Users\justi\OneDrive\Desktop\coursework\lab_capture
phantom_env\Scripts\activate
```

You should see `(phantom_env)` appear at the start of the prompt — this confirms you are
using the correct Python environment.

---

**Step 1 — Logic test (no hardware moves):**
```bat
python capture_calibration.py --dry-run
```
This simulates the full run without touching any hardware. You should see 61 positions
printed with no errors. Always do this first.

---

**Step 2 — Single position test (hardware test):**
```bat
python capture_calibration.py --start 6 --end 6
```
The stage moves to 6 mm (mid-range), the camera captures one image, and a TIFF file is
saved. Open the TIFF and confirm the image looks correct before proceeding.

---

**Step 3 — Full capture run:**
```bat
python capture_calibration.py
```
The stage homes to its starting position first, then steps through all 61 positions
automatically. A progress bar shows how many positions have been completed.

Total capture time: approximately **5 minutes**.

> **If something goes wrong:** Press **Ctrl+C** at any time to stop safely.
> The stage will park at 6 mm, the data collected so far will be saved to CSV,
> and all hardware connections will close cleanly.

---

## Part 4 — Verify the Output

After the run completes, navigate to the output folder:

```
lab_capture/captures/capture_YYYYMMDD_HHMMSS/
├── pos_000_0.0mm.tiff      ← image captured at 0.0 mm
├── pos_001_0.2mm.tiff      ← image captured at 0.2 mm
│   ...
├── pos_060_12.0mm.tiff     ← image captured at 12.0 mm
└── positions.csv           ← log of filenames and actual stage positions
```

Run through these checks before finishing:

- [ ] **61 TIFF files** are present in the folder
- [ ] **Images look correct** — open a few in an image viewer; you should see a focus
      gradient (images near the middle of the range should appear sharpest)
- [ ] **positions.csv is valid** — open in Excel; it should have two columns:
      `filename` and `stage_position_mm`, with 61 rows of data
- [ ] **Actual positions are accurate** — the `stage_position_mm` values should be
      within ±0.05 mm of the target positions (0.0, 0.2, 0.4 ... 12.0)

---

## Troubleshooting

| Error / Problem | Likely Cause | What to Do |
|---|---|---|
| `TimeoutError: Stage did not reach position` | D13 wiring issue | Check the wire from KDC101 rear I/O to Arduino D13 |
| `No Phantom camera found` | PCC is not open | Open PCC and confirm the camera shows a live view |
| `COM port not found` | Wrong port or Arduino not plugged in | Check Device Manager for the correct COM number |
| Stage doesn't home / moves wrong | `STAGE_CONFIG_NAME` is incorrect | Check the exact name in Kinesis device settings |
| Images are all black | Exposure or trigger mode not set | In PCC: confirm External trigger mode and check exposure |
| D13 never goes HIGH (timeout on every position) | Signal polarity is inverted | In `capture_calibration.py`, change `< 0.5` to `> 0.5` in `wait_for_position_then_trigger()` and re-run |

If you encounter an error not listed here, copy the full error message and contact your supervisor.
