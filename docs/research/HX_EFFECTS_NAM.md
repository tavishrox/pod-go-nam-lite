# NAM A2 Lite on the HX Effects: assessment and plan (2026-11-16)

Research only. Nothing was flashed, installed, run from RAM or saved on the unit. The only access to
the HX Effects was `hx_ctl.py --pid 0x4245 status` (read-only).

## Summary

The HX Effects is already supported by upstream (Derek Bui's `hx-stomp-nam-lite`, which this repo
forks), on **firmware 3.80.0 only**. The code is in this repo too (`build.py`, `tools/effects.py`,
`nam_multi.py --effects`), so no porting is needed for a first install. A Python build with the
owner's own stock file should give a byte-identical copy of upstream's image (MD5 pinned in
`tests/test_firmware.py`). What is missing is the **RAM run**: upstream's RAM loader is the Stomp's
and has never run on an HX Effects. So the first test is either an installed build (recoverable with
Line 6 Updater) or a RAM loader port first (safer, more work).

## Result (2026-11-16, on the owner's unit)

- Unit on stock 3.80.0; stock file checked (MD5 `7c2ebdf1…`).
- Built with `build.py` from a clean copy of this repo: kernel simulator check passed, `l6ia_verify`
  ALL OK, output MD5 **`2efb98791581b67116ba82c5ecd30ea2`**, the same as upstream's pin.
- Three A2 Lite captures converted with `nam2ir.py` (65 Champ CLN and OD, 68 Mars JMP PA CRNCH,
  amp + cab), imported as User IRs in HX Edit.
- **Installed with Line 6 Updater and played for a while by the owner: everything runs well.** So the
  current build (with the loudness step) now has run on an HX Effects too.
- Not yet checked: two and three NAM blocks (DSP headroom), snapshots changing Model, and an
  HX Edit save and reopen of a preset with NAM.

## What upstream provides for the HX Effects

