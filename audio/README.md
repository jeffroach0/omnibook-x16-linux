# Audio: speakers and microphones

The DT sets up two WSA8845 speaker amplifiers on SoundWire bus `swr0`, and the two digital microphones on the
VA macro. The sound card reuses the `GLYMUR-CRD` model name, so the audio DSP topology file that Ubuntu already
ships (`qcom/glymur/GLYMUR-CRD-tplg.bin`) is used unchanged.

**Safety:** Linux has no speaker protection for these amplifiers. The kernel's machine driver deliberately caps
the volume. Do not raise those limits, and do not use PipeWire's over-amplification at high levels.

## Why there are only two speakers

The upstream reference boards have four amplifiers (two on `swr0`, two on `swr3`). On this laptop nothing ever
answered on `swr3`. Windows' speaker endpoint is 2-channel, and listening tests showed that the two `swr0` amps
are a left/right pair. So the DT drops the `swr3` amps.

## Files

| File | Install to |
|---|---|
| `ucm/HP-OmniBook-X16.conf` | `/usr/share/alsa/ucm2/Qualcomm/glymur/` |
| `ucm/HP-OmniBook-X16-HiFi.conf` | `/usr/share/alsa/ucm2/Qualcomm/glymur/` |
| `wireplumber/51-omnibook-x16-speakers.conf` | `~/.config/wireplumber/wireplumber.conf.d/` |

ALSA looks up the UCM profile by the card's long name, so also create this link:

    sudo ln -sf ../../Qualcomm/glymur/HP-OmniBook-X16.conf \
      /usr/share/alsa/ucm2/conf.d/glymur/HP-HPOmniBookXLaptop16_cp1xxx-ConfigID-8F46.conf

Then restart PipeWire (`systemctl --user restart pipewire wireplumber`), or log out and back in.

## Details

- The topology only accepts 4 channels, so the UCM profile opens the device with 4 channels.
  The driver's channel map is FL, LB, FR, RB. Slot 0 drives the left speaker and slot 2 drives the right one.
  The WirePlumber rule labels the channels `[FL, RL, FR, RR]` so that PipeWire's "Front Left/Right" reach the
  right speakers.
- The microphones are quiet at the stock gain. The UCM profile sets `VA_DEC0/1 Volume` to 112 (+28 dB) instead of 100.
- The headphone jack is a Qualcomm SoundWire SDCA codec. Linux has no driver for it yet.
