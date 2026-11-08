# NAM A2 Lite for the POD Go

**Neural Amp Modeler captures on the Line 6 POD Go and POD Go Wireless (firmware 2.50)**, running on the
POD Go's own DSP as an amp block, with your effects either side of it.

<!-- LAUNCH: the video link and thumbnail go here -->
▶️ **Watch the launch video on [Toneshift](#)** · 🌐 **[Setup page and capture converter](https://tavishrox.github.io/pod-go-nam-lite/)**

> **Unofficial and experimental.** Not affiliated with, endorsed by or supported by Line 6 or Yamaha Guitar
> Group. Installing modified firmware is at your own risk and may void your warranty. Read
> [Install](POD_GO.md#install) and [Recovery](POD_GO.md#recovery) before you start.

This is a fork of **[hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite)** by Derek Bui,
which does the same for the HX Stomp, HX Stomp XL and HX Effects. The HX instructions are in
[README_HX_STOMP.md](README_HX_STOMP.md); everything for those units still works as upstream.

---

## What you get

- **A NAM A2 Lite block** in the amp list, where Line 6 Elektrik used to be. Every other amp, cab, effect and
  IR is unchanged.
- **Your own captures.** Convert a `.nam` file on the [converter page](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/converter.html),
  import it with POD Go Edit like an IR, and pick it with the block's **Model** knob. Up to 101 captures at once.
- **Cab included.** Most captures include the speaker cab, so turn the cab block off and spend that DSP on effects.
- **Tone controls** after the capture (Bass, Mid with frequency and width, Treble, High Cut), **Input** to set
  how hard it's driven, and **Output**.
- **Free the fixed blocks.** [Preset templates](templates/) for NAM without the cab, FX loop or fixed EQ, and a
  [block helper](POD_GO.md#the-block-helper) to put an amp, cab, IR or FX loop into any empty block.

## How it works, in one paragraph

The POD Go can't load new kinds of files, but it stores IRs. A NAM A2 Lite capture is only 1,871 numbers, so
the converter packs them into an IR-sized `.wav`. You import it with POD Go Edit, and the NAM block (new DSP
code added to the POD Go's firmware) reads the numbers back from the slot the Model knob points at, and runs
the neural network on your guitar. You build the firmware yourself, from your own copy of Line 6's official
2.50 file, so no Line 6 code is ever shared. The bootloader is never touched, so Line 6's normal recovery
(hold **Page >** at power-on) always works.

## Get started

1. **Read the [POD Go guide](POD_GO.md)**: what's needed, building, installing, recovery, the knobs.
2. **Build** the firmware from your stock `POD_Go_v2.50.0_0x6e984472.hxf`:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
   .venv/bin/python podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf
   ```
3. **Install** `build/POD_Go_v2.50.0_NAM_A2_Lite.hxf` with Line 6 Updater (*Choose File*), after a POD Go Edit backup.
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
- **POD Go port**: Toneshift.

GPL-3.0-or-later, as upstream. See [LICENSE](LICENSE) and [NOTICE](NOTICE). No Line 6 firmware, code, data or
artwork is included or distributed, and no NAM captures.
