#!/usr/bin/env python3
"""Keep the HP OmniBook X16 mute / mic-mute key LEDs in sync with PipeWire (DT mode).

Runs as a systemd --user service. Watches PipeWire with `pw-dump --monitor`; after each
burst of changes it reads the default sink/source mute state with wpctl and, only when
it changed, tells the HP EC to switch the LED.

EC protocol (from ACPI ssdt3 \\_SB.HQEX / \\_SB.WMID.SMLS, tested Nov 6 2026, Stage 24):
  EC = I2C 0x76 on the QUP i2c at 0xa84000 (DT &i2c9), node /dev/omnibook-ec (udev rule).
  wait reg 0xEF == 0x00; write reg 0xED {main, sub}; wait reg 0xEF == 0xE0.
  {01,84} before each LED command (as SMLS does); speaker LED {06,08 off | 88 on},
  mic LED {06,09 off | 89 on}.
ONLY these commands are sent. Never {BD,01} (upset the keyboard, Nov 6).
On stop (logout / shutdown) both LEDs are switched OFF, so Windows starts clean.
"""
import ctypes, fcntl, os, select, signal, subprocess, sys, time

DEV = "/dev/omnibook-ec"
ADDR = 0x76
I2C_RDWR = 0x0707
I2C_M_RD = 0x0001
QUIET = 0.15   # s without PipeWire events before syncing
MAXWAIT = 0.5  # s max delay while events keep coming


class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]


class RdwrData(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]


def xfer(fd, wr, rdlen=0):
    wbuf = (ctypes.c_uint8 * len(wr))(*wr)
    msgs = [Msg(ADDR, 0, len(wr), wbuf)]
    rbuf = None
    if rdlen:
        rbuf = (ctypes.c_uint8 * rdlen)()
        msgs.append(Msg(ADDR, I2C_M_RD, rdlen, rbuf))
    arr = (Msg * len(msgs))(*msgs)
    fcntl.ioctl(fd, I2C_RDWR, RdwrData(arr, len(msgs)))
    return list(rbuf) if rbuf is not None else []


def wait_status(fd, want):
    for _ in range(40):
        if xfer(fd, [0xEF], 1)[0] == want:
            return True
        time.sleep(0.005)
    return False


def ec_cmd(fd, main, sub):
    if not wait_status(fd, 0x00):
        raise IOError("EC busy")
    xfer(fd, [0xED, main, sub])
    if not wait_status(fd, 0xE0):
        raise IOError(f"EC did not finish {{{main:02x},{sub:02x}}}")


def set_leds(want, have):
    """want/have: dict 'speaker'/'mic' -> bool. Returns the new 'have'."""
    new = dict(have)
    fd = os.open(DEV, os.O_RDWR)
    try:
        for name, base in (("speaker", 0x08), ("mic", 0x09)):
            if want[name] != have.get(name):
                ec_cmd(fd, 0x01, 0x84)
                ec_cmd(fd, 0x06, base | (0x80 if want[name] else 0))
                new[name] = want[name]
                print(f"{name} LED {'on' if want[name] else 'off'}", flush=True)
    finally:
        os.close(fd)
    return new


def muted(target):
    r = subprocess.run(["wpctl", "get-volume", target], capture_output=True, text=True)
    return r.returncode == 0 and "[MUTED]" in r.stdout


def read_state():
    return {"speaker": muted("@DEFAULT_AUDIO_SINK@"), "mic": muted("@DEFAULT_AUDIO_SOURCE@")}


def main():
    if not os.path.exists(DEV):
        print(f"{DEV} not present (ACPI mode or DTB without &i2c9): nothing to do")
        return 0
    have = {}  # unknown at start: first sync always writes both LEDs
    mon = subprocess.Popen(["pw-dump", "--monitor", "--no-colors"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def stop(*_):
        mon.terminate()
        try:
            set_leds({"speaker": False, "mic": False}, {})
        except Exception as e:
            print(f"could not switch LEDs off: {e}", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    fd = mon.stdout.fileno()
    first_dirty = time.monotonic()
    last_event = first_dirty
    while True:
        if first_dirty is None:
            timeout = None
        else:
            now = time.monotonic()
            timeout = max(0, min(last_event + QUIET, first_dirty + MAXWAIT) - now)
        r, _, _ = select.select([fd], [], [], timeout)
        if r:
            if not os.read(fd, 1 << 16):
                print("pw-dump exited", flush=True)
                return 1  # systemd restarts us
            last_event = time.monotonic()
            if first_dirty is None:
                first_dirty = last_event
            continue
        first_dirty = None
        try:
            have = set_leds(read_state(), have)
        except OSError as e:
            print(f"EC write failed: {e}", flush=True)
            have = {}  # retry both on the next event


if __name__ == "__main__":
    sys.exit(main())
