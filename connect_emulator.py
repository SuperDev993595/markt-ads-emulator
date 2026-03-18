"""
Connect ADB to your emulator. Run this once before starting Appium/login if needed.

  python connect_emulator.py          # use config.EMULATOR_ADB_PORT
  python connect_emulator.py 5554     # LDPlayer
  python connect_emulator.py 5555     # BlueStacks
"""

import subprocess
import sys
import config

def main():
    port = config.EMULATOR_ADB_PORT
    if len(sys.argv) >= 2:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Usage: connect_emulator.py [port]", file=sys.stderr)
            sys.exit(1)
    adb = config.ADB_PATH or "adb"
    host = config.EMULATOR_ADB_HOST
    addr = f"{host}:{port}"
    print(f"Connecting to {addr} ...")
    r = subprocess.run([adb, "connect", addr], timeout=10)
    if r.returncode != 0:
        sys.exit(r.returncode)
    r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5)
    print(r.stdout)
    print("Done. Start your emulator's Chrome (or let Appium start it), then run markt_emulator_login.")

if __name__ == "__main__":
    main()
