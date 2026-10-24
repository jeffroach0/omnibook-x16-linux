# Findings: what was wrong and how it was fixed

These notes come from about 25 test boots on one HP OmniBook X 16-cp1xxx (board 8F46), October 2026, kernel
7.3.0-21-qcom-x1e. "VERIFIED" means confirmed by this laptop's ACPI tables or by a test boot. "DONOR" means copied
from the HP EliteBook X G2q device tree without independent proof.

## Starting point

- The SoC is the 12-core Snapdragon X2 Elite, codenamed **Mahua** (`qcom,mahua`), not the 18-core Glymur.
  A Glymur device tree has 18 CPU nodes, so do not use one directly.
- The DT is `mahua.dtsi` plus the PMIC includes (as in `mahua-crd.dts`), with board wiring from
  `glymur-hp-elitebook-x-g2q.dts`.
- Many pins and addresses were checked against the laptop's own ACPI tables (`acpidump` + `iasl -d`).
  Several resources had to be decoded by hand from raw ACPI buffers.

## Boot and display

**Black screen a few seconds after boot (UEFI framebuffer).** The kernel's `rpmhpd` power-domain driver keeps
every power rail at maximum until its `sync_state()`. Then it drops the rails that no driver voted for. With the
display driver off, nothing voted for the display rails (MMCX/MXC), so the display engine lost power. Neither
`pd_ignore_unused` nor `clk_ignore_unused` prevents this.
*Fix:* a `simple-framebuffer` node under `/chosen` that names those power domains (and the eDP PHY supplies), so
simpledrm keeps them on. Later the full msm display driver took over, and the node stays as a fallback.

**Display driver.** `mdss_dp3` (eDP) with the generic `samsung,atna33xc20` panel driver works on this
Samsung OLED (product 0x4214), including DP-AUX backlight control. Enable GPIO 18 and panel power GPIO 70 (DONOR)
are now verified by behaviour.

**Black screen on wake (about 1 in 20).** When the panel powers back on, link training sometimes fails at the
channel-equalization step. The msm driver then falls back from 2 lanes to 1 lane and trains that, but the panel's
maximum (2 lanes at HBR) is exactly what 1920x1200@60 needs, so the 1-lane link shows nothing. The next off/on
recovered every time. *Fix (local patch):* retry at the original rate and lane count when the fallback link is too
slow for the mode. See [display/README.md](../display/README.md).

## GPU

`glymur.dtsi` leaves the GPU nodes enabled, so enabling the display also brought up the Adreno GPU. GNOME then
rendered on it, and the screen was badly corrupted (blocks, diagonal half-screens, flickering bands).

- No GPU faults in the kernel log, and screenshots of static frames were clean. That pointed at rendering, not
  the display hardware.
- Mahua's GPU has 3 slices (Mesa: chip 0x44070031, "X2-85"), but kernel 7.3 reports the 4-slice GMEM size.
  Mesa therefore plans tiles in GMEM that does not exist. linux-next has a fix ("report the active share").
- *Workaround:* `FD_MESA_DEBUG=sysmem` (OpenGL) and `TU_DEBUG=sysmem` (Vulkan) make Mesa skip GMEM.
  `noubwc` is not needed, and it made WebKit worse.
- WebKitGTK's GPU raster (Skia) still caused real GPU page faults and hangs.
  `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` fixes it.
