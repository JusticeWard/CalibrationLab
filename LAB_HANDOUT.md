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

The Arduino acts as the hardware bridge between the computer and the camera:

| Pin | Direction | Purpose |
|-----|-----------|---------|
| **D8** | Output → Camera | Sends a trigger pulse to tell the camera to take a picture |
| **D13** | Input ← Stage | *Mode 1 only* — receives a signal confirming the stage has physically stopped moving |

### Two ways to confirm the stage has settled

The script has two trigger modes, set by `TRIGGER_MODE` at the top of `capture_calibration.py`:

**Mode 1 — D13 hardware signal** (most robust, requires extra wiring)
The KDC101 outputs a TTL "in-position" signal on its rear I/O connector once the stage
has been held within the target position window for a configured settling time. Arduino D13
reads this signal. The camera only fires once D13 goes HIGH.

**Mode 2 — SDK confirmation** (no D13 wiring needed)
The `MoveTo()` SDK call is blocking — it returns only when the encoder confirms the stage
has entered the target position window. After this, a short `SETTLE_S` delay (default 0.1 s)
allows any residual mechanical oscillation to damp, then the camera fires.

> **Which to use?** Start with Mode 2 — it requires less wiring. Switch to Mode 1 if any
> images show motion blur, or if your supervisor has already wired D13.

---

## Equipment Checklist

Before starting, confirm everything is present:

- [ ] KDC101 motor controller (small silver/black box, USB cable to PC)
- [ ] Linear translation stage (attached to KDC101)
- [ ] Phantom high-speed camera (connected via Ethernet cable to lab PC)
- [ ] Arduino Uno + USB cable
- [ ] BNC cable (camera trigger — D8 to camera)
- [ ] 2× jumper wires (D8 to BNC, GND to camera) — or 3× if using Mode 1 (add D13 wire)
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

The following connections are required regardless of trigger mode:

```
Arduino Pin  │  Connect to
─────────────┼──────────────────────────────────────────────
D8           │  Camera BNC trigger input  (via BNC cable)
GND          │  Camera GND  AND  KDC101 GND (common ground)
```

**Mode 1 only** — add this connection if using the hardware signal:

```
Arduino Pin  │  Connect to
─────────────┼──────────────────────────────────────────────
D13          │  KDC101 rear I/O "in-position" output pin
```

> **WARNING — Check voltage before connecting D13.**
> The KDC101 rear I/O connector outputs **5 V TTL** signals. The Arduino Uno also runs at
> 5 V, so direct connection is safe. If you are uncertain, ask your supervisor before wiring.

> **TIP — Which pin on the KDC101 rear I/O?**
> The KDC101 has a 15-pin D-sub connector on the rear panel. Your supervisor can confirm
> which pin carries the "in-position" (motion complete) TTL output for your specific setup.

### 1.3 Set up the Python environment

If `phantom_env` does not already exist in the `lab_capture` folder, run the setup script:

```bat
cd C:\Users\justi\OneDrive\Desktop\coursework\lab_capture
setup_lab_env.bat
```

This creates a Python 3.11 virtual environment and installs all required packages
(including the Phantom SDK). It only needs running once per PC.

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
3. Find the entry labelled **USB-SERIAL CH340** — note the COM number (e.g. `COM5`)

> **TIP:** If you are unsure which port is the Arduino, run `python check_arduino.py`
> (after activating `phantom_env`) — it lists all ports and flags the Arduino automatically.

### 2.2 Set up PCC (Phantom Camera Control)

1. Open **PCC** from the Start menu
2. Confirm the camera appears and shows a **live image**
3. Set the trigger mode to **External** — this means the camera waits for the hardware
   trigger from Arduino D8, rather than triggering itself
4. Note the current **resolution** and **frame rate** settings (you will enter these in the script)

### 2.3 Update the script configuration

Open `capture_calibration.py` in any text editor and update the values at the top:

```python
TRIGGER_MODE      = 2            # ← 1 = D13 hardware signal, 2 = SDK settling (no D13 wire)
SETTLE_S          = 0.1          # ← Mode 2 only: settling wait in seconds after MoveTo()

ARDUINO_PORT      = 'COM5'       # ← your COM port from Device Manager
STAGE_SERIAL      = '27503986'   # ← your 8-digit serial number from Kinesis
STAGE_CONFIG_NAME = 'Z825B'      # ← your stage name from Kinesis device settings
CAM_RESOLUTION    = (1024, 1024) # ← match the resolution shown in PCC
CAM_FRAME_RATE    = 100          # ← match the frame rate shown in PCC
```

> **TIP:** The scan range (0–12 mm, 0.2 mm steps, 61 images) does not need to be changed.

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

**Step 0 — Arduino pre-flight check** (do this first, every session):
```bat
python check_arduino.py
```
Confirms StandardFirmata is loaded and blinks D8 five times. In Mode 1, it also reads
D13 for 10 seconds — jog the stage in Kinesis during this time to verify D13 goes HIGH.
In Mode 2, ignore the D13 reading section.

---

**Step 1 — Logic test (no hardware moves):**
```bat
python capture_calibration.py --dry-run
```
Simulates the full run without touching any hardware. Confirm 61 positions are printed and
the startup banner shows the correct trigger mode before proceeding.

---

**Step 2 — Single position test (hardware test):**
```bat
python capture_calibration.py --start 6 --end 6
```
The stage moves to 6 mm (mid-range), the camera captures one image, and a TIFF file is
saved. Open the TIFF — if it is sharp and correctly exposed, proceed to the full run.
If it looks motion-blurred (Mode 2), increase `SETTLE_S` or switch to Mode 1.

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
- [ ] **No motion blur** — if images look smeared, increase `SETTLE_S` or switch to Mode 1
- [ ] **positions.csv is valid** — open in Excel; it should have two columns:
      `filename` and `stage_position_mm`, with 61 rows of data
- [ ] **Actual positions are accurate** — the `stage_position_mm` values should be
      within ±0.05 mm of the target positions (0.0, 0.2, 0.4 ... 12.0)

---

## Troubleshooting

| Error / Problem | Likely Cause | What to Do |
|---|---|---|
| `TimeoutError: Stage did not reach position` | Mode 1 only — D13 wiring issue | Check wire from KDC101 rear I/O to Arduino D13, or switch to `TRIGGER_MODE = 2` |
| D13 never goes HIGH (timeout every position) | Mode 1 only — signal polarity inverted | In `capture_calibration.py`, change `< 0.5` to `> 0.5` in `wait_for_position_then_trigger()` |
| Images are motion-blurred | Mode 2 — stage still oscillating | Increase `SETTLE_S` (try `0.3`) or switch to `TRIGGER_MODE = 1` |
| `No Phantom camera found` | PCC is not open | Open PCC and confirm the camera shows a live view |
| `COM port not found` | Wrong port or Arduino not plugged in | Run `check_arduino.py` — it lists all ports and flags the Arduino |
| Arduino not detected by `check_arduino.py` | CH340 driver missing | Install CH340 driver; port appears as "USB-SERIAL CH340" in Device Manager |
| Stage doesn't home / moves wrong | `STAGE_CONFIG_NAME` is incorrect | Check the exact name in Kinesis device settings |
| Images are all black | Exposure or trigger mode not set | In PCC: confirm External trigger mode and check exposure |

If you encounter an error not listed here, copy the full error message and contact your supervisor.