| | |
|---|---|
| Stock file | `HX_Effects_v3.80.0_0xd97239907.hxf`, MD5 `7c2ebdf1bffb6bcc5f89dda97f91e40c` (the build refuses anything else) |
| Build | `python3 build.py HX_Effects_v3.80.0_0xd97239907.hxf` writes `build/HX_Effects_v3.80.0_NAM_A2_Lite.hxf` (~2 min, mostly the SHARC simulator check). Steps: `nam_multi.py --mid-sweep --effects` (kernel), `patch_amp.py effects-eq` (`tools/effects.py`), `patch_amp.py patch`, `l6ia_verify.py`, `hxf.py pack` |
| Expected output | MD5 `2efb98791581b67116ba82c5ecd30ea2` (`tests/test_firmware.py`, the same pin upstream uses) |
| Browser build | Upstream's setup page builds it in Chrome from the stock file. This fork's ToneShift page (`web/pod-go/`) is POD Go only and has no HX Effects path |
| Tested on a unit? | **The previous build ran** on an HX Effects (Jerry Chuang, PRs #6 and #9; build `4d2a4a8a`). **The current build has not**: it adds only the loudness step to the DSP code, the same change that runs on the Stomp |
| RAM run | **None.** Upstream README: "the RAM loader is the HX Stomp's" |
| Credits | Scott's first HX Effects port (`scottlynn73/hx-effects-nam-lite`) found the User IR store and model tables; Jerry Chuang the browser and display fixes |

How it differs from the Stomp build (`tools/effects.py`):

- The HX Effects application refuses models it doesn't already know, so NAM **takes over Xenomorph
  Fuzz Mono** (preset ID 555, name, tables) instead of being added. Xenomorph Fuzz Stereo stays.
- The kernel reads User IRs from the HX Effects' own store (`IR_EFFECTS` in `nam_multi.py`).
- The capture's name shows as "Model: name" in the knob pop-up and on the scribble strip in overview
  mode; elsewhere Model shows the slot number (1..128).
- Code caves: room for 416 bytes of display helpers is freed by shrinking a model table only read by
  name (the HX Effects application has no room to append).
- 4 of 15 firmware entries change (application, DSP program, model list, DSP graph library).
  **The bootloader (Entry 1) is untouched.**

## Firmware the owner needs

1. Find the installed version: Line 6 Updater shows it when the HX Effects is selected (HX Edit also
   shows it). USB doesn't report it (`bcdDevice` is 0x0200, not the firmware).
2. Download **HX Effects 3.80.0** with Line 6 Updater (or line6.com) and keep the `.hxf`; check its
   MD5 is `7c2ebdf1bffb6bcc5f89dda97f91e40c`. No HX Effects firmware is on this Mac yet.
3. If the unit is on a version newer than 3.80.0, NAM needs a step back to 3.80.0 first: back up
   everything in HX Edit before doing that, and check Line 6's release notes on presets. If the unit
   is older, update it to stock 3.80.0 and play it for a day before going further.

## Where the NAM block goes

- **Menu:** Distortion > Mono, in Xenomorph Fuzz Mono's place (the HX Effects has no Amp category).
  HX Edit shows the block as "Xenomorph Fuzz" with its knob names (Gain = Input, MinFreq = Model, ...).
- **Grid:** any of the 9 mono-capable slots; for the usual use, **path A position 1** (first in the
  chain, after a wah or compressor if there is one). Up to 3 NAM blocks a preset (the kernel has 3
  model slots).
- **Captures:** converted with `tools/nam2ir.py` (or the setup page) to `.wav`, imported as User IRs
  in HX Edit, picked with the Model knob, as on the POD Go. The HX Effects has the User IR store the
  kernel reads; 48 kHz A2 Lite captures only.
- **What to capture:** a full-rig capture (amp + cab) wants the HX Effects going to FRFR, PA or an
  interface. In front of a real amp, or in 4-cable-method before the send, use drive pedal or
  preamp captures with Cab off in the capture.
- **DSP:** each block declares DSP cost 2275 and uses about 23% on the Stomp (empty preset ~20%).
  The HX Effects' real load hasn't been measured anywhere. Expect two blocks with room for effects,
  three with little else; the unit greys out what doesn't fit.
- **Presets:** any of the owner's presets that use **Xenomorph Fuzz Mono** would open NAM in its
  place. The current preset (setlist 0, 27 "Rocker 2") doesn't use it. Check the rest before
  installing (step 3).

## Risks

- **A build that hangs at boot.** The current build hasn't run on an HX Effects. Recovery: power
  off, **hold the right arrow (>) while powering on** (update mode), install the stock 3.80.0 `.hxf`
  with Line 6 Updater. This works because the bootloader is untouched; it has restored a Stomp that
  hung at the splash. It hasn't been needed on an HX Effects yet.
- **Firmware version change.** Going to 3.80.0 from another version changes the unit even before
  NAM. Back up first.
- **Xenomorph Fuzz Mono is gone** while the NAM build is installed.
- **DSP load is unmeasured** on this unit; a third block may not fit.
- **Input level:** the converter's level trim uses the Stomp's measured 11.5 dBu; the HX Effects'
  input may differ (instrument/line switch). Sound only, not safety.
- **Warranty and Line 6's position:** unofficial firmware, at the owner's risk (README).

## Plan

Steps 1 to 4 don't touch the unit. Each step after that waits for the owner's go.

1. **Owner:** read the installed version in Line 6 Updater; download stock HX Effects 3.80.0 and
   keep it (MD5 above). Back up all setlists and IRs in HX Edit.
2. **Build (no unit):** `python3 build.py HX_Effects_v3.80.0_0xd97239907.hxf` in this repo, then
   check the output MD5 is `2efb9879...`, i.e. exactly upstream's image. Optional: also build the
   image that has already run on an HX Effects (`4d2a4a8a`, from the upstream commit before the
   loudness step) in a separate worktree, as a fallback first install.
3. **Read-only checks:** look through the HX Edit backup for Xenomorph Fuzz Mono; convert one or two
   A2 Lite captures with `nam2ir.py`.
4. **Decide the first on-unit test** (owner):
   - **4a. Install now** (upstream's route): Line 6 Updater, Choose File, the built `.hxf`. Recovery
     is the right arrow at power-on plus the stock file. Fastest; a previous build has run.
   - **4b. RAM loader port first** (this repo's POD Go route): a RAM run writes nothing to the unit.
     Line 6 Updater's strings show the HX Effects uses the same DFU route as the Stomp ("loading
     update app (via DFU)", `L6HxEffectsDevice`). The port needs: `hx_dfu_reboot.py` for PID 0x4245;
     the HX Effects' MCU, SDRAM and eMMC set-up read from its own bootloader entry; its
     `read_blocks`/`write_blocks` addresses for the hook; and a layout that avoids its application,
     which runs from SDRAM at 0x28000000. Roughly the POD Go's loader work (`docs/PODGO_PORT_MAP.md`,
     "RAM run on the POD Go"), and its first try is itself an on-unit step (a DFU load of the loader
     into RAM) that needs a go.
5. **First test (after go):** one NAM block in path A position 1, Model on the imported slot, other
   blocks off. Check: the block appears in Distortion > Mono, sound, Model switching, the name in the
   pop-up. Read it back with `hx_ctl.py --pid 0x4245 status` (expect model 555 in the slot).
6. **Then:** two blocks, then three (does the unit grey out the third?); snapshot Model changes;
   HX Edit round-trip of a preset with NAM (open, edit, save, reopen) on a scratch preset slot.
7. **If anything goes wrong:** power off, hold >, power on, stock 3.80.0 in Line 6 Updater.
8. **Later (optional):** an HX Effects path in the ToneShift browser page, and MORF-X knowing the
   NAM block on the HX Effects.

Recommendation: 4a with the build that matches upstream's pin, because upstream's recovery path is
proven and the HX Effects code has run. Choose 4b if the owner wants a no-write first test; it costs
a loader port before any NAM sound.

## Next: 6 snapshots on the HX Effects (first look, 2026-11-16, read-only)

The owner tested HX Edit save and reopen with NAM: works.

The HX Effects 3.80.0 application (Entry 0, segment at 0x28000000) has the same snapshot module as
the POD Go 2.50 (`snapshotModel.c`, `SNAPSHOT_MODEL_MAX_SNAPSHOTS`, "Snap 1".."Snap 4"), so
`docs/research/SNAPSHOTS_6.md` and `podgo/snap6/` are the template:

| | POD Go 2.50 | HX Effects 3.80.0 |
|---|---|---|
| Snapshots | 4 | 4 |
| Reset (names "SNAPSHOT n", loop `cmp #5`) | `0x28cb7878` | `0x280b8754` |
| Record stride | `0x28c` | `0x26c` (first record at +0xc) |
| Tail: per-snapshot bytes (0x01010101 words) | +0xa3c | +0x9bc (5 words + a halfword) |
| Current snapshot | +0xa4b | +0x9d5 |

Not yet found on the HX Effects: the select function, the preset serializer (`fixarray(4)`), the
footswitch and scribble-strip code, CC69. The HX Effects shows snapshots on its six scribble strips
rather than the POD Go's tiles, so the screen part is different work. Whether HX Edit keeps
snapshots 5 and 6 on this unit is unknown (it handles 8 on the Helix Floor).

The big difference: **no RAM run on the HX Effects.** The POD Go's six-snapshot work took many
on-unit tries from RAM. Here each try would be a full install (recoverable with > at power-on and the
stock file), unless the RAM loader is ported first (step 4b above).
