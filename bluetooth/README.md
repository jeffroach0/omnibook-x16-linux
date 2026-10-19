# Bluetooth (QCC2072) on kernel 7.3

The Wi-Fi/Bluetooth card is a Qualcomm QCC2072. Wi-Fi works with the stock kernel. Bluetooth does not:
kernel 7.3 knows neither the QCC2072 Bluetooth chip (`btqca`, `hci_qca`) nor its PCI ID in the M.2 power
sequencing driver (`pwrseq-pcie-m2`). Bluetooth did not work in ACPI mode either.

The fix uses two patches from an upstream series that has not been merged yet
("rb3-industrial-bt-uart" v2, July 2026):

- `patches/0002-Bluetooth-qca-add-QCC2072-support.patch`
- `patches/0003-pwrseq-pcie-m2-add-QCC2072.patch`

They did not apply cleanly to Ubuntu's 7.3 source; two hunks had to be fixed by hand.
`qcc2072-applied-7.3.diff` is the result: the exact change as applied to the 7.3 source.

## How it fits together

- The DT describes the card as an M.2 E-key slot (`pcie-m2-e-connector`), with its UART on `uart14`
  (`serial1` alias). This laptop's ACPI tables confirm: `QCOM0F6B` on UART at 0x00a98000, 115200 baud, RTS/CTS.
- Once the Wi-Fi PCI function (`17cb:1112`) appears, the patched `pwrseq-pcie-m2` creates a
  `qcom,qcc2072-bt` serial device, and the patched `hci_qca`/`btqca` set up the chip.
- Firmware comes from linux-firmware (already in Ubuntu): `qca/ornbtfw11.tlv`, `qca/ornnv11.bin`,
  `qca/ornbcscal11.bin`. The Windows Bluetooth files are a different format and are not used.

## Build (out of tree, against the installed kernel headers)

1. Get the kernel source (`apt-get source --only-source linux-qcom-x1e`). Copy `drivers/bluetooth/` and
   `drivers/power/sequencing/pwrseq-pcie-m2.c` into a work directory, keeping the same paths.
2. Apply `qcc2072-applied-7.3.diff` there (`patch -p1 < qcc2072-applied-7.3.diff`).
3. Replace the Makefiles with the small Kbuild files from `build/`, so only the needed modules are built:
   `build/Kbuild.bluetooth` -> `drivers/bluetooth/Kbuild`, `build/Kbuild.pwrseq` -> `drivers/power/sequencing/Kbuild`.
4. Build:

       make -C /lib/modules/$(uname -r)/build M=$PWD/drivers/bluetooth modules
       make -C /lib/modules/$(uname -r)/build M=$PWD/drivers/power/sequencing modules

## Install

    sudo mkdir -p /lib/modules/$(uname -r)/updates/qcc2072-bt
    sudo cp drivers/bluetooth/btqca.ko drivers/bluetooth/hci_uart.ko \
            drivers/power/sequencing/pwrseq-pcie-m2.ko /lib/modules/$(uname -r)/updates/qcc2072-bt/
    sudo depmod -a

`pwrseq-pcie-m2` is loaded from the initramfs, so the initramfs needs the patched module too. To leave the
normal boot untouched, build a separate initramfs just for the DT test entry (Ubuntu Concept uses dracut):

    sudo dracut --force /boot/dtb-test/initrd.img-$(uname -r)-dt-test

Then point the `initrd` line of the DT test entry at that file.

Check: `bluetoothctl list` shows a controller, and the kernel log shows `hci0: setting up qcc2072` and
`QCA setup on UART is completed`.

To undo: delete `updates/qcc2072-bt/` and run `sudo depmod -a`.

These modules only match the exact kernel they were built for. Rebuild them after any kernel update.
