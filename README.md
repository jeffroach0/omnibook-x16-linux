# Linux device tree for the HP OmniBook X 16 (Snapdragon X2 Elite)

This is a community device tree (DT) and a set of fixes that run Ubuntu on the
**HP OmniBook X Laptop 16-cp1xxx** (Snapdragon X2 Elite, 12-core "Mahua",
board ID 8F46) **with a device tree instead of ACPI**. In ACPI mode most of the
hardware does not work. With this DT, nearly everything does.

> **Status: experimental.** It was tested on one laptop (October 2026),
> booted as a one-time test entry next to the normal boot entry. It is not
> upstream. Use it at your own risk, and keep your normal boot entry.

## What works

| Hardware | Status | Notes |
|---|---|---|
| NVMe SSD, boot to desktop | ✅ | |
| Internal display (16" Samsung OLED, eDP) | ✅ | msm DRM driver, `samsung,atna33xc20` panel |
| Brightness (keys + slider) | ✅ | DP-AUX backlight |
| GPU (Adreno X2-85, hardware rendering) | ⚠️ works with a workaround | see [GPU](#gpu) |
| Keyboard, touchpad, lid switch, power key | ✅ | |
| Touchscreen (ELAN, I2C) | ✅ | `i2c8`, address 0x10, interrupt GPIO 51 (from the DSDT) |
| Wi-Fi (Qualcomm QCC2072, Wi-Fi 7) | ✅ | needs a board file from Windows, see [Wi-Fi](#wi-fi) |
| Bluetooth (QCC2072) | ⚠️ works with patched modules | not in kernel 7.3, see [Bluetooth](#bluetooth) |
| USB-C ports (both, left side): USB 3, charging, plug orientation | ✅ | via pmic-glink |
| USB-A port (right side), USB 3 + USB 2 | ✅ | |
| Battery status | ✅ | |
| Webcam (HP True Vision FHD, RGB + IR) | ✅ | |
| Speakers (2, stereo) | ✅ | needs UCM + WirePlumber files, see [Audio](#audio) |
| Built-in microphones | ✅ | |
| Audio DSP / compute DSP (ADSP, CDSP) | ✅ | firmware from Windows |
| Suspend (s2idle) | ✅ with a sleep hook | deep sleep is refused by the firmware |
| Headphone jack | ❌ | Qualcomm SoundWire SDCA codec, no Linux driver |
| DisplayPort over USB-C | ❌ | not tried yet |
| CPU frequency scaling | ❌ | firmware does not answer SCMI performance requests; CPUs stay at the clock UEFI set (~3.5 / 3.9 GHz) |
| Real-time clock | ❌ | the PMIC RTC needs a UEFI variable (`RTCInfo`) that this laptop does not have. The time is correct once NTP syncs. |

## Repository layout

| Path | What it is |
|---|---|
| `dts/mahua-hp-omnibook-x16.dts` | The device tree source. Comments mark each part VERIFIED / DONOR / GUESS. |
| `bluetooth/` | Upstream QCC2072 patches (not merged yet), the diff as applied to 7.3, and build files |
| `audio/ucm/` | ALSA UCM profile for the two speakers and the microphones |
| `audio/wireplumber/` | Fixes the stereo channel order of the speakers |
| `gpu/` | Environment variables that work around GPU rendering corruption, and a Chrome launcher |
| `suspend/omnibook-x16-dt` | systemd sleep hook that makes suspend work |
| `grub/40_custom.example` | Example one-shot GRUB test entry |
| `docs/findings.md` | What was found and how each problem was fixed |
| `docs/linux-arm-msm-post-2026-10-21.txt` | Bring-up report and questions sent to the linux-arm-msm mailing list (Oct 21, 2026). Thread with replies: [lore.kernel.org](https://lore.kernel.org/all/CAAnD8Rb4ZZrHFWMJayabioB_8bOHh1mqZ5LCXZz0jTNGMA7UZQ@mail.gmail.com/T/) |
| `CONTRIBUTORS.md` | Who did the work |

## Tested setup

- Ubuntu "Concept" with the `linux-qcom-x1e` kernel **7.3.0-21-qcom-x1e** (Ubuntu Concept PPA).
  The kernel packages were held (`apt-mark hold`) during testing.
- Dual boot with Windows 11. Several firmware files come from the Windows partition.
- Mesa 26.2.4, systemd 261.

## How to use it

These are outlines. Read [docs/findings.md](docs/findings.md) before you start.

### 1. Build the device tree

You need the kernel source that matches your kernel. On Ubuntu, `apt-get source --only-source linux-qcom-x1e`
fetches it. Copy `dts/mahua-hp-omnibook-x16.dts` to `arch/arm64/boot/dts/qcom/` in that source tree, then run
this from the top of the tree:

    cpp -nostdinc -I include -I arch/arm64/boot/dts -I arch/arm64/boot/dts/qcom \
      -undef -x assembler-with-cpp -D__DTS__ \
      arch/arm64/boot/dts/qcom/mahua-hp-omnibook-x16.dts \
    | dtc -@ -I dts -O dtb -o mahua-hp-omnibook-x16.dtb -

`unique_unit_address` warnings are harmless.

### 2. Add a one-shot GRUB entry

Copy the DTB to `/boot/dtb-test/`, then add an entry based on `grub/40_custom.example` to `/etc/grub.d/40_custom`
and run `sudo update-grub`. The important kernel arguments are:

- `devicetree /boot/dtb-test/mahua-hp-omnibook-x16.dtb` loads our DT.
- `stubble.dtb_override=false` stops Ubuntu's stub from replacing it.
- `clk_ignore_unused pd_ignore_unused` keep clocks and power domains the firmware turned on.

Boot it **once** with `sudo grub-reboot '<entry name>'` and `sudo reboot`. If anything goes wrong, hold the power
button for about 10 seconds; the next boot uses your normal entry again.

To check you are really in DT mode: `cat /proc/device-tree/model` should print `HP OmniBook X Laptop 16-cp1xxx`.

### 3. Firmware from Windows

The firmware files are **not** in this repository, because they are copyrighted by HP/Qualcomm. Copy them from
your own Windows partition. Mount it read-only, for example
`sudo mount -t ntfs-3g -o ro /dev/nvme0n1p3 /mnt/win`. All the files are under
`/mnt/win/Windows/System32/DriverStore/FileRepository/`.

| File | Windows driver folder | Install to |
|---|---|---|
| `qcadsp8480.mbn` | `qcsubsys_ext_adsp8480.inf_*` | `/lib/firmware/qcom/mahua/hp/omnibook-x16/` |
| `qccdsp8480.mbn` | `qcnspmcdm8480.inf_*` | `/lib/firmware/qcom/mahua/hp/omnibook-x16/` |
| Wi-Fi board file | `qcwlancol8480.inf_*` (see below) | `/lib/firmware/ath12k/QCC2072/hw1.0/board.bin` |

#### Wi-Fi

The chip reports board ID `0xff`, and linux-firmware's `board-2.bin` has no matching entry, so ath12k falls
back to `board.bin`. The right data is inside Windows' `bdwlan_qcc2072_1p0_ncm820A.elf`, at byte offset 1024,
123600 bytes long:

    cd /lib/firmware/ath12k/QCC2072/hw1.0/
    sudo cp board.bin board.bin.orig 2>/dev/null
    sudo dd if=/mnt/win/.../bdwlan_qcc2072_1p0_ncm820A.elf of=board.bin bs=1 skip=1024 count=123600

(Offset and length were measured on one laptop with one Windows driver version. Check them against your own file.)

### 4. Optional fixes

- **Bluetooth:** see [bluetooth/README.md](bluetooth/README.md).
- **Audio:** see [audio/README.md](audio/README.md).
- **GPU:** add the lines from `gpu/environment-additions` to `/etc/environment`, then log out and in.
  These variables only affect the msm GPU driver, which is not used in ACPI mode, so they are harmless there.
- **Suspend:** `sudo install -m 755 suspend/omnibook-x16-dt /usr/lib/systemd/system-sleep/`.
  The hook does nothing when you are not booted with this DT.

## GPU

Hardware rendering works, but without a workaround the screen shows corruption: garbled blocks, diagonal
half-screens, bands of colour. The cause is very likely the kernel reporting the full 4-slice GMEM size, while
Mahua's GPU has 3 slices. linux-next has a fix that reports the active share; kernel 7.3.0-23 does not have it.
The workaround tells Mesa to bypass GMEM:

    FD_MESA_DEBUG=sysmem                 # OpenGL (freedreno): gnome-shell, most apps
    TU_DEBUG=sysmem                      # Vulkan (turnip): GTK4 apps such as Ptyxis
    WEBKIT_SKIA_ENABLE_CPU_RENDERING=1   # WebKitGTK apps (e.g. GNOME Help), which still caused GPU faults

For Google Chrome, the OpenGL path still faulted the GPU, but Vulkan works. `gpu/google-chrome-omnibook` starts
Chrome with `--use-angle=vulkan --enable-features=Vulkan,DefaultANGLEVulkan,VulkanFromANGLE` when it runs in DT mode.

## Bluetooth

Kernel 7.3 has no QCC2072 Bluetooth support. The upstream patch series (v2, July 2026, not merged as of
October 2026) adds it. Build the patched `btqca`, `hci_uart` and `pwrseq-pcie-m2` modules out of tree, and use
an initramfs that contains them. Details: [bluetooth/README.md](bluetooth/README.md).

## Credits

- The board wiring is based on the upstream `glymur-hp-elitebook-x-g2q.dts` (HP EliteBook X G2q) and
  `mahua-crd.dts`/`mahua.dtsi`, by the Linux kernel arm64/Qualcomm contributors.
- QCC2072 Bluetooth patches (series "rb3-industrial-bt-uart" v2, July 2026): Vivek Sahu, Yepuri Siddu,
  Rahul Samana and Krishna Chaitanya Chundru (Qualcomm), as posted to the kernel mailing lists.
- Investigation, device tree, fixes and write-up: Jeff R together with **Claude Opus 5.5** (Anthropic), working
  in Claude Code. Claude analysed ACPI tables, kernel source and boot logs and drafted the DT and fixes; Jeff ran
  every test boot on the real hardware and confirmed the results.

## Licence

- `dts/`: BSD-3-Clause (as in its SPDX header, like the upstream files it is based on).
- `bluetooth/`: kernel patches, GPL-2.0.
- Everything else (scripts, config files, documentation): MIT, see [LICENSE](LICENSE).
