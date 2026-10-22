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
  hub and monitor work in Windows. Picture tested on the back port; the front port detects the monitor too.
- At the default link rates, Linux picked HBR2 (5.4 Gbps) on 2 lanes. AUX, EDID and link training all succeeded,
  but the monitor said "No signal". Timing the vblank interrupts showed the DP stream running at **exactly 30 Hz**
  for a 60 Hz mode, so the display timing ran at half the pixel clock the stream header promised.
- *Workaround:* cap `link-frequencies` at HBR (2.7 Gbps). Then the stream runs at 60.000 Hz and the picture is fine.
  2 lanes at HBR is enough for 1080p60, not for 1440p60 or 4K60.
- Likely cause (not yet proven by a patched driver): `qmp_v8_configure_dp_clocks()` in `phy-qcom-qmp-combo.c` uses a
  VCO divider of 0x4 for 5.4 Gbps (0x2 for 2.7 Gbps). The Glymur eDP PHY driver (`phy-qcom-edp.c`) uses 0x2 for
  5.4 Gbps, and the internal eDP panel works at that rate. 8.1 Gbps may be affected too (0x3 vs 0x1); untested.

## USB

- USB-C (`usb_0` left back, `usb_1` left front): host mode with the smb2370 eUSB2 repeaters (DONOR) worked at once.
  SuperSpeed only worked in one plug orientation until **pmic-glink** was added.
- **pmic-glink on Glymur/Mahua talks to the SoCCP, not the ADSP.** The SoCCP is already running when UEFI hands
  over, so it needs no firmware from Windows. pmic-glink also brings battery status and USB-C charging information.
- USB-A (`usb_2`, right side): ACPI shows this port as USB 3 Standard-A. A guessed smb2370 repeater at SPMI SID 0xb
  does not exist (probe fails with -5). Without any repeater node, both USB 3 and USB 2 work, because UEFI leaves
  the repeater set up.
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
- `suspend/omnibook-x16-dt` does all three. Tested with repeated suspends.

## Still open

- **CPU frequency:** `scmi_cpufreq` gets no answer from the firmware for SCMI performance requests (protocol 0x13,
  timeout, -110), even when loaded early. ACPI has no CPU performance control either. The CPUs run at the clock
  UEFI set.
- **RTC:** `rtc-pm8xxx` reads its offset from the UEFI variable `RTCInfo`, which this laptop does not have, so
  probe fails with -2. The time is fine once NTP syncs.
- **Headphone jack:** no Linux driver for the Qualcomm SDCA codec.
- **DisplayPort over USB-C above HBR:** see [DisplayPort over USB-C](#displayport-over-usb-c).
- Minor: `GICv3: SPI 4115 out of range`. Also, the debug UART (`894000.serial`) has no alias. Adding one would let
  interconnect `sync_state()` run and drop bandwidth votes that simpledrm relies on, so it was left alone.

## Things that are easy to get wrong

- `DMI:` in the kernel log does not mean ACPI mode; arm64 prints it in DT mode too. Check `Machine model:` and
  `ACPI: Interpreter disabled.` instead.
- `qcom-firmware-extract` does not know this laptop (it matches a fixed model list and X1E file names). Copy the
  files by hand.
- In `/sys/kernel/debug/gpio` for LPASS pins, the number after `in`/`out` is the pin *function*, not its level.
- With the clock starting at a fake date on every boot (no RTC), journald may delete a test boot's log.
  `/var/log/kern.log` from rsyslog kept it.