- Chrome's default ANGLE-on-OpenGL path faulted the GPU even with `sysmem`. ANGLE on Vulkan works.
- *Fix (Oct 22):* on linux-arm-msm, Akhil P Oommen pointed to the series "drm/msm: Mahua GPU support" v1.
  It gives Mahua its own catalog entry (chip ID 0x44060000, GMEM 15.75 MB = 3/4 of Glymur's). Patch 3 (driver)
  and patch 5 (`mahua.dtsi`) were applied, with `msm.ko` built out of tree. The driver then reports
  GMEM_SIZE 0xfc0000. Released Mesa (up to 26.2.5) does not know chip ID 0x44060030, so a local shim reports it
  as Glymur's 3-slice X2-85 (0x44070031), which Mesa main treats identically.
  Result: gnome-shell, turnip (Ptyxis) and WebKitGTK GPU raster (GNOME Help) render cleanly with none of the
  workaround variables, and the kernel log shows no GPU faults. Before the patch the same WebKit test caused
  GPU page faults and hangs. Still clean after a longer session of normal use (all windows, no anomalies).

## Touchscreen

- ACPI device TSC1 (ELAN2513) is enabled on this board (its `_STA` checks `\_SB.SKID`, which is 1). Its `_CRS`,
  decoded by hand, gives I2C9 (QUP_1_SE_0, base `0x00a80000` = DT `i2c8`), address 0x10, 400 kHz, HID descriptor
  address 1, and a level, active-low interrupt on GPIO 51. That matches the EliteBook X G2q donor node exactly.
- With `&i2c8` enabled and a `hid-over-i2c` node, the panel probes as `04F3:44BF` (hid-multitouch) and touch works.
  It needs no supply in the DT ("using dummy regulator" is harmless).

## DisplayPort over USB-C

- `mdss_dp0` (left back port) and `mdss_dp1` (left front port) enabled as in the EliteBook X G2q donor. `glymur.dtsi`
  already connects them to the USB-C QMP PHYs, and pmic-glink (already present for USB) reports hot-plug.
- Tested with a USB-C hub with an HDMI output (Parade PS176 DP-to-HDMI converter) and a 1080p monitor. The same
  hub and monitor work in Windows. Both ports give a picture.
- At the default link rates, Linux picked HBR2 (5.4 Gbps) on 2 lanes. AUX, EDID and link training all succeeded,
  but the monitor said "No signal". Timing the vblank interrupts showed the DP stream running at **exactly 30 Hz**
  for a 60 Hz mode, so the display timing ran at half the pixel clock the stream header promised.
- *Workaround:* cap `link-frequencies` at HBR (2.7 Gbps). Then the stream runs at 60.000 Hz and the picture is fine.
  2 lanes at HBR is enough for 1080p60, not for 1440p60 or 4K60.
- My first guess was the VCO divider in `qmp_v8_configure_dp_clocks()` (`phy-qcom-qmp-combo.c`). That was wrong: the
  real fix is Qualcomm's series "phy: qualcomm: qmp-combo: update DP PHY PLL programming on Glymur" v5
  (https://lore.kernel.org/linux-arm-msm/20261001-glymur-phy-v3-v5-0-3848c2615d5a@oss.qualcomm.com/), which
  reworks the DP PHY PLL/init tables and removes the VCO_DIV programming altogether.
- **With that series** (11 patches on the 7.3 `phy-qcom-qmp-combo.c`, built out of tree; the module probes from the
  initramfs, so the initramfs must be rebuilt) and the `link-frequencies` cap removed: HBR2 on 2 lanes, sharp
  picture, DP stream measured at 60.000 Hz, DPCD lane status `77 00 81`. Works in both plug orientations. Plain
  USB 3 on the patched PHY is fine. Front port too: HBR2 on 2 lanes, 60.000 Hz, both lanes locked, hub USB 3
  stable, in both plug orientations (two plug-ins so far).
- Seen with the series on the back port, intermittent, cause unknown (PHY, hub or cable): one of four hub plug-ins gave no picture
  (DPCD lane status `00 00 80`, no clock recovery; replugging fixed it), and on three of four plug-ins the hub's
  USB 3 side kept re-enumerating while DP was running (stopped when HDMI was unplugged).
- The DTS in this repo keeps the HBR cap, so it works with the stock driver. Remove it only together with the series.

## USB

- USB-C (`usb_0` left back, `usb_1` left front): host mode with the smb2370 eUSB2 repeaters (DONOR) worked at once.
  SuperSpeed only worked in one plug orientation until **pmic-glink** was added.
- **pmic-glink on Glymur/Mahua talks to the SoCCP, not the ADSP.** The SoCCP is already running when UEFI hands
  over, so it needs no firmware from Windows. pmic-glink also brings battery status and USB-C charging information.
- USB-A (`usb_2`, right side): ACPI shows this port as USB 3 Standard-A. A guessed smb2370 repeater at SPMI SID 0xb
  does not exist (probe fails with -5). Without any repeater node, both USB 3 and USB 2 work, because UEFI leaves
  the repeater set up.
- USB-A QMP PHY: this port has no Type-C orientation or mode switch, so the DTS deletes `mode-switch` and
  `orientation-switch` from `usb_2_qmpphy`. Without static `data-lanes` the driver then prints "unable to
  determine orientation & mode from data-lanes" (27 times per boot here) and falls back to its default. Adding a
  `port@0` endpoint with `data-lanes = <1 0>` (USB 3, normal orientation) puts the PHY in USB 3 only mode and
  the warning goes away. Tested Oct 24 with the upstream DTS: USB 3 stick at 5000M and a low-speed USB 2 mouse
  both work. (Found by the Sashiko review bot on the upstream patch.)
- Webcam: on the internal USB 2 controller `usb_hs` (HP True Vision FHD, `30c9:00d9`, RGB + IR).

## Wi-Fi

- QCC2072 on `pcie4`. ACPI has no power GPIOs for it. It is modelled as a `pcie-m2-e-connector` (like the
  Zenbook A16), with a 3.3 V regulator on GPIO 94 and W_DISABLE on GPIO 117/116 (DONOR, all verified by behaviour).
- The chip reports board ID `0xff`, so ath12k falls back to `board.bin`. The right data is embedded in Windows'
  `bdwlan_qcc2072_1p0_ncm820A.elf` (offset 1024, 123600 bytes on the tested driver version).

## Bluetooth

QCC2072 Bluetooth is not supported by kernel 7.3, and it did not work in ACPI mode either. With the unmerged
upstream patches (see `bluetooth/`), it works over `uart14`, including pairing.
The firmware is linux-firmware's `ornbtfw11.tlv` / `ornnv11.bin`. The board-specific `ornnv11.b17` does not exist
yet, and the driver falls back to the generic file.

Audio over Bluetooth (PipeWire + WirePlumber, Pixel Buds Pro 2): A2DP playback with the Opus codec works. The
earbud microphone works in A2DP duplex mode (source `bluez_input.<address>`) and in HFP headset mode (source
`bluez_input.<address with underscores>.0`). Both test recordings had normal speech levels. Note that
PipeWire node names use underscores in the address (`bluez_output.XX_XX_XX_XX_XX_XX.1`); a `pw-play --target` with a
wrong name silently falls back to the default output. Once, after switching to HFP and back, WirePlumber
logged `Acquire ... returned error: org.bluez.Error.Failed` and the A2DP profiles vanished until the earbuds
were reconnected.

## DSPs

The ADSP and CDSP need the OEM-signed firmware from the Windows driver store (`qcadsp8480.mbn`, `qccdsp8480.mbn`).
linux-firmware's generic Glymur files are signed differently. The DT points `firmware-name` at
`qcom/mahua/hp/omnibook-x16/`.

## Audio

- Speaker wiring is not in ACPI. The DSDT only describes the headphone jack, as a SoundWire SDCA device.
  The amp reset pins were checked through the Windows audio driver's ACPI resources: TLMM 204/205 = LPASS pins
  12/13, the same as the reference boards.
- The `swr3` amps never answered. A note from early on: the kernel message "soundwire sdw:4:... no matching ACPI
  device found" is printed when Linux creates the device from the DT. It does **not** mean the device answered on
  the bus. Several theories (runtime PM clock stop, the reset pulse) were tested and ruled out before it was clear
  that the laptop simply has two speakers.
- See `audio/README.md` for the UCM and WirePlumber files.

## Suspend

- `/sys/power/mem_sleep` offers `deep`, but the firmware refuses PSCI SYSTEM_SUSPEND (`EOPNOTSUPP`), so only
  **s2idle** works. Windows uses Modern Standby (s2idle-like) on this laptop too.
- The Wi-Fi card's PCIe WAKE# (GPIO 148) woke the system at once. Disabling wakeup on the root port
  (`0004:00:00.0`) fixes that. Wi-Fi still reconnects after resume.
- The webcam's USB controller (`usb_hs`, `a200000.usb`) crashes on resume (SMMU context fault, "HC died"), and
  every later suspend then fails. Unbinding it before sleep and binding it after resume avoids that.
- Real fix: Qualcomm's patch that lets the USB power domains keep their state (retention) instead of switching off
  (`gcc-glymur`, [lore](https://lore.kernel.org/all/20261016-glymur-usb-ret-on-v1-1-1790a523fd9c@oss.qualcomm.com/)).
  Built as an out-of-tree `gcc-glymur.ko`, the webcam survives resume without the unbind (tested several times).
- `suspend/omnibook-x16-dt` sets s2idle and disables the Wi-Fi wakeup. It unbinds the webcam controller only when
  the patched `gcc-glymur` is not loaded (it compares the module's `srcversion`; set yours in the script).

## CPU frequency scaling

- With Ubuntu's kernel, `scmi_cpufreq` gets no answer from the firmware for SCMI performance requests (protocol 0x13):
  "timed out in resp", probe -110. The CPUs stay at the clock UEFI set (~3.5 / 3.9 GHz). ACPI has no CPU performance
  control either.
- The SCMI channel itself works (base protocol queries answer long after boot), and the firmware lists protocol 0x13,
  but ignores every perf message. Loading `qcom_cpucp_mbox` and `scmi_cpufreq` from the initramfs (about 1 s into
  boot) does not help.
- Fix (Konrad Dybcio: "Timing."): build `CONFIG_QCOM_CPUCP_MBOX` and `CONFIG_ARM_SCMI_CPUFREQ` into the kernel
  (`=y`). Then the firmware answers: two policies, 355 MHz - 3.42 GHz (CPUs 0-5) and 355 MHz - 4.03 GHz (CPUs 6-11),
  driver `scmi`, governor `ondemand`. Works after s2idle resume too. Build steps: [cpufreq/README.md](../cpufreq/README.md).

## ACPI mode: kernel log flood

Not a device tree issue, but it affects the normal (ACPI) boot of the same install.
- In ACPI mode the `acpi_tad` driver binds the ACPI time device `\_SB.PRTC`. Its `_GRT`/`_SRT` methods use a
  GenericSerialBus region (`ROP1`) that Linux has no handler for, so every clock read and write fails.
- Once NTP sets the clock (chrony `rtcsync`), the kernel keeps retrying the write: about 120 "ACPI Error" lines per
  second for the whole boot (millions of lines, gigabytes of `kern.log`/`syslog`/journal).
- Fix: `acpi-mode/blacklist-acpi-tad.conf` in `/etc/modprobe.d/`, plus `acpi-mode/omnibook-no-acpi-tad.service`
  (enable it) to unload the driver early if an initramfs loaded it anyway. Tested in an ACPI boot: no `PRTC` errors.
  There is no RTC in ACPI mode then; the time comes from NTP. The driver never loads in DT mode.

## Still open

- **RTC:** `rtc-pm8xxx` reads its offset from the UEFI variable `RTCInfo`, which this laptop does not have, so
  probe failed with -2. Without `qcom,uefi-rtc-info` (Konrad Dybcio's suggestion) the driver probes and `rtc0`
  is read-only, but it reads the raw PMIC counter (~190 days after 1970 on this laptop), not the real time.
  Where Windows keeps the real offset is unknown. The time is fine once NTP syncs.
- **Headphone jack:** no Linux driver for the Qualcomm SDCA codec.
- **DisplayPort over USB-C above HBR:** see [DisplayPort over USB-C](#displayport-over-usb-c).

## Things that are easy to get wrong

- `DMI:` in the kernel log does not mean ACPI mode; arm64 prints it in DT mode too. Check `Machine model:` and
  `ACPI: Interpreter disabled.` instead.
- `qcom-firmware-extract` does not know this laptop (it matches a fixed model list and X1E file names). Copy the
  files by hand.
- In `/sys/kernel/debug/gpio` for LPASS pins, the number after `in`/`out` is the pin *function*, not its level.
- With the clock starting at a fake date on every boot (no RTC), journald may delete a test boot's log.
  `/var/log/kern.log` from rsyslog kept it.
- `GICv3: SPI 4115 out of range (use ESPI?)` at boot is harmless. It is the lid switch: GPIO 92 maps to PDC pin 182,
  which `glymur.dtsi` (`qcom,pdc-ranges <171 4104 36>`) routes to interrupt 4104 + 11 = 4115, in the GIC's extended
  SPI range. The PDC driver passes it as a plain SPI, so the GIC driver warns (once), but it still works out the
  correct interrupt and the lid works. Not a board DTS issue; any fix belongs in `qcom-pdc.c` or `glymur.dtsi`.
