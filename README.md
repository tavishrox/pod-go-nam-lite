# NAM A2 Lite for the POD Go

**Neural Amp Modeler captures on the Line 6 POD Go and POD Go Wireless (firmware 2.50)**, running on the
POD Go's own DSP as an amp block, with your effects either side of it.

[![NAM A2 Lite on the POD Go: launch video](https://img.youtube.com/vi/w9rP10gc9I0/hqdefault.jpg)](https://youtu.be/w9rP10gc9I0)

▶️ **[Watch the launch video](https://youtu.be/w9rP10gc9I0)** on [ToneShift](https://www.youtube.com/channel/UC8Fy07TKY0txLxOgj7edHCA) · 🌐 **[Setup page and capture converter](https://tavishrox.github.io/pod-go-nam-lite/)** · 📘 **[Step-by-step install guide](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/how-to.html)** ([PDF](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/POD-Go-NAM-Install-Guide.pdf))

> **Unofficial and experimental.** Not affiliated with, endorsed by or supported by Line 6 or Yamaha Guitar
> Group. Installing modified firmware is at your own risk and may void your warranty. Read
> [Install](POD_GO.md#install) and [Recovery](POD_GO.md#recovery) before you start.
>
> **A word from me on risk.** Line 6 have commented on the mods now appearing for the HX Stomp, HX Effects and
> POD Go, and they seem encouraged that people are experimenting. That doesn't surprise me: the company was
> built that way. They have also warned against installing third-party firmware, because support will be very
> limited if something goes wrong. That is absolutely true. If you don't fully understand what you're
> installing, or you'd be uncomfortable bricking your unit, sleep on it. I talk about who this is for in the
> video: it's for tinkerers, the kind of folks who hang around on GitHub, the same folks who were modding Tube
> Screamers in the 80s. Just a heads-up: understand the risks before you start. *ToneShift*
>
> **No Line 6 files in this project.** This repository contains no Line 6 firmware, code or artwork. Everything
> that uses Line 6's work is made during the build, on your computer, from the official firmware file you
> download from Line 6: the NAM block is written into your own copy, the boot screen is drawn over your own, and
> the six-snapshot tiles are drawn from your own firmware's snapshot images.

This is a fork of **[hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite)** by Derek Bui,
which does the same for the HX Stomp, HX Stomp XL and HX Effects. For the HX Stomp and XL, use Derek's project.

**Now including the HX Effects (3.80.0), fully tested.** The [setup page](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/#build)
also builds NAM A2 Lite for the HX Effects from your own stock `HX_Effects_v3.80.0_0xd97239907.hxf`: upstream's
HX Effects build (Derek Bui; HX Effects port by Jerry Chuang and Scott), byte for byte, installed and played on
an HX Effects by ToneShift. NAM is under **Distortion > Mono**, in Xenomorph Fuzz Mono's place; captures load as
User IRs in HX Edit and are picked with the Model knob, up to three NAM blocks a preset. No run from RAM on the
HX Effects. Recovery: hold **>** at power-on and install the stock file with Line 6 Updater. Notes:
[docs/research/HX_EFFECTS_NAM.md](docs/research/HX_EFFECTS_NAM.md).

---

## What you get

- **A NAM A2 Lite block** in the amp list, where Line 6 Elektrik used to be. Every other amp, cab, effect and
  IR is unchanged.
- **Your own captures.** Convert a `.nam` file on the [converter page](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/converter.html),
  import it with POD Go Edit like an IR, and pick it with the block's **Model** knob. Up to 101 captures at once.
- **Cab included.** Most captures include the speaker cab, so turn the cab block off and spend that DSP on effects.
- **Tone controls** after the capture (Bass, Mid with frequency and width, Treble, High Cut), **Input** to set
  how hard it's driven, and **Output**.
- **Six snapshots** (optional, experimental): hold MODE and the footswitches become snapshots 1&ndash;6 (bottom row
  1 2 3, top row 4 5 6), with 5 and 6 saved in the preset, and snapshot tiles in each snapshot's LED colour, as
  stomp mode shows its blocks. Also on its own, without NAM. POD Go Edit only sees four: see
  [Six snapshots](POD_GO.md#six-snapshots-experimental) for what that means.
- **The ToneShift Edition** (optional): a boot screen with ToneShift's "NAM A2 Edition" lettering over your POD Go's own splash.
- **Free the fixed blocks.** [Preset templates](templates/) for NAM without the cab, FX loop or fixed EQ (or just without the FX loop), and a
  [block helper](POD_GO.md#the-block-helper) to put an amp, cab, IR or FX loop into any empty block.

## How it works, in one paragraph

The POD Go can't load new kinds of files, but it stores IRs. A NAM A2 Lite capture is only 1,871 numbers, so
the converter packs them into an IR-sized `.wav`. You import it with POD Go Edit, and the NAM block (new DSP
code added to the POD Go's firmware) reads the numbers back from the slot the Model knob points at, and runs
the neural network on your guitar. You build the firmware yourself, from your own copy of Line 6's official
2.50 file, so no Line 6 code is ever shared. The bootloader is never touched, so Line 6's normal recovery
(hold **Page >** at power-on) always works.

## Get started

1. **Follow the [step-by-step install guide](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/how-to.html)**
   (every click, also as a [PDF](web/pod-go/POD-Go-NAM-Install-Guide.pdf)), or read the [POD Go guide](POD_GO.md)
   for the details: what's needed, building, installing, recovery, the knobs.
2. **Build** the firmware: drop your stock `POD_Go_v2.50.0_0x6e984472.hxf` on the
   [setup page](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/#build). It builds in your browser (nothing is uploaded)
   and says **Verified** when the result is byte for byte the tested build. Or on the command line:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
   .venv/bin/python podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf
   ```
3. **Install** the built `POD_Go_v2.50.0_NAM_A2_Lite.hxf` with Line 6 Updater (*Choose File*), after a POD Go Edit backup.
4. **Convert** your captures on the [converter page](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/converter.html)
   and import the `.wav` files with POD Go Edit.
5. **Play**: amp block → **NAM A2 Lite**, Model → your IR slot (0.0 = slot 1, 0.3 = slot 4), cab block off.

## Tested

On a POD Go Wireless, firmware 2.50: the sound matches the capture run offline on the same guitar signal; all
128 user presets load with NAM unaffected; NAM measured at 28.3% of the DSP and counted as 2,850 of the
unit's 9,000 budget units; the heaviest preset the unit admits plays clean. Wired POD Go: same firmware file,
not yet tried. Details: [docs/PODGO_PORT_MAP.md](docs/PODGO_PORT_MAP.md).

## Problems, ideas, captures that won't convert

[Open an issue](../../issues/new/choose): the form asks for what's needed (wired or Wireless, what you did,
what happened).

## Credits and licence

- **[hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite)** by **Derek Bui**: the NAM kernel,
  converter, build tools and RAM loader this port is built on.
- **[Neural Amp Modeler](https://www.neuralampmodeler.com)** by Steven Atkinson: the A2 model format.
- **POD Go port**: Mark Daniels (TavishRox, ToneShift). Copyright (C) 2026 Mark Daniels.

GPL-3.0-or-later, as upstream. See [LICENSE](LICENSE) and [NOTICE](NOTICE). No Line 6 firmware, code, data or
artwork is included or distributed, and no NAM captures.
