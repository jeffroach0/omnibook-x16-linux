# Mute / mic-mute key LEDs and the mic-mute key (DT mode)

In device tree mode, two things on the keyboard don't work out of the box:

1. The orange **mute** and **mic-mute** LEDs never light.
2. The **mic-mute** key does nothing (the mute key works).

The files here fix both. Tested Nov 6, 2026 on kernel 7.3.0-21-qcom-x1e, GNOME, PipeWire.

## Why the LEDs don't light

The LEDs are not keyboard LEDs. HP's embedded controller (EC) drives them. Windows sets
them through HP's mute LED service, which calls an ACPI method (`\_SB.WMID.SMLS` in ssdt3).
That method talks to the EC over I2C:

- EC: I2C address **0x76** on the QUP I2C at **0xa84000** (`&i2c9` in the DT, `\_SB.IC10` in ACPI), 400 kHz.
- Mailbox: wait until register `0xEF` reads `0x00`, write `{main, sub}` to register `0xED`,
  then wait until `0xEF` reads `0xE0` (done).
- Commands: `{0x01, 0x84}` first, then speaker LED `{0x06, 0x08}` off / `{0x06, 0x88}` on,
  mic LED `{0x06, 0x09}` off / `{0x06, 0x89}` on.

The DTS enables `&i2c9` with no child node. `omnibook-ec-leds.py` runs as a systemd **user**
service. It watches PipeWire (`pw-dump --monitor`), reads the mute state of the default output
and input with `wpctl`, and sends the LED command when it changes. When the service stops
(logout, shutdown) it switches both LEDs off. The EC keeps its state across reboots, and
Windows' HP service only writes on a change, so a lit LED would otherwise stay on in Windows.

Only the commands above are sent. Don't experiment with other EC commands: one test
command (`{0xBD, 0x01}`) left the keyboard unable to type and confused the media keys
in Windows until Fn-lock (Fn+Shift) was toggled.

## Why the mic-mute key does nothing

The keyboard (HID over I2C, `0416:C300`) sends mic-mute as Keyboard-page usage **0x8000**.
Its report descriptor declares usages 0 to 0x8000, but the kernel only keeps the first
`HID_MAX_USAGES` (12288). The kernel log shows `ignoring exceeding usage max` at boot, and
the key press is silently dropped. A hwdb remap (`KEYBOARD_KEY_78000=micmute`) does not work:
udev fails with `EVIOCSKEYCODE ... Invalid argument`, because the kernel has no slot for that usage.

`omnibook-micmute-key.py` runs as a root system service. It reads the keyboard's `hidraw`
node (read-only), looks for 0x8000 in the key slots of input report 0x08, and presses
`KEY_MICMUTE` on a small virtual keyboard (uinput). GNOME then shows its usual pop-up and mutes
the microphone, and the LED service lights the LED. It ignores and never stores other keys.
A proper kernel fix would be a HID-BPF report descriptor fixup or a HID quirk.

## Files

| File | Install to | What it does |
|---|---|---|
| `70-omnibook-ec.rules` | `/etc/udev/rules.d/` | `/dev/omnibook-ec` symlink to the EC's I2C bus (its number changes per boot) and access for the logged-in user |
| `omnibook-ec-leds.py` | `~/.local/bin/omnibook-ec-leds` | LED sync (user service) |
| `omnibook-ec-leds.service` | `~/.config/systemd/user/` | starts it at login; skipped when `/dev/omnibook-ec` is missing (ACPI mode) |
| `omnibook-micmute-key.py` | `/usr/local/sbin/omnibook-micmute-key` | mic-mute key (root) |
| `omnibook-micmute-key.service` | `/etc/systemd/system/` | starts it at boot, DT mode only |

Note: the udev rule gives the logged-in user raw access to the EC's I2C bus, not only the LEDs.
That is fine on a single-user laptop. On a shared machine, use a group instead of `uaccess`.

## Install

Needs a DTB with `&i2c9` enabled (the DTS in this repo has it) and the `i2c-dev` module
(Ubuntu loads it through fwupd's `/usr/lib/modules-load.d/fwupd-i2c.conf`).

    sudo cp 70-omnibook-ec.rules /etc/udev/rules.d/
    sudo udevadm control --reload
    sudo udevadm trigger --subsystem-match=i2c-dev

    install -D -m 755 omnibook-ec-leds.py ~/.local/bin/omnibook-ec-leds
    install -D -m 644 omnibook-ec-leds.service ~/.config/systemd/user/omnibook-ec-leds.service
    systemctl --user daemon-reload
    systemctl --user enable --now omnibook-ec-leds.service

    sudo install -m 755 omnibook-micmute-key.py /usr/local/sbin/omnibook-micmute-key
    sudo cp omnibook-micmute-key.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now omnibook-micmute-key.service

Check: `journalctl --user -u omnibook-ec-leds` logs each LED change.

## If Windows keys act up afterwards

The EC keeps its state across reboots and OS switches. If the mute or volume keys stop working in
Windows, or an LED stays lit: press **Fn+Shift** twice (Fn-lock on and off), or do a full shutdown
instead of a restart. Fn-lock is Fn+Shift on this model. There are no keyboard settings in the BIOS.
