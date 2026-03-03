#!/usr/bin/env python3
"""
capture_calibration.py
======================

Automated calibration capture: moves the ThorLabs KDC101 stage from START_MM to
END_MM in STEP_MM increments, capturing one Phantom camera image per position.

Hardware connections
--------------------
  KDC101 USB     → PC (Kinesis drivers)
  Phantom camera → PC (PCC software, Gigabit Ethernet)
  Arduino D8     → Camera BNC / hardware-trigger input   (camera trigger pulse)
  Arduino D13    ← KDC101 rear I/O "in-position" output  (stage settled signal)
  Arduino GND    → Camera GND                             (common ground)

Before running
--------------
  1. Flash StandardFirmata to Arduino Uno
       Arduino IDE → File → Examples → Firmata → StandardFirmata → Upload
  2. Open PCC, connect camera, set trigger mode to External (hardware trigger)
  3. Edit the CONFIGURATION block below (ARDUINO_PORT, STAGE_SERIAL, etc.)
  4. Confirm STAGE_CONFIG_NAME matches your actuator name in Kinesis software

Usage
-----
  python capture_calibration.py                     # normal run
  python capture_calibration.py --dry-run           # test without hardware
  python capture_calibration.py --start 5 --end 7   # custom range
  python capture_calibration.py --out D:/captures   # custom output dir

Output
------
  captures/capture_YYYYMMDD_HHMMSS/
      pos_000_0.0mm.tiff
      pos_001_0.2mm.tiff
      ...
      pos_060_12.0mm.tiff
      positions.csv          ← filename, stage_position_mm  (loads into calibration_gui.py)
"""

import sys
import time
import csv
import argparse
import signal
from pathlib import Path
from datetime import datetime

import numpy as np
import cv2
from tqdm import tqdm


# =============================================================================
# CONFIGURATION — edit these before each lab session
# =============================================================================

ARDUINO_PORT      = 'COM3'         # Arduino COM port (check Device Manager)
STAGE_SERIAL      = '27XXXXXX'     # 8-digit serial number on KDC101 label
KINESIS_DLL_PATH  = r'C:\Program Files\Thorlabs\Kinesis'
STAGE_CONFIG_NAME = 'Z825B'        # actuator model name saved in Kinesis software
                                   # (e.g. 'Z825B' for 25mm, 'Z812B' for 12mm)

START_MM          = 0.0            # scan start position (mm)
END_MM            = 12.0           # scan end position (mm)
STEP_MM           = 0.2            # step size (mm) → 61 positions

CAM_RESOLUTION    = (1024, 1024)   # camera resolution — match your PCC setting
CAM_FRAME_RATE    = 100            # frames per second

TRIGGER_PULSE_MS  = 50             # D8 HIGH duration (ms)
TRIGGER_TIMEOUT_S = 15.0           # max time to wait for D13 (stage in-position)
CAPTURE_WAIT_S    = 0.5            # wait after D8 trigger before reading cine from RAM
MOVE_TIMEOUT_MS   = 20000          # max time per MoveTo call (ms)

OUTPUT_BASE_DIR   = Path(r'C:\Users\justi\OneDrive\Desktop\coursework\lab_capture\captures')


# =============================================================================
# STAGE (ThorLabs KDC101 via pythonnet + Kinesis .NET DLLs)
# =============================================================================

