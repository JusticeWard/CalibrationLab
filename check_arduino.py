"""
check_arduino.py
================

One-stop Arduino verification script. Run this before every lab session.

What it does:
  1. Lists all COM ports and flags any that look like an Arduino
  2. Connects via pyfirmata and confirms StandardFirmata is loaded
  3. Blinks D8 five times (camera trigger output) — verify on oscilloscope/LED
  4. Reads D13 for 10 seconds (stage in-position input) — jumper 5V→D13 to test

Usage:
  python check_arduino.py               # auto-detects Arduino COM port
  python check_arduino.py --port COM5   # specify port manually
  python check_arduino.py --no-pins     # firmware check only, skip pin tests
"""

import argparse
import inspect
import time

# pyfirmata uses inspect.getargspec which was removed in Python 3.11
if not hasattr(inspect, 'getargspec'):
    inspect.getargspec = inspect.getfullargspec

BLINK_COUNT  = 5
BLINK_MS     = 200   # D8 HIGH duration per blink (ms)
D13_READ_S   = 10    # seconds to read D13


def list_ports():
    from serial.tools import list_ports
    return [(p.device, p.description) for p in list_ports.comports()]


def find_arduino_port(ports):
    keywords = ('arduino', 'ch340', 'ch341', 'ftdi', 'usb serial')
    for port, desc in ports:
        if any(k in desc.lower() for k in keywords):
            return port
    return None


def run_checks(port: str, test_pins: bool):
    try:
        import pyfirmata
        from pyfirmata.util import Iterator
    except ImportError:
        print("ERROR: pyfirmata not installed.  Run: pip install pyfirmata")
        return

    # ── Step 1: Connect and check firmware ───────────────────────────────────
    print(f"\n[1/3] Connecting to {port}...")
    try:
        board = pyfirmata.Arduino(port)
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  → Check: correct COM port? StandardFirmata flashed? Arduino plugged in?")
        return

    it = Iterator(board)
    it.start()
    time.sleep(2)   # allow Firmata handshake

    name    = getattr(board, 'firmware', None) or 'unknown'
    version = getattr(board, 'firmware_version', None)
    ver_str = f"{version[0]}.{version[1]}" if version else "unknown"

    print(f"  Firmware : {name}  (v{ver_str})")

    if 'firmata' not in name.lower():
        print("  ERROR: StandardFirmata not detected.")
        print("  Flash it via Arduino IDE: File → Examples → Firmata → StandardFirmata → Upload")
        board.exit()
        return

    print("  OK — StandardFirmata confirmed.")

    if not test_pins:
        board.exit()
        print("\nPin tests skipped (--no-pins).")
        return

    d8  = board.get_pin('d:8:o')    # output: camera trigger
    d13 = board.get_pin('d:13:i')   # input:  stage in-position signal
    d8.write(0)

    # ── Step 2: Blink D8 ─────────────────────────────────────────────────────
    print(f"\n[2/3] Blinking D8 {BLINK_COUNT} times ({BLINK_MS} ms each)...")
    print("  Verify with oscilloscope or LED on D8.")
    print("  (The on-board 'L' LED will NOT light — it is on D13, not D8.)\n")
    for i in range(BLINK_COUNT):
        d8.write(1)
        time.sleep(BLINK_MS / 1000)
        d8.write(0)
        time.sleep(BLINK_MS / 1000)
        print(f"  Pulse {i+1}/{BLINK_COUNT}")
    d8.write(0)
    print("  D8 test complete.")

    # ── Step 3: Read D13 ─────────────────────────────────────────────────────
    print(f"\n[3/3] Reading D13 for {D13_READ_S} s (stage in-position input)...")
    print("  In the lab: D13 goes HIGH once the KDC101 stage reaches its target position.")
    print("  To test now: jumper a wire from Arduino 5V pin → D13 to simulate HIGH.\n")

    t_end = time.time() + D13_READ_S
    last  = None
    while time.time() < t_end:
        state = d13.read()
        level = "HIGH (in position)" if (state or 0) > 0.5 else "LOW  (still moving)"
        if state != last:
            print(f"  D13 = {level}")
            last = state
        time.sleep(0.05)

    print("  D13 test complete.")

    board.exit()
    print("\n✓ All checks passed — Arduino is correctly configured for capture_calibration.py.")


def main():
    parser = argparse.ArgumentParser(description="Arduino pre-flight check")
    parser.add_argument('--port',     default=None,  help="COM port (e.g. COM5); auto-detects if omitted")
    parser.add_argument('--no-pins',  action='store_true', help="Skip D8/D13 pin tests")
    args = parser.parse_args()

    # ── List all ports ────────────────────────────────────────────────────────
    ports = list_ports()
    print("COM ports detected:")
    if not ports:
        print("  (none — is the Arduino plugged in?)")
    for port, desc in ports:
        marker = " ← Arduino?" if find_arduino_port([(port, desc)]) else ""
        print(f"  {port:8s}  {desc}{marker}")

    target = args.port or find_arduino_port(ports)
    if not target:
        print("\nNo Arduino detected. Plug it in and re-run, or use --port COMx.")
        return

    run_checks(target, test_pins=not args.no_pins)


if __name__ == '__main__':
    main()
