# Internal display: black screen on wake (eDP link training)

About 1 in 20 times the screen turns back on (after idle blank, unlock or resume), the internal OLED
stays black. The system keeps running; switching to a text console does not help. The next screen
off/on cycle brings it back.

## Cause

The kernel log shows only this pair, with no "Failed link training" after it:

    [drm:msm_dp_ctrl_link_train_1_2 [msm]] *ERROR* link training #2 on phy 0 failed. ret=-110
    [drm:msm_dp_ctrl_setup_main_link [msm]] *ERROR* link training on sink failed. ret=-110

So the driver did not give up. After a failed channel-equalization step it falls back to a smaller
link (here 2 lanes -> 1 lane, both at HBR) and trains that successfully. But this panel's maximum is
2 lanes at HBR (its DPCD lists only RBR and HBR), and 1920x1200 at 60 Hz needs all of it. A 1-lane link
trains fine but cannot carry the picture, so the screen stays black.

## Fix

`patches/local-dp-training-fallback-bw.diff` (**local, not upstream**) changes
`drivers/gpu/drm/msm/dp/dp_ctrl.c`: before each retry it checks whether the fallback link can carry the
current mode. If not, it retries at the original rate and lane count instead, and logs:

    [drm] fallback link rate=270000 lanes=1 too slow for mode, retrying at rate=270000 lanes=2

The training failure itself still happens now and then. The screen comes back on its own.

It applies cleanly to the stock 7.3 `drivers/gpu/drm/msm`, alone or together with the GPU patches.
It goes into the same `msm.ko`, so build it the way [gpu/README.md](../gpu/README.md#build-msmko-out-of-tree)
describes, with one more `patch -p1` line:

    patch -p1 < .../display/patches/local-dp-training-fallback-bw.diff

If your initramfs contains `msm`, rebuild it after installing the module.

## Tested

Screen off/on 60 times in a loop (`org.gnome.Mutter.DisplayConfig` `PowerSaveMode` 3/0, 4 s off):
2 training failures, both followed by the retry message, and the screen came back both times.
Before the patch: 2 failures in 40 cycles, both left the screen black until the next off/on.
