# Calibration Capture — Lab Guide

**Setup:** ~20 min (first time only) | **Capture:** ~5 min
**Script:** `capture_calibration.py` | **Output:** 61 TIFF images + `positions.csv`

---

## Equipment Checklist

- [ ] KDC101 motor controller (USB to PC)
- [ ] Linear translation stage (attached to KDC101)
- [ ] Phantom camera (Ethernet to PC)
- [ ] Arduino Uno (USB to PC)
- [ ] BNC cable: Arduino D8 → camera trigger input
- [ ] Common ground: Arduino GND → camera GND + KDC101 GND
- [ ] *(Mode 1 only)* Jumper: KDC101 rear I/O "in-position" → Arduino D13

> **Mode 1 vs Mode 2:** Mode 2 (no D13 wire) is simpler — start with it. Switch to Mode 1 only if images show motion blur. See README for details.

---

## Part 1 — One-Time Setup

### Flash Arduino
1. Open Arduino IDE
2. File → Examples → Firmata → **StandardFirmata** → Upload
3. Confirm "Done uploading"

### Wire Hardware
```
Arduino D8  → Camera BNC trigger input
Arduino GND → Camera GND + KDC101 GND
(Mode 1 only) KDC101 rear I/O "in-position" → Arduino D13
```

> **WARNING:** KDC101 rear I/O outputs 5 V TTL. Arduino Uno also runs at 5 V — direct connection is safe. If unsure, ask your supervisor.

### Install Python Environment
```bat
cd C:\Users\justi\OneDrive\Desktop\coursework\lab_capture
setup_lab_env.bat
```

---

## Part 2 — Before Each Session

### 1. Get hardware IDs
- **Kinesis:** Open Kinesis → note the KDC101 **serial number** (8 digits) and **actuator name** (e.g. `Z825B`)
- **Device Manager:** Right-click Start → Device Manager → Ports (COM & LPT) → find **USB-SERIAL CH340** → note COM number

### 2. Configure PCC
1. Open PCC → confirm camera shows live view
2. Set trigger to **External**

### 3. Update script config
Edit the top of `capture_calibration.py`:

```python
TRIGGER_MODE      = 2            # 1 = D13 hardware signal, 2 = SDK settling (no D13 wire)
SETTLE_S          = 0.1          # Mode 2 only: wait (s) after MoveTo() before triggering
ARDUINO_PORT      = 'COM5'       # from Device Manager
STAGE_SERIAL      = '27XXXXXX'   # 8-digit serial from Kinesis label
STAGE_CONFIG_NAME = 'Z825B'      # actuator name from Kinesis device settings
```

---

## Part 3 — Capture

```bat
cd C:\Users\justi\OneDrive\Desktop\coursework\lab_capture
phantom_env\Scripts\activate
```

```bat
python check_arduino.py                       # pre-flight: confirms firmware, blinks D8
python capture_calibration.py --dry-run       # logic test — no hardware moves
python capture_calibration.py --start 6 --end 6   # single-position test — check image is sharp
python capture_calibration.py                 # full 0–12 mm run (~5 min, 61 images)
```

> **Ctrl+C** stops cleanly — stage parks at 6 mm, partial CSV saved.

---

## Part 4 — Verify Output

```
captures/capture_YYYYMMDD_HHMMSS/
├── pos_000_0.0mm.tiff  …  pos_060_12.0mm.tiff
└── positions.csv
```

- [ ] 61 TIFF files present
- [ ] Focus gradient visible — images near mid-range should appear sharpest
- [ ] No motion blur (if blurred: increase `SETTLE_S` or switch to Mode 1)
- [ ] `positions.csv` has 61 rows; `stage_position_mm` within ±0.05 mm of targets

`positions.csv` loads directly into `calibration/calibration_gui.py`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `TimeoutError: Stage did not reach position` | Mode 1: check D13 wiring, or switch to `TRIGGER_MODE = 2` |
| D13 never goes HIGH | Mode 1: flip `< 0.5` to `> 0.5` in `wait_for_position_then_trigger()` |
| Images motion-blurred | Mode 2: increase `SETTLE_S` (try `0.3`) or switch to `TRIGGER_MODE = 1` |
| `No Phantom camera found` | Open PCC, confirm camera is live, set trigger to External |
| `COM port not found` | Run `check_arduino.py` — lists all ports and flags the Arduino |
| Arduino not detected | Install CH340 driver; port shows as "USB-SERIAL CH340" in Device Manager |
| Stage homes wrong direction | Check actuator name in Kinesis matches `STAGE_CONFIG_NAME` |
| Images all black | Check exposure in PCC; confirm External trigger mode is set |
