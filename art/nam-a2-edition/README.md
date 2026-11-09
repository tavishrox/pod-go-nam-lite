# ToneShift Edition boot screen

Lettering by **ToneShift** (Mark Daniels, TavishRox), copyright (C) 2026 Mark Daniels, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): use it, share
it, change it, with credit to ToneShift.

These overlays hold only the green lettering on a transparent background, at the POD Go's screen size
(480 x 272): `wired.png` for the POD Go, `wireless.png` for the POD Go Wireless. The build draws them over the
boot screen taken from **your own** firmware file, so no Line 6 artwork is in this repository:

- setup page: tick **ToneShift Edition** before building
- command line: `podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf --edition`

Your own design: any transparent PNG of the screen's shape works the same way (`podgo/splash.py overlay` shows
it on your POD Go's screen first).
