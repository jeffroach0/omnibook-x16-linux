# Face login with the IR camera (Howdy)

The webcam (HP True Vision FHD, USB `30c9:00d9`) has a second UVC function, **HP IR Camera**, the
camera Windows Hello uses. In DT mode it shows up as `/dev/video2` (`/dev/video3` is its metadata node)
and works without any extra driver. The IR emitter fires on its own: frames alternate between lit
(clear grayscale image) and unlit (black), so `linux-enable-ir-emitter` is **not** needed.

Quick test (no extra packages, GStreamer is installed by default):

    gst-launch-1.0 -q v4l2src device=/dev/video2 num-buffers=30 ! videoconvert ! \
      pngenc snapshot=false ! multifilesink location=ir-%02d.png

The frames are 400x400, 8-bit grayscale. Every other one should show your face lit by the IR LEDs.

[Howdy](https://github.com/boltgolt/howdy) uses this camera for face login. It was tested for
`sudo`, the GNOME lock screen and the GDM login screen.

> **Security:** Howdy is a convenience feature, not strong authentication (its own documentation
> says so). Your password keeps working: if Howdy does not recognise you within 4 seconds, you get the
> normal password prompt.

## Why Howdy 3.0 from source

- The PPA (`ppa:boltgolt/howdy`) only has Howdy 2.6.1 from 2020. The package is `Architecture: all`, so it
  installs on arm64, but its install script runs `pip` on the system Python, which Ubuntu blocks since
  23.04 (PEP 668, [issue #812](https://github.com/boltgolt/howdy/issues/812)). The newest Ubuntu release
  in the PPA is 25.10.
- Howdy 3.0 (the `master` branch, no tagged release yet) builds with meson, has a native C++ PAM module
  (no `libpam-python`) and lets you choose the Python interpreter. That allows dlib to live in its own
  virtual environment instead of the system Python.

Tested with Howdy `master` at commit `d3ab993` (June 22, 2025), Python 3.14, dlib 20.0.1, OpenCV 4.10.

## Install

1. Build dependencies (all in the Ubuntu 26.10 archive):

       sudo apt install meson ninja-build libinih-dev libevdev-dev libpam0g-dev cmake \
         libopencv-dev python3-opencv

2. A root-owned virtual environment for dlib. It must be root-owned: the PAM module runs Howdy's
   Python as root at every login. `--system-site-packages` reuses numpy and OpenCV from apt.
   dlib is compiled from source (5-20 minutes):

       sudo python3 -m venv --system-site-packages /opt/howdy-venv
       sudo /opt/howdy-venv/bin/pip install dlib

3. Give the IR camera a fixed name. Do not use `/dev/v4l/by-path/...`: on this laptop the USB
   controller numbers in those names (`xhci-hcd.N`) change from boot to boot, and Howdy then cannot find
   the camera. The IR camera also has no `/dev/v4l/by-id/` link. The udev rule
   [`99-omnibook-ir-camera.rules`](99-omnibook-ir-camera.rules) matches the camera by name and creates
   `/dev/ir-camera`:

       sudo cp 99-omnibook-ir-camera.rules /etc/udev/rules.d/
       sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=video4linux
       ls -l /dev/ir-camera     # -> video2

4. Build Howdy. The interpreter path is compiled into the PAM module, so the venv must exist first.
   Set the camera in the config before installing:

       git clone https://github.com/boltgolt/howdy.git && cd howdy
       sed -i 's#^device_path = none#device_path = /dev/ir-camera#' howdy/src/config.ini
       meson setup build -Dpython_path=/opt/howdy-venv/bin/python3
       meson compile -C build
       sudo meson install -C build --no-rebuild

   Everything goes under `/usr/local` (PAM module: `/usr/local/lib/aarch64-linux-gnu/security/pam_howdy.so`,
   config: `/usr/local/etc/howdy/config.ini`). `install_pam_config` is off by default, so nothing in
   `/etc/pam.d` changes yet.

5. Download the dlib models. The script saves into the current directory:

       cd /usr/local/share/dlib-data && sudo ./install.sh

6. Add your face and test the same check PAM will run (exit code 0 = recognised, 11 = timeout):

       sudo howdy add
       sudo /opt/howdy-venv/bin/python3 /usr/local/lib/aarch64-linux-gnu/howdy/compare.py $USER; echo $?

   Run it once while looking away too: it must not return 0.

## Enable it

Back up `/etc/pam.d` and keep a root shell (`sudo -i`) open in another terminal while testing.

Add this line just above `@include common-auth`:

    auth    sufficient   /usr/local/lib/aarch64-linux-gnu/security/pam_howdy.so

- `/etc/pam.d/sudo` for `sudo`
- `/etc/pam.d/gdm-password` for both the GNOME lock screen and the GDM login screen

For example:

    sudo sed -i 's#^@include common-auth#auth    sufficient   /usr/local/lib/aarch64-linux-gnu/security/pam_howdy.so\n@include common-auth#' /etc/pam.d/sudo

Test `sudo` with `sudo -k; sudo echo ok` (looking at the screen, then looking away), and the lock
screen with Super+L.

## Notes

- **Login keyring:** logging in at GDM by face leaves the GNOME login keyring locked, so the first app
  that needs a saved password (Chrome, for example) asks for it once. Unlocking the lock screen by face
  is fine, because the keyring is already open.
- The journal shows `pam_howdy: Failed to read files from glob: 3` at every attempt in DT mode. Howdy
  looks for the lid state in `/proc/acpi/button/lid/*/state`, which does not exist without ACPI. It is
  harmless (the `abort_if_lid_closed` option just cannot work).
- If Howdy cannot open the camera (for example in the normal ACPI boot, if the camera is missing there), it logs
  "could not find a camera device" and falls back to the password.
- `sudo howdy test` opens an OpenCV window, which usually fails under `sudo` on Wayland. The
  `compare.py` command above tests the same thing.

## Remove

    sudo cp <backup>/sudo /etc/pam.d/sudo
    sudo cp <backup>/gdm-password /etc/pam.d/gdm-password
    cd howdy && sudo ninja -C build uninstall
    sudo rm -rf /opt/howdy-venv /usr/local/share/dlib-data /usr/local/etc/howdy
    sudo rm /etc/udev/rules.d/99-omnibook-ir-camera.rules
