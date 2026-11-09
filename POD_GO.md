# NAM A2 Lite for the POD Go

A Neural Amp Modeler block for the **Line 6 POD Go and POD Go Wireless, firmware 2.50**. It plays
[NAM](https://www.neuralampmodeler.com) "A2 Lite" captures of real amps and pedals on the POD Go's own
DSP, as an amp block, next to everything the POD Go already does.

This is a port of [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite) by Derek Bui,
which does the same for the HX Stomp, HX Stomp XL and HX Effects. POD Go port by Toneshift.

> **Unofficial and experimental.** Not affiliated with, endorsed by or supported by Line 6 or Yamaha
> Guitar Group. Installing modified firmware is at your own risk and may void your warranty. Read
> [Install](#install) and [Recovery](#recovery) before you start.

**Status (2026-11-08):** built, tested and installed on one POD Go Wireless. Every check below passed
on that unit. It has not yet been tried on a wired POD Go, which runs the same firmware file.

---

## What it gives you

- **A NAM A2 Lite block in the amp slot.** Pick it from the amp list where **Line 6 Elektrik** used to
  be. Elektrik is the one model this build gives up; every other amp, cab, effect and IR is unchanged.
- **Your own captures.** Convert a `.nam` file, import it with POD Go Edit as an IR, and choose it with
  the block's **Model** knob. Up to 101 captures can be on the unit at once (IR slots 1 to 101).
- **Cab included.** Most captures include the speaker cab, so you turn the cab block off and use the
  freed DSP for effects: a drive before NAM, delay and reverb after it.
- **A tone stack** (Bass, Mid with adjustable frequency and width, Treble, High Cut), an **Input** knob
  to set how hard the capture is driven, and an **Output** level.
- **Captures at matching volume.** A capture whose file states its loudness plays at about the same
  level as the others. A capture whose file states the input level it was recorded at is driven at that
  level when Input is at 5.0.

## How it works (in plain terms)

The POD Go cannot load new kinds of files, but it can store IRs: short audio files that describe a
speaker cab. A NAM A2 Lite capture is small, 1,871 numbers. So:

1. **The converter** writes those numbers into an IR-sized `.wav`, in the order the DSP code needs them.
2. **POD Go Edit** imports that `.wav` into an IR slot like any other IR. It keeps the whole file.
3. **The NAM block** is new DSP code added to the POD Go's DSP program. On each audio block it reads the
   numbers from the IR slot the Model knob points at and runs the neural network on your guitar signal.

The firmware build reads your own copy of the official POD Go 2.50 firmware file and changes four parts
of it on your computer:

| Part | What changes |
|---|---|
| DSP program | The NAM code is added, and one unused DSP function slot is pointed at it. No stock DSP code is changed. |
| DSP block library | Line 6 Elektrik's processing chain is replaced by one that runs the NAM code. |
| Model list | Elektrik's entry gets NAM's name and its 11 knobs. |
| Main app | The name shown on the unit and in its browser, and the DSP cost the unit counts for the block. |

The bootloader is never touched, which is what keeps [Recovery](#recovery) possible.

## What's needed

- A POD Go or POD Go Wireless with **firmware 2.50**, and the official
  `POD_Go_v2.50.0_0x6e984472.hxf` (Line 6 Updater downloads it; MD5 `e0ea3e1ed32f0f353b79f6ad39631838`).
- A Mac or Windows computer with **Line 6 Updater** and **POD Go Edit**.
- To build the firmware: Python 3.10 or newer with `numpy` (see [Building](#building)).

No Line 6 firmware is included in this project, and **built firmware must not be shared**: it contains
Line 6's code. Everyone builds their own from their own stock file.

## Converting captures

Use the **[converter page](https://tavishrox.github.io/pod-go-nam-lite/web/pod-go/converter.html)**: drop in `.nam` files and download the converted files. It runs entirely in
your browser and uploads nothing. Or use the command-line tool:

```bash
python3 tools/nam2ir.py "My Capture.nam" -o "NAM My Capture.wav"
```

Both give byte-identical files, checked against captures playing on the unit.

Accepted: NAM **A2 Lite** captures trained at **48 kHz**. A `.nam` that holds several sizes (a
"slimmable" A2 file) gives its A2 Lite part. Refused, with the reason shown: other NAM sizes (Standard,
Lite, Feather, Nano, A2 Full) and captures trained at other sample rates.

Name your converted files with " NAM" at the end (the tools do this) so you can tell captures from real
IRs in POD Go Edit's IR list.

## Using it

1. **Import the `.wav`** into an empty IR slot with POD Go Edit, as you would any IR.
2. **Choose NAM A2 Lite** as the amp in a preset. It is in the amp list where Line 6 Elektrik was.
3. **Set Model to the slot.** Model value = (slot − 1) ÷ 10:

   | Slot | 1 | 2 | 4 | 10 | 11 | 50 | 101 |
   |---|---|---|---|---|---|---|---|
   | Model | 0.0 | 0.1 | 0.3 | 0.9 | 1.0 | 4.9 | 10.0 |

   An empty slot, or one holding a normal IR, keeps the block silent.
4. **Turn the cab block off** for captures that include a cab (most do: look for "CAB" in the name).
   Keep a cab or IR on for "DI" / amp-only captures.
5. **Play.** Input at 5.0 drives the capture as it was recorded; adjust to taste (each 0.1 step is 0.4 dB).

**Never point the cab/IR block at a NAM slot.** Played as an IR, a capture file is harsh noise.

### The knobs

POD Go Edit knows the block only as Line 6 Elektrik, so it shows Elektrik's knob names. The unit shows
NAM's.

| On the POD Go | In POD Go Edit | What it does |
|---|---|---|
| Input | Drive | Level into the capture, ±20 dB; 5.0 = as recorded |
| Bass | Bass | Low shelf at 100 Hz, ±12 dB |
| Mid | Mid | Peak at Mid Freq, ±12 dB |
| Treble | Treble | Peak at 2.5 kHz, ±12 dB |
| High Cut | Presence | Top-end roll-off; 10 = open |
| Output | Ch Vol | Block volume; 5.0 = unity |
| Model | Master | The IR slot to play (table above) |
| Mid Freq | Sag | Centre of the Mid knob, 150 Hz to 3 kHz |
| Q | Ripple | Width of the Mid peak: wide, medium, narrow |
| Polarity | Bias X | Inverts the phase above 5.0 |
| (unused) | Bias | Nothing |

### DSP use

NAM takes about **28%** of the POD Go's DSP (measured on the unit). The unit counts it as **2,850** of
its 9,000-unit budget, so it refuses presets that would not run, as it does for stock blocks. Drive +
NAM + delay + reverb fits easily; the heaviest preset the unit would accept around NAM played without a
crackle. POD Go Edit's DSP meter still shows Elektrik's figure (18.25) for the block; the unit's own
check is the one that counts.

## Freeing the fixed blocks

The POD Go's "fixed" blocks (volume, wah, FX loop, amp, cab, EQ) are only what stock presets contain. An edited
preset can leave any of them out, and the DSP they held goes to effects. Measured on firmware 2.50:

| Rule | Limit |
|---|---|
| Amp, cab or IR, fixed EQ, FX loop | one of each at most (two of any are refused) |
| Other effects (wah and volume count as ordinary effects) | up to 7 |
| DSP | blocks totalling about 8,000 cost units |

A preset over a limit is dropped whole by the unit. Leaving out volume, wah, FX loop, cab and fixed EQ frees
about 1,236 units. Five EQs (Simple EQ, Low and High Cut, Low/High Shelf, Tilt, 10 Band Graphic) are ordinary
effects already, in the EQ category of any empty block, so several can be used at once.

### Templates

Import with POD Go Edit (they overwrite the slot you import into):

| Template | Chain | DSP |
|---|---|---|
| [NAM Blank](templates/NAM%20Blank.pgp) | Volume, NAM; 9 empty blocks | 3,000 |
| [NAM Essentials](templates/NAM%20Essentials.pgp) | Volume, Wah, Minotaur, NAM, Simple Delay, Plate | 5,411 |
| [NAM Full Board](templates/NAM%20Full%20Board.pgp) | Volume, Deluxe Comp, Minotaur, NAM, Simple EQ, Chorus, Vintage Digital, Hall | 6,725 |

NAM is on IR slot 4 (Model 0.3): set Model to your capture's slot. The expression pedal runs volume, with the
wah on the toe switch. `podgo/make_templates.py` makes your own from any POD Go Edit export.

### The block helper

Once a fixed block is removed, neither the POD Go nor POD Go Edit offers Amp, Cab/IR or Send/Return on an
empty block. `podgo/blocks.py` puts any model into any empty block of the preset on the unit, over USB
(quit POD Go Edit first; press SAVE on the POD Go to keep the change):

```bash
python3 podgo/blocks.py status                    # blocks, effect count, DSP use
python3 podgo/blocks.py list cab 4x12             # amp | cab | ir | loop | eq | fx, and a word to filter
python3 podgo/blocks.py add "4x12 Greenback25"     # the modern cab (250 units); "add ir NAME" for the legacy one
python3 podgo/blocks.py add "Mono FX Loop" --at 5
python3 podgo/blocks.py remove 5
```

It checks the one-of-each rule first; a change the unit still refuses is undone. Each change keeps the preset
before it in `build/blocks_undo/` (`blocks.py restore FILE`).

## Your own boot screen

**NAM A2 Edition**: tick *Add the NAM A2 Edition boot screen* on the setup page, or build with `--edition`.
Toneshift's lettering ([art/nam-a2-edition](art/nam-a2-edition/), CC BY 4.0) is drawn over your own POD Go's
boot screen; the repository holds only the lettering.


The splash screen with the Line 6 logo is a 480 x 272 app graphic (two of them: POD Go and POD Go Wireless).
`podgo/splash.py preview IMAGE OUT.png` shows what an image will look like on the unit (fitted to the screen,
16-bit colour), and the build takes it:

```bash
.venv/bin/python podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf --splash wired.png --splash-wireless wireless.png
```

The unit writes "Firmware 2.50.0" over the bottom of the image. The bootloader's own brief red frame before
it is not changed. A build with an image based on Line 6's artwork is for your own unit only.

## Install

1. Turn the POD Go off and on, so it is running its installed firmware.
2. **Back up** with POD Go Edit (presets and IRs). Quit POD Go Edit.
3. Open **Line 6 Updater**, work offline if offered, choose your POD Go, choose **Choose File** (or
   *use local file*), and pick the built `.hxf`.
4. Don't unplug or power off until the update has finished and the unit has restarted.

Presets and IRs stay on the unit.

### Try it first without installing

`tools/hxf_ram.py` can run a build from the POD Go's memory for one session, installing nothing; a
power-cycle brings back the installed firmware. This is how every build was tested. See
[RAM_RUN.md](RAM_RUN.md) and the POD Go notes in `docs/PODGO_PORT_MAP.md`; the POD Go needs its own
loader, `tools/ramboot/firmware-ramboot-podgo.dfu` (`make podgo` in `src/ramboot`).

## Recovery

If the unit stops at the splash screen or an update fails:

1. Turn the POD Go off.
2. Hold **Page >** and turn it on: update mode.
3. In Line 6 Updater, install the stock `POD_Go_v2.50.0_0x6e984472.hxf` with Choose File.

## Building

The easy way: the [setup page](https://tavishrox.github.io/pod-go-nam-lite/#build) builds it in your browser
(Pyodide running these same tools; nothing is uploaded) and compares the result with the tested build. The
command line does the same, plus a run of the NAM code in a SHARC simulator:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf
```

It checks your file's MD5, builds the NAM code and runs it in a SHARC simulator against a reference
(bit for bit, including the 32-sample call test), then writes `build/POD_Go_v2.50.0_NAM_A2_Lite.hxf`.
`--donor plexi` builds the earlier variant that replaces Brit Plexi Brt instead of Elektrik.

## Tested on the unit

| Check | Result |
|---|---|
| Sound | Recorded over USB and compared with the capture run offline on the same dry signal: matches. A capture cut to 1,024 samples would not (so POD Go Edit stores the whole file). |
| Names | NAM A2 Lite in the browser and on the block, NAM knob names on the unit |
| Presets | All 128 user presets selected in turn, NAM loaded after each: its output never moved (largest change 3×10⁻¹⁰) |
| DSP | NAM measured at 28.3% (median) of the 393.2 MHz DSP; heaviest admitted preset plays clean |
| Install | Installed with Line 6 Updater; presets intact, NAM loads and plays |

## Known limits

- **One NAM block per preset**: the POD Go has one amp block.
- **POD Go Edit** shows the block as Line 6 Elektrik with Elektrik's knob names and DSP figure.
- **Model shows a number**, not the capture's name.
- **Input calibration** assumes the Helix family's input level (11.5 dBu at full scale); the POD Go's
  has not been measured. If drive captures feel off, adjust Input.
- **Firmware 2.50 only.** Another firmware version needs the build updated.

## What was different from the HX Stomp

For anyone porting further, the full log is `docs/PODGO_PORT_MAP.md`. In short:

- **Block size.** The POD Go calls amp blocks with 32 samples; the Stomp with 16. A 16-sample kernel
  processed half of each buffer and let the dry signal through the other half. A small wrapper now
  runs the kernel on each half.
- **DSP clock.** 393.216 MHz, not 450 MHz.
- **Memory.** Growing the DSP's graph buffer or adding a model or block library entry hangs the POD Go,
  so NAM replaces an existing model in place and uses fixed external memory.
- **Same protocols.** The DFU route, the RAM loader (with an eMMC timing fix) and HX Edit's control
  protocol all work on the POD Go.

## Credits and licence

- [hx-stomp-nam-lite](https://github.com/nocaseguy/hx-stomp-nam-lite) by **Derek Bui**: the NAM
  kernel, converter, build tools and RAM loader this port is built on.
- [Neural Amp Modeler](https://www.neuralampmodeler.com) by Steven Atkinson: the A2 model format.
- POD Go port: this project.

GPL-3.0, as the upstream project. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
