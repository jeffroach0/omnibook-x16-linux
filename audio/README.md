# Audio: speakers, microphones and DisplayPort/HDMI

The DT sets up two WSA8845 speaker amplifiers on SoundWire bus `swr0`, the two digital microphones on the
VA macro, and audio on both USB-C DisplayPort outputs. The sound card is named `HP-OmniBook-X16-DP`.

**Safety:** Linux has no speaker protection for these amplifiers. The kernel's machine driver deliberately caps
the volume. Do not raise those limits, and do not use PipeWire's over-amplification at high levels.

## Why there are only two speakers

The upstream reference boards have four amplifiers (two on `swr0`, two on `swr3`). On this laptop nothing ever
answered on `swr3`. Windows' speaker endpoint is 2-channel, and listening tests showed that the two `swr0` amps
are a left/right pair. So the DT drops the `swr3` amps.

## Audio DSP topology

The kernel loads the audio DSP topology `qcom/glymur/<card name>-tplg.bin`. The Glymur topology that Ubuntu
ships (`GLYMUR-CRD-tplg.bin`) has only the speaker and microphone paths. The X1E80100 CRD topology (package
`linux-firmware-qualcomm-misc`) also has DisplayPort 0/1 paths, and it works on the Mahua audio DSP unchanged.
Point the card name at it:

    sudo ln -s ../x1e80100/X1E80100-CRD-tplg.bin.zst \
      /usr/lib/firmware/qcom/glymur/HP-OmniBook-X16-DP-tplg.bin.zst

(Older DTS versions used `model = "GLYMUR-CRD"` and the Glymur topology, with no DisplayPort audio.
The UCM profile below handles both.)

## Files

| File | Install to |
|---|---|
| `ucm/HP-OmniBook-X16.conf` | `/usr/share/alsa/ucm2/Qualcomm/glymur/` |
| `ucm/HP-OmniBook-X16-DP-HiFi.conf` | `/usr/share/alsa/ucm2/Qualcomm/glymur/` (X1E topology, with DisplayPort) |
| `ucm/HP-OmniBook-X16-HiFi.conf` | `/usr/share/alsa/ucm2/Qualcomm/glymur/` (Glymur topology, older DTS) |
| `wireplumber/51-omnibook-x16-speakers.conf` | `~/.config/wireplumber/wireplumber.conf.d/` |

`HP-OmniBook-X16.conf` picks the right HiFi file by itself: it checks for a DisplayPort mixer control that only
the X1E topology has.

ALSA looks up the UCM profile by the card's long name, so also create this link:

    sudo ln -sf ../../Qualcomm/glymur/HP-OmniBook-X16.conf \
      /usr/share/alsa/ucm2/conf.d/glymur/HP-HPOmniBookXLaptop16_cp1xxx-ConfigID-8F46.conf

Then restart PipeWire (`systemctl --user restart pipewire wireplumber`), or log out and back in.
PipeWire then shows "Speaker playback", "Internal microphones", "USB-C DisplayPort (back port)" and
"USB-C DisplayPort (front port)".

## Details

- The speaker device only accepts 4 channels, so the UCM profile opens it with 4 channels.
  The driver's channel map is FL, LB, FR, RB. Slot 0 drives the left speaker and slot 2 drives the right one.
  The WirePlumber rule labels the channels `[FL, RL, FR, RR]` so that PipeWire's "Front Left/Right" reach the
  right speakers.
- The microphones are quiet at the stock gain (`VA_DEC0/1 Volume` 100 = +16 dB). The UCM profile uses 112 with the
  Glymur topology and 118 with the X1E topology (speech measured about 6 dB lower there).
- X1E topology: the microphone device only starts with 4 channels (the two mics are on slots 0/1, slots 2/3 are
  silent; PipeWire mixes it down). The DisplayPort routes stay on all the time, because PipeWire tests every
  output with only the base setup active and rejects the whole profile if one fails to open.
- DisplayPort audio: back USB-C port = `hw:0,4`, front USB-C port = `hw:0,5`, 2 channels, 48 kHz.
- The headphone jack is a Qualcomm SoundWire SDCA codec. Linux has no driver for it yet.
