# CPU frequency scaling

The firmware only answers SCMI performance requests (protocol 0x13) if the CPUCP mailbox driver is
up very early in boot. Ubuntu's 7.3 kernel builds it as a module (`CONFIG_QCOM_CPUCP_MBOX=m`), which
loads about 1 s into boot from the initramfs, and by then perf requests time out:

    scmi-cpufreq: ... timed out in resp
    Failed to query supported version for protocol 0x13
    probe ... failed with error -110

Loading the modules earlier from the initramfs does not help. Building them into the kernel does
(Konrad Dybcio's suggestion; his explanation: "Timing.").

## Kernel config change

Start from the running kernel's config (`/boot/config-7.3.0-21-qcom-x1e`) and set:

    CONFIG_QCOM_CPUCP_MBOX=y
    CONFIG_ARM_SCMI_CPUFREQ=y
    CONFIG_MODULE_ALLOW_BTF_MISMATCH=y

The last one is needed to keep using the stock Ubuntu modules: without it the kernel refuses to
load modules whose BTF was generated against the stock image.

## Building only the kernel image

Use the exact source of the installed kernel (here `linux-qcom-x1e` 7.3.0-21.21) and keep the same
release string, so the existing `/lib/modules/7.3.0-21-qcom-x1e` (and any patched modules in
`updates/`) and the existing initramfs keep working:

    mkdir build && cp /boot/config-7.3.0-21-qcom-x1e build/.config
    scripts/config --file build/.config -e QCOM_CPUCP_MBOX -e ARM_SCMI_CPUFREQ -e MODULE_ALLOW_BTF_MISMATCH
    make O=build ARCH=arm64 CC=aarch64-linux-gnu-gcc HOSTCC=aarch64-linux-gnu-gcc \
      KERNELRELEASE=7.3.0-21-qcom-x1e KBUILD_BUILD_VERSION=21 olddefconfig
    make O=build ARCH=arm64 CC=aarch64-linux-gnu-gcc HOSTCC=aarch64-linux-gnu-gcc \
      KERNELRELEASE=7.3.0-21-qcom-x1e KBUILD_BUILD_VERSION=21 -j12 vmlinuz.efi

The resulting `.config` should differ from the stock one in exactly those three options. `gawk`
is needed (it is in the kernel's Build-Depends). Use the same compiler and Rust/bindgen/pahole
versions as the stock kernel (here gcc 15.3, rustc 1.97.1, bindgen 0.72.1, pahole 1.31). Before installing, check that the exported symbol CRCs match the stock kernel:
every `vmlinux` line in `build/Module.symvers` should be identical to the `vmlinux` lines in
`/usr/src/linux-headers-7.3.0-21-qcom-x1e/Module.symvers`.

Install `build/arch/arm64/boot/vmlinuz.efi` as a separate file (for example
`/boot/vmlinuz-7.3.0-21-qcom-x1e-cpucp`) and add a GRUB entry for it next to the stock one; keep
the stock kernel and entry as a fallback. The kernel is unsigned: this only works with Secure Boot
off, and stock modules then log "signature and/or required key missing - tainting kernel" (harmless).

## Result

Two policies with the `scmi` driver (governor `ondemand`):

| CPUs | Range |
|---|---|
| 0-5 | 355 MHz - 3.42 GHz (19 steps) |
| 6-11 | 355 MHz - 4.03 GHz (18 steps) |

The clocks drop to 355-900 MHz at idle and reach the maximum under load, also after s2idle resume.
Harmless log lines: `Failed to get FC for protocol 13 ... Using regular messaging` (no fast channels),
and `qcom_cpucp_mbox: module is already loaded` (the stock module file is still in `/lib/modules`).

Also tested on this kernel: s2idle suspend/resume (scaling keeps working afterwards), GPU, Wi-Fi,
Bluetooth, webcam, DisplayPort, and all the patched out-of-tree modules from this repo.

Battery draw at idle (screen on, 10 minutes untouched) was the same as with the stock kernel,
about 3.2 W: idle CPUs sit in their idle states, so the clock barely matters there. A light-load
comparison has not been done yet.

## Caveats

- This kernel matches one exact kernel version. If the kernel package is upgraded, rebuild it for
  the new version (the exported symbol CRCs must match that version's modules).
- It is not managed by the package manager: kernel updates will not touch or replace it.
- Undo: delete the GRUB entry and the kernel file; the stock kernel is unchanged.
