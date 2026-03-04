#!/usr/bin/env python3
"""
capture_calibration.py
----------------------
Z-stack capture: KDC101 stage 0–12 mm in 0.2 mm steps, one Phantom image per position.

Hardware
  Arduino D8  → Camera BNC trigger input
  Arduino GND → Camera GND
  Mode 1 only: Arduino D13 ← KDC101 rear I/O "in-position" output

Trigger modes (set TRIGGER_MODE below)
  1 — wait for D13 HIGH (KDC101 hardware "in-position" signal)
  2 — rely on MoveTo() blocking call + SETTLE_S damping wait (no D13 wiring needed)

Usage
  python capture_calibration.py             # full run
  python capture_calibration.py --dry-run   # simulate without hardware
  python capture_calibration.py --start 5 --end 7
  python capture_calibration.py --out D:/captures
"""

import time
import csv
import argparse
import signal
import inspect
from pathlib import Path
from datetime import datetime

# pyfirmata uses inspect.getargspec, removed in Python 3.11
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

import numpy as np
import cv2
from tqdm import tqdm


# --- CONFIGURATION — edit before each session --------------------------------

TRIGGER_MODE = 1        # 1 = D13 hardware signal  |  2 = SDK settling (no D13 wire)
SETTLE_S     = 0.1      # Mode 2 only: wait (s) after MoveTo() before triggering

ARDUINO_PORT      = 'COM5'
STAGE_SERIAL      = '27XXXXXX'     # 8-digit serial on KDC101 label
KINESIS_DLL_PATH  = r'C:\Program Files\Thorlabs\Kinesis'
STAGE_CONFIG_NAME = 'Z825B'        # actuator name in Kinesis (e.g. Z825B, Z812B)

START_MM = 0.0
END_MM   = 12.0
STEP_MM  = 0.2          # 61 positions

TRIGGER_PULSE_MS  = 50      # D8 HIGH duration (ms)
TRIGGER_TIMEOUT_S = 15.0    # Mode 1: max wait for D13 (s)
CAPTURE_WAIT_S    = 0.5     # wait after trigger before reading frame from camera RAM
MOVE_TIMEOUT_MS   = 20000   # max time per MoveTo call (ms)

OUTPUT_BASE_DIR = Path.cwd() / 'outputs'

DRY_RUN = True             # Set True to simulate without hardware (overrides --dry-run)

# -----------------------------------------------------------------------------


# --- Stage -------------------------------------------------------------------

