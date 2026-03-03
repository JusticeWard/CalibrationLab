"""
test_arduino.py
===============

Standalone Arduino connection test — run this at home (or in the lab)
to verify pyfirmata is working and D8/D13 are wired correctly.

What it does:
  1. Connects to the Arduino
  2. Blinks D8 five times (camera trigger pin) — verify with a multimeter or LED
  3. Reads D13 (stage in-position pin) and prints its state

Testing D13 at home (no stage):
  - Connect a jumper wire from Arduino 5V pin → D13: should read HIGH
  - Remove the wire (leave D13 unconnected): should read LOW (or float near 0)

Usage:
  python test_arduino.py
  python test_arduino.py --port COM5    (if COM3 is not correct)
"""

import time
import argparse

ARDUINO_PORT = 'COM3'      # change this if needed, or use --port argument
BLINK_COUNT  = 5
BLINK_MS     = 200         # D8 HIGH duration per blink (ms)


def main():
    parser = argparse.ArgumentParser(description="Arduino D8/D13 connection test")
    parser.add_argument('--port', default=ARDUINO_PORT, help="Arduino COM port")
    args = parser.parse_args()

    print(f"Connecting to Arduino on {args.port}...")
    try:
        import pyfirmata
        from pyfirmata.util import Iterator
    except ImportError:
        print("ERROR: pyfirmata not installed. Run: pip install pyfirmata")
        return

    try:
        board = pyfirmata.Arduino(args.port)
    except Exception as e:
        print(f"ERROR: Could not connect to Arduino on {args.port}")
        print(f"  → {e}")
        print("  Check: correct COM port? Arduino plugged in? StandardFirmata flashed?")
        return

    it = Iterator(board)
    it.start()
    time.sleep(2)   # allow Firmata handshake

    d8  = board.get_pin('d:8:o')    # output: camera trigger
    d13 = board.get_pin('d:13:i')   # input:  stage in-position
    d8.write(0)
    print("Arduino connected.\n")

    # ── Test D8 (camera trigger output) ──────────────────────────────────
    print(f"Testing D8 (camera trigger) — blinking {BLINK_COUNT} times...")
    print("  If you have a multimeter on D8, you should see it pulse 0 V → 5 V.\n")
    for i in range(BLINK_COUNT):
        d8.write(1)
        time.sleep(BLINK_MS / 1000)
        d8.write(0)
        time.sleep(BLINK_MS / 1000)
        print(f"  Blink {i+1}/{BLINK_COUNT}")

    d8.write(0)
    print("D8 test complete.\n")

    # ── Test D13 (stage in-position input) ───────────────────────────────
    print("Testing D13 (stage in-position input) — reading for 10 seconds...")
    print("  Connect a jumper from Arduino 5V → D13 to simulate HIGH.")
    print("  Remove the jumper to simulate LOW (stage moving).\n")

    t_end = time.time() + 10
    last_state = None
    while time.time() < t_end:
        state = d13.read()
        level = "HIGH (in position)" if (state or 0) > 0.5 else "LOW  (still moving)"
        if state != last_state:
            print(f"  D13 = {level}")
            last_state = state
        time.sleep(0.05)

    print("\nD13 test complete.")
    print("\n✓ All tests done. If D8 blinked and D13 responded to the jumper,")
    print("  the Arduino is correctly configured for the capture script.")

    board.exit()


if __name__ == '__main__':
    main()