def init_stage(dry_run: bool = False):
    """Connect to KDC101, load motor config, home the stage. Returns device object."""
    if dry_run:
        print("[DRY RUN] Stage init skipped")
        return None

    import clr
    clr.AddReference(f"{KINESIS_DLL_PATH}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
    clr.AddReference(f"{KINESIS_DLL_PATH}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
    clr.AddReference(f"{KINESIS_DLL_PATH}\\ThorLabs.MotionControl.KCube.DCServoCLI.dll")

    # NOTE: Do NOT call SimulationManager.InitializeSimulations() here —
    # that is for offline testing only and prevents real hardware from working.

    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI, DeviceConfiguration
    from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

    print("Connecting to KDC101 stage...")
    DeviceManagerCLI.BuildDeviceList()

    device = KCubeDCServo.CreateKCubeDCServo(STAGE_SERIAL)
    device.Connect(STAGE_SERIAL)
    time.sleep(0.25)
    device.StartPolling(250)          # poll status every 250 ms
    time.sleep(0.25)                  # allow settings to propagate
    device.EnableDevice()
    time.sleep(0.25)

    if not device.IsSettingsInitialized():
        device.WaitForSettingsInitialized(10000)
        if not device.IsSettingsInitialized():
            raise RuntimeError("KDC101 settings failed to initialise after 10 s")

    m_config = device.LoadMotorConfiguration(
        STAGE_SERIAL,
        DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings
    )
    m_config.DeviceSettingsName = STAGE_CONFIG_NAME
    m_config.UpdateCurrentConfiguration()
    device.SetSettings(device.MotorDeviceSettings, True, False)

    print("Homing stage (please wait)...")
    device.Home(60000)                # blocking, 60 s timeout
    print("Stage homed.")
    return device


def move_stage(device, target_mm: float, dry_run: bool = False):
    """Send blocking move command. Returns when motor command completes (not necessarily settled)."""
    if dry_run:
        return
    from System import Decimal
    device.MoveTo(Decimal(target_mm), MOVE_TIMEOUT_MS)


def get_stage_position(device, dry_run: bool = False) -> float:
    """Return current stage position in mm."""
    if dry_run:
        return 0.0
    return float(str(device.Position))  # device.Position is System.Decimal


def close_stage(device, dry_run: bool = False):
    """Move to safe mid-position and disconnect."""
    if dry_run or device is None:
        return
    from System import Decimal
    try:
        device.MoveTo(Decimal(6.0), MOVE_TIMEOUT_MS)  # park at mid-range
    except Exception:
        pass
    device.StopPolling()
    device.Disconnect()
    print("Stage disconnected.")


# =============================================================================
# ARDUINO (pyfirmata — StandardFirmata firmware required)
# =============================================================================

def init_arduino(dry_run: bool = False):
    """Connect to Arduino, set up D8 (output) and D13 (input)."""
    if dry_run:
        print("[DRY RUN] Arduino init skipped")
        return None, None, None

    import pyfirmata
    from pyfirmata.util import Iterator

    print(f"Connecting to Arduino on {ARDUINO_PORT}...")
    board = pyfirmata.Arduino(ARDUINO_PORT)
    it = Iterator(board)
    it.start()
    time.sleep(2)                        # allow Firmata handshake to complete

    d8  = board.get_pin('d:8:o')        # output: camera trigger pulse
    d13 = board.get_pin('d:13:i')       # input:  stage "in position" signal
    d8.write(0)                          # ensure trigger starts LOW
    print("Arduino connected.")
    return board, d8, d13


def wait_for_position_then_trigger(d8, d13, dry_run: bool = False):
    """
    Wait until D13 goes HIGH (stage physically settled at target position),
    then pulse D8 HIGH briefly to trigger the camera.

    D13 LOW  = stage still moving or settling → keep waiting
    D13 HIGH = stage confirmed in position    → fire camera trigger
    """
    if dry_run:
        tqdm.write("  [DRY RUN] Wait D13 high, pulse D8")
        return

    t0 = time.time()
    while (d13.read() or 0.0) < 0.5:    # wait while NOT in position
        time.sleep(0.001)
        if time.time() - t0 > TRIGGER_TIMEOUT_S:
            raise TimeoutError(
                f"Stage did not reach position within {TRIGGER_TIMEOUT_S:.0f} s — "
                f"check D13 wiring (KDC101 rear I/O 'in-position' output → Arduino D13).\n"
                f"If your signal is active-LOW, flip the < 0.5 condition to > 0.5 in "
                f"wait_for_position_then_trigger()."
            )

    # Stage confirmed in position — fire the camera trigger
    d8.write(1)
    time.sleep(TRIGGER_PULSE_MS / 1000.0)
    d8.write(0)


def close_arduino(board, dry_run: bool = False):
    if dry_run or board is None:
        return
    board.exit()
    print("Arduino disconnected.")


# =============================================================================
# PHANTOM CAMERA (pyphantom SDK — requires PCC running in external trigger mode)
# =============================================================================

def init_camera(dry_run: bool = False):
    """Connect to Phantom camera via pyphantom SDK, configure for triggered capture."""
    if dry_run:
        print("[DRY RUN] Camera init skipped")
        return None, None

    from pyphantom import Phantom, utils

    ph = Phantom()
    if ph.camera_count == 0:
        raise RuntimeError(
            "No Phantom camera found.\n"
            "Ensure PCC is running, camera is connected, and external trigger mode is set."
        )

    cam = ph.Camera(0)
    cam.resolution          = CAM_RESOLUTION
    cam.frame_rate          = CAM_FRAME_RATE
    cam.post_trigger_frames = 1   # capture 1 frame after hardware trigger fires
    cam.partition_count     = 1   # 1 RAM cine slot, reused each position

    try:
        model = cam.get_selector_string(utils.CamSelector.gsModel)
    except Exception:
        model = "Unknown"
    print(f"Camera connected: {model}")
    return ph, cam


def capture_and_retrieve(cam, dry_run: bool = False) -> np.ndarray:
    """
    Arm the camera for the next hardware trigger, wait for capture, return frame
    as a 2-D numpy array (H, W).

    Call BEFORE wait_for_position_then_trigger so the camera is armed
    when the D8 pulse fires.
    """
    if dry_run:
        return np.zeros((128, 128), dtype=np.uint16)

    from pyphantom import utils

    cam.record()            # arm camera — starts filling pre-trigger ring buffer
    time.sleep(0.1)         # allow arm to complete before trigger fires


def retrieve_frame(cam, dry_run: bool = False) -> np.ndarray:
    """Read the captured frame from camera RAM after trigger has fired."""
    if dry_run:
        return np.zeros((128, 128), dtype=np.uint16)

    from pyphantom import utils

    time.sleep(CAPTURE_WAIT_S)   # wait for single-frame capture to complete
    cine1 = cam.Cine(1)
    images = cine1.get_images(utils.FrameRange(
        cine1.range.last_image,
        cine1.range.last_image    # single frame
    ))
    return np.squeeze(images)    # (H, W) for monochrome


def close_camera(ph, cam, dry_run: bool = False):
    if dry_run or cam is None:
        return
    try:
        cam.clear_ram()
    except Exception:
        pass
    cam.close()
    ph.close()
    print("Camera disconnected.")


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="Calibration capture: KDC101 stage scan + Phantom camera trigger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--dry-run', action='store_true',
                   help="Test logic without moving hardware")
    p.add_argument('--start',   type=float, default=START_MM,
                   help=f"Start position in mm (default: {START_MM})")
    p.add_argument('--end',     type=float, default=END_MM,
                   help=f"End position in mm (default: {END_MM})")
    p.add_argument('--step',    type=float, default=STEP_MM,
                   help=f"Step size in mm (default: {STEP_MM})")
    p.add_argument('--out',     type=str,   default=None,
                   help="Override output directory path")
    return p.parse_args()


def main():
    args = parse_args()
    dry_run = args.dry_run

    positions = np.arange(args.start, args.end + args.step / 2, args.step)
    n_pos = len(positions)

    # Output directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if args.out:
        output_dir = Path(args.out)
    else:
        OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)
        output_dir = OUTPUT_BASE_DIR / f"capture_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Calibration Capture Script")
    print("=" * 60)
    print(f"  Output:    {output_dir}")
    print(f"  Positions: {n_pos}  ({args.start:.1f} → {args.end:.1f} mm, step {args.step:.1f} mm)")
    if dry_run:
        print("  *** DRY RUN — no hardware will be moved or triggered ***")
    print("=" * 60)

    # ── Pre-flight: connect all hardware before starting loop ─────────────
    device          = init_stage(dry_run)
    board, d8, d13  = init_arduino(dry_run)
    ph, cam         = init_camera(dry_run)

    # ── Graceful Ctrl-C: park stage and disconnect ────────────────────────
    interrupted = [False]

    def _on_interrupt(sig, frame):
        interrupted[0] = True
        tqdm.write("\nInterrupted by user — finishing current position then cleaning up...")

    signal.signal(signal.SIGINT, _on_interrupt)

    # ── Capture loop ──────────────────────────────────────────────────────
    log_rows = []
    try:
        for idx, target_mm in enumerate(tqdm(positions, desc="Capturing", unit="pos")):
            if interrupted[0]:
                tqdm.write("Stopping early at user request.")
                break

            tqdm.write(f"  [{idx+1}/{n_pos}]  target: {target_mm:.1f} mm")

            # 1. Move stage (blocking — motor command done, may not be mechanically settled)
            move_stage(device, target_mm, dry_run)

            # 2. Arm camera (do this while stage is settling, before D13 fires)
            capture_and_retrieve(cam, dry_run)

            # 3. Wait for D13 HIGH (stage physically settled) then pulse D8 (camera trigger)
            wait_for_position_then_trigger(d8, d13, dry_run)

            # 4. Query actual position (after settle confirmed)
            actual_mm = get_stage_position(device, dry_run)

            # 5. Retrieve captured frame from camera RAM
            img = retrieve_frame(cam, dry_run)

            # 6. Save as 16-bit TIFF
            filename = f"pos_{idx:03d}_{target_mm:.1f}mm.tiff"
            filepath = output_dir / filename
            if not dry_run:
                cv2.imwrite(str(filepath), img)
            else:
                tqdm.write(f"  [DRY RUN] Would save: {filename}")

            # 7. Log position
            log_rows.append({
                'filename':          filename,
                'stage_position_mm': round(actual_mm, 4),
                'target_mm':         round(target_mm, 4),
            })
            tqdm.write(f"  → saved: {filename}  (actual: {actual_mm:.4f} mm)")

    finally:
        # ── Write positions CSV ───────────────────────────────────────────
        if log_rows:
            csv_path = output_dir / 'positions.csv'
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(
                    f, fieldnames=['filename', 'stage_position_mm', 'target_mm']
                )
                writer.writeheader()
                writer.writerows(log_rows)
            print(f"\nSaved {len(log_rows)}/{n_pos} positions → {csv_path}")

        # ── Disconnect hardware ───────────────────────────────────────────
        close_stage(device, dry_run)
        close_arduino(board, dry_run)
        close_camera(ph, cam, dry_run)
        print("Done.")


if __name__ == '__main__':
    main()