def init_stage(dry_run=False):
    if dry_run:
        print("[DRY RUN] Stage init skipped")
        return None

    import clr
    clr.AddReference(f"{KINESIS_DLL_PATH}\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
    clr.AddReference(f"{KINESIS_DLL_PATH}\\Thorlabs.MotionControl.GenericMotorCLI.dll")
    clr.AddReference(f"{KINESIS_DLL_PATH}\\ThorLabs.MotionControl.KCube.DCServoCLI.dll")

    # Do NOT call SimulationManager.InitializeSimulations() — for offline testing only.
    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI, DeviceConfiguration
    from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo

    print("Connecting to KDC101...")
    DeviceManagerCLI.BuildDeviceList()
    device = KCubeDCServo.CreateKCubeDCServo(STAGE_SERIAL)
    device.Connect(STAGE_SERIAL)
    time.sleep(0.25)
    device.StartPolling(250)
    time.sleep(0.25)
    device.EnableDevice()
    time.sleep(0.25)

    if not device.IsSettingsInitialized():
        device.WaitForSettingsInitialized(10000)
        if not device.IsSettingsInitialized():
            raise RuntimeError("KDC101 settings failed to initialise")

    m_config = device.LoadMotorConfiguration(
        STAGE_SERIAL, DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings
    )
    m_config.DeviceSettingsName = STAGE_CONFIG_NAME
    m_config.UpdateCurrentConfiguration()
    device.SetSettings(device.MotorDeviceSettings, True, False)

    print("Homing stage...")
    device.Home(60000)
    print("Stage homed.")
    return device


def move_stage(device, target_mm, dry_run=False):
    # Blocking — returns when encoder confirms stage has entered the target window.
    # Stage may still have residual oscillation; Mode 1/2 handle settling differently.
    if dry_run:
        return
    from System import Decimal
    device.MoveTo(Decimal(target_mm), MOVE_TIMEOUT_MS)


def get_stage_position(device, dry_run=False):
    if dry_run:
        return 0.0
    return float(str(device.Position))  # device.Position is System.Decimal


def close_stage(device, dry_run=False):
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


# --- Arduino -----------------------------------------------------------------

def init_arduino(dry_run=False):
    if dry_run:
        print("[DRY RUN] Arduino init skipped")
        return None, None, None

    import pyfirmata
    from pyfirmata.util import Iterator

    print(f"Connecting to Arduino on {ARDUINO_PORT}...")
    board = pyfirmata.Arduino(ARDUINO_PORT)
    Iterator(board).start()
    time.sleep(2)  # allow Firmata handshake

    d8 = board.get_pin('d:8:o')
    d8.write(0)

    if TRIGGER_MODE == 1:
        d13 = board.get_pin('d:13:i')
        print("Arduino ready (Mode 1: D8 + D13).")
    else:
        d13 = None
        print("Arduino ready (Mode 2: D8 only).")

    return board, d8, d13


def trigger(d8, d13, dry_run=False):
    """Wait for stage to settle, then pulse D8 to fire the camera."""
    if dry_run:
        tqdm.write("  [DRY RUN] trigger")
        return

    if TRIGGER_MODE == 1:
        t0 = time.time()
        while (d13.read() or 0.0) < 0.5:
            time.sleep(0.001)
            if time.time() - t0 > TRIGGER_TIMEOUT_S:
                raise TimeoutError(
                    f"Stage not in position after {TRIGGER_TIMEOUT_S:.0f}s — "
                    "check D13 wiring. If signal is active-LOW, flip < 0.5 to > 0.5."
                )
    else:
        time.sleep(SETTLE_S)  # MoveTo() confirmed position; wait for oscillation to damp

    d8.write(1)
    time.sleep(TRIGGER_PULSE_MS / 1000.0)
    d8.write(0)


def close_arduino(board, dry_run=False):
    if dry_run or board is None:
        return
    board.exit()
    print("Arduino disconnected.")


# --- Camera ------------------------------------------------------------------

def init_camera(dry_run=False):
    if dry_run:
        print("[DRY RUN] Camera init skipped")
        return None, None

    from pyphantom import Phantom, utils

    ph = Phantom()
    if ph.camera_count == 0:
        raise RuntimeError(
            "No Phantom camera found. "
            "Open PCC, confirm camera is live, and set trigger mode to External."
        )

    cam = ph.Camera(0)
    # Resolution and frame rate are taken from PCC — no need to set them here.
    cam.post_trigger_frames = 1
    cam.partition_count     = 1

    try:
        model = cam.get_selector_string(utils.CamSelector.gsModel)
    except Exception:
        model = "Unknown"
    print(f"Camera connected: {model}")
    return ph, cam


def arm_camera(cam, dry_run=False):
    """Arm camera for the next hardware trigger. Call before trigger()."""
    if dry_run:
        return
    cam.record()
    time.sleep(0.1)


def get_frame(cam, dry_run=False):
    """Read frame from camera RAM after trigger has fired."""
    if dry_run:
        return np.zeros((128, 128), dtype=np.uint16)
    from pyphantom import utils
    time.sleep(CAPTURE_WAIT_S)
    cine = cam.Cine(1)
    images = cine.get_images(utils.FrameRange(cine.range.last_image, cine.range.last_image))
    return np.squeeze(images)


def close_camera(ph, cam, dry_run=False):
    if dry_run or cam is None:
        return
    try:
        cam.clear_ram()
    except Exception:
        pass
    cam.close()
    ph.close()
    print("Camera disconnected.")


# --- Main --------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="KDC101 stage scan + Phantom camera capture")
    p.add_argument('--dry-run', action='store_true', help="Simulate without hardware")
    p.add_argument('--start', type=float, default=START_MM)
    p.add_argument('--end',   type=float, default=END_MM)
    p.add_argument('--step',  type=float, default=STEP_MM)
    p.add_argument('--out',   type=str,   default=None, help="Output directory")
    return p.parse_args()


def main():
    args = parse_args()
    dry_run = args.dry_run or DRY_RUN

    positions = np.arange(args.start, args.end + args.step / 2, args.step)
    n_pos = len(positions)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path(args.out) if args.out else OUTPUT_BASE_DIR / f"capture_{timestamp}"
    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    trigger_desc = (
        "Mode 1 — D13 hardware signal" if TRIGGER_MODE == 1
        else f"Mode 2 — SDK settling ({SETTLE_S}s)"
    )
    print(f"\nCapture: {n_pos} positions  {args.start:.1f}–{args.end:.1f} mm  |  {trigger_desc}")
    print(f"Output:  {output_dir}")
    if dry_run:
        print("DRY RUN — no hardware will move\n")

    device         = init_stage(dry_run)
    board, d8, d13 = init_arduino(dry_run)
    ph, cam        = init_camera(dry_run)

    interrupted = [False]
    def _stop(_sig, _frame):
        interrupted[0] = True
        tqdm.write("\nStopping after this position...")
    signal.signal(signal.SIGINT, _stop)

    log_rows = []
    try:
        for idx, target_mm in enumerate(tqdm(positions, desc="Capturing", unit="pos")):
            if interrupted[0]:
                break

            tqdm.write(f"  {target_mm:.1f} mm")
            move_stage(device, target_mm, dry_run)
            arm_camera(cam, dry_run)
            trigger(d8, d13, dry_run)
            actual_mm = get_stage_position(device, dry_run)
            img = get_frame(cam, dry_run)

            filename = f"pos_{idx:03d}_{target_mm:.1f}mm.tiff"
            if not dry_run:
                cv2.imwrite(str(output_dir / filename), img)
            else:
                tqdm.write(f"  [DRY RUN] {filename}")

            log_rows.append({
                'filename':          filename,
                'stage_position_mm': round(actual_mm, 4),
                'target_mm':         round(target_mm, 4),
            })
            tqdm.write(f"  → {filename}  (actual {actual_mm:.4f} mm)")

    finally:
        if log_rows:
            csv_path = output_dir / 'positions.csv'
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['filename', 'stage_position_mm', 'target_mm'])
                writer.writeheader()
                writer.writerows(log_rows)
            print(f"\n{len(log_rows)}/{n_pos} positions saved → {csv_path}")

        close_stage(device, dry_run)
        close_arduino(board, dry_run)
        close_camera(ph, cam, dry_run)


if __name__ == '__main__':
    main()
