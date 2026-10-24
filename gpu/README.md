# GPU (Adreno X2-85)

With the stock 7.3 kernel, hardware rendering corrupts the screen. The msm driver reports the
4-slice GMEM size of Glymur's GPU, but Mahua's X2-85 has only 3 slices, so Mesa plans tiles in GMEM
that does not exist.

There are two ways to fix it. Use one of them.

## Option A (recommended): the Mahua GPU patches

Qualcomm's series "drm/msm: Mahua GPU support" v1 (Sept 2026, not merged yet;
[lore](https://lore.kernel.org/all/20260925-mahua-gpu-v1-0-0fa0bfd8d315@oss.qualcomm.com/))
adds a catalog entry for the Mahua GPU (chip ID 0x44060000, 15.75 MB GMEM, 3 slices).
Two of its patches are needed here:

| File | Goes into | What it does |
|---|---|---|
| `patches/0003-drm-msm-a8xx-Add-Mahua-GPU-support.patch` | `msm.ko` | New GPU catalog entry |
| `patches/0005-arm64-dts-qcom-mahua-Support-GPU-and-GMU.patch` | `mahua.dtsi` (DTB) | GPU/GMU compatibles that match the new entry |
| `patches/local-mesa-chip-id-shim.diff` | `msm.ko` | **Local, not upstream.** Reports the GPU to Mesa as 0x44070031 |

Why the shim: no released Mesa (26.2.5 or older) knows Mahua's chip ID 0x44060030 yet; only Mesa's
main branch does. Without the shim, Mesa does not recognise the GPU. Mesa's main branch treats both IDs as
the same GPU. Drop the shim once your Mesa knows 0x44060030.

The two parts must be used together. A DTB with patch 5 and a stock `msm.ko` gives no GPU at all
(software rendering). A patched `msm.ko` with an old DTB behaves like stock.

Tested: Ubuntu Concept kernel 7.3.0-21-qcom-x1e, Mesa 26.2.4: gnome-shell (OpenGL), Ptyxis (Vulkan) and
GNOME Help (WebKitGTK GPU raster) are clean, with no GPU faults and none of the Option B variables set.
Google Chrome (arm64 .deb) with the patches: no GPU faults on its default OpenGL path, but small black
blocks still appear now and then, mostly on Chrome's own bookmarks bar. On Vulkan it is clean, so use the
`google-chrome-omnibook` launcher (see Option B) with both options.

### Build `msm.ko` out of tree

You need the kernel source for your kernel version (here `apt-get source --only-source linux-qcom-x1e`)
and the matching headers package. Both patches apply cleanly to the 7.3 `drivers/gpu/drm/msm`.

    KSRC=~/linux-qcom-x1e-7.3.0          # unpacked kernel source
    W=~/msm-build                         # work directory
    mkdir -p $W/drivers/gpu/drm $W/include
    cp -r $KSRC/drivers/gpu/drm/msm $W/drivers/gpu/drm/
    cp $KSRC/drivers/gpu/drm/drm_crtc_internal.h $W/drivers/gpu/drm/   # included as ../../../
    cp -r $KSRC/include/trace $W/include/                              # trace headers
    cd $W
    patch -p1 < .../gpu/patches/0003-drm-msm-a8xx-Add-Mahua-GPU-support.patch
    patch -p1 < .../gpu/patches/local-mesa-chip-id-shim.diff
    cd drivers/gpu/drm/msm
    make -C /lib/modules/$(uname -r)/build M=$PWD KCFLAGS="-I$W/include/trace" -j$(nproc) modules
    strip --strip-debug msm.ko

Check that `modinfo ./msm.ko` shows the same `vermagic` as `modinfo msm`. Then install it so it
takes priority over the stock module:

    sudo mkdir -p /lib/modules/$(uname -r)/updates/mahua-gpu
    sudo cp msm.ko /lib/modules/$(uname -r)/updates/mahua-gpu/
    sudo depmod -a

On this laptop `msm` loads after the root filesystem is mounted, so the initramfs does not need
rebuilding. (If your initramfs does contain `msm`, it must be rebuilt.) To undo: delete the
`updates/mahua-gpu` directory and run `sudo depmod -a`.

### Build the DTB

Apply patch 5 to `arch/arm64/boot/dts/qcom/mahua.dtsi` in the kernel source, then build
`dts/mahua-hp-omnibook-x16.dts` as usual.

### Check that it worked

    modinfo -F filename msm                # .../updates/mahua-gpu/msm.ko
    grep -a 'bound 3d00000.gpu' /var/log/kern.log | tail -1

## Option B: Mesa workaround (no kernel changes)

Add the lines from `environment-additions` to `/etc/environment`, then log out and in.

    FD_MESA_DEBUG=sysmem                 # OpenGL (freedreno): gnome-shell, most apps
    TU_DEBUG=sysmem                      # Vulkan (turnip): GTK4 apps such as Ptyxis
    WEBKIT_SKIA_ENABLE_CPU_RENDERING=1   # WebKitGTK apps (e.g. GNOME Help), which still caused GPU faults

These make Mesa skip GMEM (slower). They only affect the msm GPU driver, which is not used in ACPI mode.
Google Chrome's OpenGL path still faulted the GPU this way. `google-chrome-omnibook` starts Chrome on
Vulkan (`--use-angle=vulkan --enable-features=Vulkan,DefaultANGLEVulkan,VulkanFromANGLE`) in DT mode.
The launcher is also needed with Option A (black blocks on the OpenGL path).

If you switch from Option B to Option A, remove the lines. Note that logging out does not clear them
from the systemd user manager: reboot, or run
`systemctl --user unset-environment FD_MESA_DEBUG TU_DEBUG WEBKIT_SKIA_ENABLE_CPU_RENDERING`.
