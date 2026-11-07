#!/usr/bin/env python3
"""HP OmniBook X16: make the mic-mute key work (runs as root, systemd system service).

The keyboard (HID over I2C 0416:C300) sends mic-mute as Keyboard-page usage 0x8000, but its
report descriptor declares 0..0x8000 usages and the kernel keeps only HID_MAX_USAGES (12288)
("ignoring exceeding usage max"), so the key is dropped and hwdb cannot remap it.

This reads the keyboard's hidraw node (read-only; nothing is written to the keyboard),
watches input report 0x08 (modifiers, reserved, 6 x 16-bit key slots, little endian) for
0x8000, and presses/releases KEY_MICMUTE on a virtual uinput keyboard.
Other key data is ignored and never stored or logged.
"""
import fcntl, glob, os, struct, sys

HID_ID = "0018:0416:C300"
MICMUTE_USAGE = 0x8000
KEY_MICMUTE = 248
EV_SYN, EV_KEY, SYN_REPORT = 0, 1, 0
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501


def find_hidraw():
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        if os.path.basename(os.path.realpath(h + "/device")).startswith(HID_ID):
            return "/dev/" + os.path.basename(h)
    sys.exit(f"keyboard {HID_ID} hidraw node not found")


def make_uinput():
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    fcntl.ioctl(fd, UI_SET_KEYBIT, KEY_MICMUTE)
    name = b"OmniBook X16 mic-mute key"
    # struct uinput_setup: input_id {bustype, vendor, product, version}, name[80], ff_effects_max
    setup = struct.pack("HHHH80sI", 0x18, 0x0416, 0xC300, 1, name, 0)
    fcntl.ioctl(fd, UI_DEV_SETUP, setup)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    return fd


def emit(fd, value):
    # struct input_event on 64-bit: timeval (2 x long), type, code, value
    os.write(fd, struct.pack("qqHHi", 0, 0, EV_KEY, KEY_MICMUTE, value)
                 + struct.pack("qqHHi", 0, 0, EV_SYN, SYN_REPORT, 0))


def main():
    dev = find_hidraw()
    ui = make_uinput()
    print(f"watching {dev} for mic-mute (usage 0x{MICMUTE_USAGE:04x})", flush=True)
    down = False
    with open(dev, "rb", buffering=0) as f:
        while True:
            r = f.read(64)
            if not r:
                return 1
            if r[0] != 0x08 or len(r) < 15:
                continue
            slots = struct.unpack_from("<6H", r, 3)
            now = MICMUTE_USAGE in slots
            if now != down:
                emit(ui, 1 if now else 0)
                down = now


if __name__ == "__main__":
    sys.exit(main())
