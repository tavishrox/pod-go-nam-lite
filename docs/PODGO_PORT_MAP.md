# NAM A2 Lite on the POD Go (2.50): port map

Working notes for porting this repository (HX Stomp 3.80.0) to the POD Go / POD Go Wireless,
firmware `POD_Go_v2.50.0_0x6e984472.hxf`. Static analysis only unless marked **on unit**.
Labels: **verified** (checked against the bytes), **likely**, **unknown**.
Earlier POD Go research lives in `../POD Go Firmware Investigation.txt` and `../POD Go/`.

## Container and entries (verified)

`hxf.py unpack` / `pack` round-trip the stock file byte for byte (`../build/stock/roundtrip.hxf`).
L6IA has 17 entries (Stomp 15). Version marker `0x02500000` (Stomp `0x03800000`); `tools/l6ia.py`
accepts both. The `.hxf` carries a kind-5 trailer (RAM updater app, 0x17010 bytes) like the Stomp's.

| Role | Stomp | POD Go | POD Go size / notes |
|---|---|---|---|
| Cortex-M4 application | 0 | 0 | type 2, 7 segments, code seg[6] at `0x28c58ba0` (Stomp `0x28d8fa80`) |
| Bootloader (SPIFI image) | 1 | 1 | type 1, "App:Bootloader" |
| SHARC boot stream (LDR) | 2 | 2 | 0x62150 bytes (Stomp NAM build fills 0x7ffb8 of 512 KiB): ~120 KB headroom |
| Model descriptors | 3 | 3 | 620 models, 106 `HD2_Amp*`; `parse_entry3_full` works unchanged |
| Model blobs / DSP graph library | 4 | 4 | Blob 0 = 0x57ff1 words; `stock_prims_in_use` works unchanged |

Donor models used by the Stomp build all exist on the POD Go (verified):
`HD2_DistXenomorphFuzzMono` (blob 0x244), `HD2_ImpulseResponse2048Mono` (0x114),
`HD2_AmpLine6Clarity` (0xce), `HD2_VolPanVolMono` (0x1ed), `HD2_DistMinotaurMono` (0x1ff).

## SHARC (Entry 2)

- DSP: ADSP-21489 (owner photo). Same internal block map as the Stomp's 21469; external memory is
  **SDRAM**, not DDR2 (same EP DMA descriptor layout per ADI HRM).
- Primitive registry: INIT_L32 at `0x200000`, 8-word records `{id, f1, 0, f3, f4, entry, dm, pm}`
  (verified, same format). Primitive **0x9c75 exists at `0x200588` and no stock model uses it**
  (verified with `kit_patch_amp.stock_prims_in_use`). 20 of the Stomp's 24 unused IDs are also
  unused here.
- Hook record template: primitive 0x822 at `0x200470` =
  `{0x822, 0x60d8f2, 0, 0x60d956, 0x60d83f, 0x8dc17, 0x91, 0x0d}` (dm 0x91 / pm 0x0d, same as the
  Stomp hook). POD Go hook record: `{0x9c75, 0x60d8f2, 0, 0x60d956, 0x60d83f, <kernel entry>, 0x91, 0x0d}` (**likely**).
- User IR store (from the earlier research, offline replay of the shipped copy loop):
  flag table `0x26758e`, slot-0 high `0x267e0d`, pool `0x26760e` .. `0x2a760e` (128 x 2,048).
  Same shape as the Stomp's `IR_FLAG 0x2ab56e` / `IR_TOP 0x2abded` (both differ by 0x87f), so
  `nam_multi.py` needs `IR_FLAG, IR_TOP = 0x26758e, 0x267e0d` (**likely**; the 0xf0 command's
  argument path is not fully traced).
- Static LDR occupancy (`podgo/e2map.py`): Block 2 statically touched only at `0xc0000..0xc08e4`;
  Block 3 PM zeroed up to ~`0xe2560`. The Stomp kernel's windows (PM `0xc4ef8..`, `0xe302c..`,
  DM `0xe4850..`) do not collide with static records, **but run-time heaps are unknown** (the
  Stomp's heap table is DM `0x9d5cc`, set up by code; no static triple table found on the POD Go).
- Most SHARC code is VISA (INIT_L16 at `0x165308..`), so finding heap setup and the Blob 0 buffer
  size needs a VISA decoder or measurement on the unit.

### Still unknown (SHARC)

1. Free internal memory for kernel code/data (heap extents) - measure on unit as the Stomp work did
   (`docs/research/KIT_HEAP_USE.md`).
2. A free SDRAM window for the kernel's static rings (Stomp: DDR2 `0x324500..0x328000`) and the
   per-block `sdram_words` arena (0x5000).
3. Blob 0 buffer size in the DSP (Stomp patches `0x77aac -> 0x8ee00` and moves Heap 6). The POD Go's
   Blob 0 is 0x57ff1 words; the NAM composite adds a few hundred, so this may not be needed.
4. POD Go DSP budget: 9000-unit admission limit in the app (earlier research); NAM declares 2275 on
   the Stomp. Expect one block to fit; more needs measuring.

## ARM application (Entry 0)

Different link from the Stomp; every `E0_DEVICES` / `IR_TITLE` address must be found again.
**Unknown:** model Table 1/2, browser lists, subcategory folders, IR-title sites. The POD Go also has
fixed blocks (amp, cab) plus four flexible slots; the block identity (Xenomorph Fuzz Mono, an effect)
should land NAM in a flexible slot.

## Run from RAM (no install) - looks portable

- The POD Go app contains `BootIntoDfu!` (verified) and Line 6 Updater's `L6PodGoDevice` has a DFU
  mode path (`prepareForDeviceInfoDfu(eHxFirmwareMode_Dfu)`), the same route as the Stomp
  (`L6HxStompDevice`). MCU memory map matches the LPC43xx (segments at 0x10000000 / 0x10080000 /
  0x20000000 / 0x28000000).
- eMMC functions (Stomp prologue `2de9f04f804dd5f84832`): **read `0x28c6aa04`, write `0x28c6adb8`**
  (verified pattern match, the only two hits). Still needed for `tools/hxf_ram.py`: their
  continuation addresses, the card struct literal, the app's SDRAM ceiling, the eMMC partition
  starts for 17 entries, and the POD Go's update-mode button.
- POD Go USB: VID 0x0e41 PID 0x424b (**on unit**, seen connected).

### RAM loader findings (2026-11-07)

- Bootloader SDRAM set-up (verified, capstone): `sdram_init` at `0x14002714`, called from
  `0x14004e4e` with EMC at 102 MHz and timing table `0x1400576c` =
  `{18,44,74,10,44,22,62,62,74,14,22,15625}`: **identical** to `src/ramboot/sdram.h`. Same EMC
  delay (0x5555), clock pins (0xF5/0xF0), CREG6 bit 16, EMCDIV 0x21, and the P6_7 / GPIO5[15]
  low step at `0x14004e10`. Dynamic config `0x84480` present. So the loader's SDRAM code should
  run unchanged.
- eMMC hook: read `0x28c6aa04`, write `0x28c6adb8`; their `ldr r5,[pc,#0x200]` literals
  (`0x28c6ac0c`, `0x28c6afc0`) both hold the card struct **`0x28230740`** (verified).
- App entry `0x28c5ba8d`, parameter word `0x100013e8`. App code names SDRAM only below
  `0x28ce4000` (code) and around `0x28000000..0x28232000` (data); nothing loads addresses in
  `0x29000000..0x29F00000` (pc-relative and movw/movt scan), so the Stomp's hook/staging
  windows look free. The bootloader holds `0x29F00000` and the 0x10020000 / 0x10092000 /
  0x20010000 range constants (`0x14001b0c`, `0x14001cbc..`), as the Stomp's does.
- Still needed: eMMC partition starts for the 17 entries, the POD Go's update-mode button,
  `PRODUCTS` id from the .hxf HEAD.

## Design: NAM in the fixed amp slot (proposed)

POD Go model costs (firmware table, `work/model_inventory.csv`): amps 750..3100
(Line 6 Elmsley 3100), cabs 250..600, 1024-sample IR 250. NAM A2 Lite declared 2275 on the Stomp,
so a NAM model taking an **amp's** identity would sit inside the DSP the fixed amp block already
reserves: no JSON preset edits and no change to the 9000 admission limit. The cab slot can still
hold a real cab or IR. Raising the 9000 limit adds no DSP power and risks audio drop-outs; JSON
preset edits (removing fixed blocks) release only what those blocks reserved.

**Decision (2026-11-07):** NAM A2 Lite goes in the amp slot, on **Brit Plexi Brt**'s identity
(amp, firmware id 0x11c, cost 2550; Brit Plexi Nrm and Jump stay). Rig: Drive -> NAM -> cab block
(cheapest cab or 1024 IR, switched off for full-rig captures) -> Delay -> Reverb. Normal presets
keep using stock amps with the cab on. Donor is a build parameter, easy to change.

## RAM run on the POD Go: tool status

`tools/hxf_ram.py` now knows the POD Go (product 0x0007, app CRC 0xe0891668, hook addresses above).
`plan` passes all application checks for stock 2.50 (699 KiB, no overlay). The POD Go's eMMC
layout comes from `hxf_ram.py layout --stock ...` (read only, needs the loader running), saved to
`podgo/emmc_layout_podgo_2.50.json`; until then only the stock application can be run from RAM.
The unit's USB interface 0 is vendor class with bulk EP 0x81/0x01, as the Stomp's
(`hx_dfu_reboot.py --pid 0x424b`). Device steps:

1. Quit POD Go Edit and Line 6 Updater.
2. `python3 tools/hx_dfu_reboot.py --pid 0x424b` (unit restarts into update mode, 1fc9:000c)
3. `dfu-util -d 1fc9:000c -a 0 -D tools/ramboot/firmware-ramboot.dfu`
4. `python3 tools/hxf_ram.py info` (SDRAM test, eMMC start)
5. `python3 tools/hxf_ram.py layout --stock ../POD_Go_v2.50.0_0x6e984472.hxf`
6. `python3 tools/hxf_ram.py run ../POD_Go_v2.50.0_0x6e984472.hxf --stock ../POD_Go_v2.50.0_0x6e984472.hxf`
   (stock from RAM: proves the loader and hook)
7. Power-cycle: back to the installed firmware.

## RAM run on the unit: results (2026-11-07, **on unit**)

- `hx_dfu_reboot.py --pid 0x424b` puts the POD Go in ROM DFU (1fc9:000c) every time, from the
  installed app and from a RAM-run app. The loader's own 'D' (back to DFU) does **not** work on
  the POD Go: it dropped off USB and needed a power-cycle. Use the app route.
- Loader: SDRAM test passes, core 204 MHz, EMC 102 MHz (stock sdram.h unchanged).
- eMMC: the Stomp loader stops at 0x10B. Diagnosed: after CMD7 (sent without waiting for a
  response) the first CMD13 times out (RTO 0x100). Fix: send CMD7 expecting its R1b reply, wait
  5 ms, retry CMD13 (`EMMC_CMD7_R1B` in `src/ramboot/emmc.h`; `make -C src/ramboot podgo` ->
  `tools/ramboot/firmware-ramboot-podgo.dfu`, builds with Homebrew `arm-none-eabi-gcc`). With it:
  eMMC up, 0x720000 sectors (3.56 GiB). The Stomp loader is unchanged.
- **Stock 2.50 runs from RAM** through the hook (`hxf_ram.py run STOCK --stock STOCK`), back on
  USB as 0e41:424b with audio, ~8 s after GO.
- eMMC layout (`podgo/emmc_layout_podgo_2.50.json`, payload sectors, each after a 1-sector
  sub-header): E0 0x1, E1 0x8002, **E2 0x8803**, **E3 0x8c04**, **E4 0x940d**, E5 0x11006,
  E6 0x11039, E7 0x1109e, E8 0x11167, E9 0x1dc12. E10 (132 bytes) cannot be matched by sector CRC;
  E11..16 lie beyond 0x40000 sectors past E9 (not needed: NAM changes only E0, E2, E3, E4).
  Room: E2 0x80000 (512 KiB, as the Stomp), E3 0x101000, E4 0xf7f000.
- Entries 2, 3 and 4 on the card match stock 2.50 sector for sector (the check `run` makes).

## DSP memory map (static, 2026-11-07)

`python3 podgo/dsp_memory.py POD_Go_v2.50.0_0x6e984472.hxf` reproduces this. The VISA decoding
fix (high half of each LDR word is the earlier parcel) is **verified** by finding the IR store
addresses in the IR copy code. Static only: allocations no constant names are not seen.

Internal (normal words):
- **Block 2**: boot zeroes/inits `0xc0000..0xc08e4`; code names `0xc0000..0xc0504`. Nothing above
  `0xc08e4` is named: **~30,500 words unused**.
- **Block 3**: boot zeroes `0xe0000..0xe2560` (heap `0xe08fe..0xe174f`, buffers `0xe1750..`,
  `0xe2098`, `0xe2218`). Nothing above `0xe2560`: **~23,200 words unused**.
- The Stomp kernel's windows (PM `0xc4ef8..0xc5554` = normal `0xc7674..0xc8000`, DM `0xc7cd7..`,
  Block 3 `0xe4842..0xe8000`, PM `0xe5486..`) all fall inside these unused tails, so the Stomp
  layout can be kept unchanged on the POD Go.

SDRAM (zero-filled regions set up by the boot code at `0x16cec9..0x16e1e6`):

| range | what |
|---|---|
| `0x200000..0x202fb0` | primitive registry and init data |
| `0x204400..0x25c3f2` | **Blob 0 buffer**: `R0 = 0x57ff1` (size) at `0x16aaad`, `R0 = 0x204400` at `0x16aab5`; exactly stock Blob 0 (0x57ff1 words), no headroom |
| `0x25c3f2..0x2673fc` | region A (`M3`/`I3`/`R4` at `0x16cf9d`/`0x16cfa7`/`0x16cfb0`), 0xb00a words |
| `0x2673fc..0x26758e` | region B (IR slot metadata?) |
| `0x26758e`, `0x26760e..0x2a760e` | User IR ready flags, 128 x 2,048 IR pool |
| `0x2a763c..0x2c31f6` | six buffers (`0x16e143..0x16e1e6`) |
| **`0x2c31f6..0x300000`** | **no constant names it: ~249k words, candidate free** |
| `0x300000..0x30a673` | external code (LDR tag 10) |
| `0x310000..` | heap (`M0`/`R4` at `0x16cf32`/`0x16cf45`), end not an immediate |

Consequences for the build (same shape as the Stomp's `expand_sharc_blob0_buffer`):
- The NAM composite grows Blob 0 by 2,150 words (cloning Line 6 Clarity's composite
  `0x600114`) or 6,311 (Brit Plexi's `0x6000cf`). Enlarge the buffer size immediate and move
  region A (start `M3` and `R4`, end `I3`) into the free gap, e.g. `0x2d0000..0x2db00a`.
- The kernel's static SDRAM window (Stomp DDR2 `0x324500..0x328000`, 0x3b00 words) must move:
  on the POD Go `0x324500` lies in the `0x310000` heap. Candidate: `0x2f0000..0x2f3b00` in the gap.
- Entry 4 has 620 blobs (Stomp 864): `add_model_entry4`'s hard-coded 864 must become per-device.
- Runtime check still needed: the first NAM RAM run plus a preset sweep (as
  `docs/research/STOMP_TEST_A_PRESET_SWEEP.md`).

## DSP-side build (2026-11-07)

- Kernel: `tools/sharc/nam_multi.py --mid-sweep --podgo -o build/nam_lite_podgo.asm --check`.
  `--podgo` sets the IR store (`0x26758e` / `0x267e0d`) and the shared SDRAM table
  (`0x2f0000..0x2f3b00`, uses `..0x2f07e6`). Simulator check **passes** (exit 0, bit-exact; steady
  worst 30,347 instructions a call, as the Stomp build). Same internal layout as the Stomp:
  PM `0xc4ef8` (1,096 instructions), cold PM `0xe5414` (309), DM `0xc7ce0..`, `0xe4850..`.
- Entry 2: `podgo/podgo_e2.py IN OUT --asm build/nam_lite_podgo.asm`: Blob 0 buffer
  0x57ff1 -> 0x5fff1 words, region A -> `0x2d0000..0x2db00a`, kernel LDR blocks, primitive
  0x9c75 -> kernel. Entry 2 0x62150 -> 0x68268 bytes. `l6ia_verify.py`: ALL OK.
  `tests/test_podgo_e2.py` (with `PODGO_HXF=...`): 5 pass.
- **On unit:** this Entry-2-only build (no NAM model yet) ran from RAM: eMMC check passed, the
  app came back on USB after 8.1 s. Listening test pending.
- Input calibration: `STOMP_DBU` (11.5 dBu) is the Stomp's; the POD Go's input level at 0 dBFS
  is not measured yet.

**On unit (2026-11-07):** the Entry-2-only build from RAM sounds and behaves normally across
presets (owner's listening test).

## Main-app plan: NAM on Brit Plexi Brt in place (proposed)

Following `tools/effects.py` (the HX Effects build takes Xenomorph Fuzz Mono's identity in place):
Entry 4 a NAM host graph cloned from an amp composite (Line 6 Clarity `0x600114`) with primitive
0x9c75; Entry 3 NAM's descriptor written onto model 74 (`HD2_AmpBritPlexiBrt`, name index 0x11c);
Entry 0 the cost row (Table at `0x28001e10`, rows `{name index, preset id, cost}`), the name row,
the browser item, and later the IR-name title.

POD Go Edit (`/Applications/Line6/POD Go Edit.app/Contents/Resources/amp.models`) defines Brit
Plexi Brt as 12 float knobs, 0..1: Drive, Bass, Mid, Treble, Presence, Ch Vol, Master, Sag, Hum,
Ripple, Bias, BiasX. Per `docs/research/HX_EDIT_DROPS_NAM.md`, the editor rewrites values in its
own types and ranges, and the unit drops the whole preset on a type mismatch. Editor-safe layout:
NAM keeps those 12 floats 0..1 and the kernel decodes them:

| Plexi knob | NAM | decoding |
|---|---|---|
| Drive | Input | as now |
| Bass, Mid, Treble | Bass, Mid, Treble | as now |
| Presence | High Cut | as now |
| Ch Vol | Output | as now |
| Master | Model | slot = round(v x 127) + 1 |
| Sag | Mid Freq | 150..3000 Hz, log |
| Hum | Q | 0.7 / 1.4 / 2.8 by thirds |
| Ripple | Polarity | inverted above 0.5 (editor default 0.5 = Normal) |
| Bias, BiasX | (unused) | ignored |

## First NAM image (2026-11-07)

- Kernel `--mid-sweep --podgo --plexi`: simulator check passes (exit 0); Polarity inverts above
  0.5 (checked at 0.5 normal, 0.51 inverted). 1,097 hot instructions (Block 2: 1 word left).
- `podgo/podgo_model.py`: Entry 4 blob 620 on composite 0x600129 (a Line 6 Clarity clone, member 1
  primitive 0x9c75, DM 0x303 / PM 0x147 / SDRAM 0x5000; Amp harness 0x600007's placeholder SDRAM
  0x800 -> 0x5000); Blob 0 0x58857 words. Entry 3 model 74 keeps its name and id, NAM's 12 knobs in
  Plexi's slots and types, slot lists as stock.
- `python3 podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf` -> `build/POD_Go_v2.50.0_NAM_A2_Lite.hxf`
  (payload MD5 91eb6d92b809cc998c1e83dee5ae6428), `l6ia_verify` ALL OK. Entry 0 unchanged: listed
  as Brit Plexi Brt.
- Open question for the unit: does POD Go Edit keep all 2,048 samples of an imported IR? The kernel
  reads words up to 1,950. If Edit cuts to 1,024, the block stays silent.

## Order of work

1. Port the RAM loader (`hxf_ram.py`, `src/ramboot`) to the POD Go: safest way to test on the unit.
2. On unit, from RAM: probe heaps and SDRAM use; pick kernel and ring windows.
3. Kernel: `nam_multi.py --podgo` (IR addresses, memory windows), simulator check.
4. Entry 0 tables, Entry 3/4 model, hook; build `POD_Go_v2.50.0_NAM_A2_Lite.hxf`.
5. Test from RAM, then install with Line 6 Updater (owner approved flashing with a backup).

## Boot hang found and fixed (on unit, 2026-11-07)

The first NAM image stopped at the Line 6 splash. From RAM, Entry 2 always the NAM one:

| Entry 4 change | result |
|---|---|
| none (stock) | boots, plays normally |
| full (reference `add_model_entry4`: appended directory) | splash |
| full, stock layout | splash |
| Blob 0 grown only (v2) | **boots** 8.6 s |
| blob 620 added only (v3) | **boots** 8.6 s |
| Blob 0 grown + Amp harness placeholder SDRAM 0x800 -> 0x5000 (v6) | **splash** |

So the enlarged Blob 0 buffer works, an extra blob is accepted, and raising the Amp harness's model
SDRAM hangs the POD Go at boot. Fix: the harness stays stock (NAM's member asks for no SDRAM) and the
kernel's far rings, HIST and sentinels sit at fixed SDRAM per kernel slot,
`0x2d0000 + k x 0x8000` (`nam_multi.py --static-sdram`; simulator check passes, the DMA check
bounded to the slot's own area). Region A moved to `0x2c4000..0x2cf00a` to make room. Entry 4 is now
rebuilt in the stock layout (`podgo_model.entry4`), as the images that booted.

## UI hang: no 621st blob or model (on unit, 2026-11-07)

"On USB" is not enough: the pedal's own checks matter. With the NAM Entry 2, these reached USB but the
buttons, screen and POD Go Edit's preset load hung (the update service still answered): the full
build, Entry 4 alone (test D), and **one extra blob (620) that nothing names** (v3). So the POD Go's
application cannot take a 621st blob. Fix: NAM's host blob replaces the donor's own blob 74 (no other
model uses it) and Entry 3 drops the copy's descriptor, so both stay at 620. Built, on USB in 8.6 s;
button test pending.

## Correction: the UI hang was Entry 2's region A at 0x2c4000 (on unit, 2026-11-07)

Every UI-hang test above (full, D, v3, v2, in-place, zero-growth) carried the same Entry 2, with
region A moved to `0x2c4000` to make room. That Entry 2 alone, with stock Entries 3 and 4, froze the
buttons too; the same Entry 2 with region A at `0x2d0000` worked. So `0x2c4000..` is used at run time
by something no constant names, and the "621 blobs" and "grown Blob 0" conclusions are **not**
established (they were never tested without the bad region A). What still stands: raising the Amp
harness's model SDRAM to 0x5000 stops the unit at the splash (that test had region A at 0x2d0000).

Now: NAM's host composite overwrites unused composite 0x60011c in place and model/blob 74 are reused,
so Blob 0, the blob count and the model count stay stock, and Entry 2 needs **no** buffer or region
change (`podgo_e2.GROW_BLOB0 = False`: stock code untouched, only LDR blocks added). NAM's SDRAM at
the top of the gap: per-slot `0x2e0000 + k x 0x8000`, table `0x2f8000..0x2f884b` (below the external
code at `0x300000`). Simulator check passes. Full build on USB in 8.6 s; button test pending.
Whatever owns `0x2c4000..` may grow toward NAM's areas with heavier presets: a preset sweep is needed.

## Block size: the POD Go calls with 32 samples (2026-11-08)

- On the unit (RAM build, Brit Plexi Brt slot = NAM, cab off), recorded over USB (1/2 processed, 3/4 dry,
  `podgo/record_podgo.py`): the output alternated every 16 samples between the kernel's output and the
  dry input x 0.71 (sample-exact, no lag). An empty slot (Master 0.9) played 16 samples of silence, 16 of dry.
  So the POD Go calls the amp primitive with **32 samples** (the HX Stomp: 16); the kernel did only the
  first half, and the model saw every other 16 samples (garbled tone, an idle whistle).
- Fix: `nam_multi.py --block32` adds NAM_ENTRY32 (cold code): it keeps I1-I3 at WRAP32 0xE7FF0..2 (above
  COLD_END, below the prof stamps), calls CUSTOM_AMP_ENTRY, then I1 += 16, I2 += 16 and jumps to it again.
  `podgo_e2.py` points primitive 0x9c75 at NAM_ENTRY32 when present (0xe553f); `build_podgo.py` uses it.
- Check: the full KernelCheck passes, plus `check_block32`: two rigs from one seed, 120 calls of two
  instances (claim, load, play), 16+16 vs 32: bit for bit.
- On the unit: no 16/32-sample structure left (residual flat over phase mod 32). Against the numpy A2
  reference on the dry channel (a clean A2 Lite capture with cab, slot 4), after a 64-tap linear fit: -18.5 dB at +6 dB
  input (-14.0 dB at 0 dB; the dry signal itself fits to -13.0 dB). Before the fix: -0.4 dB.
  Open: input calibration (STOMP_DBU is the Stomp's 11.5 dBu) and the tone stack settings in the comparison.

## Input level (2026-11-08)

No published POD Go figure (Line 6 lists none; the forum measurements are Helix/HX Stomp, about
+11.4..11.5 dBu at 0 dBFS). The user has no meter or reference interface, so the kernel keeps
STOMP_DBU = 11.5 dBu (the Helix family's figure). Input (Plexi Drive) trims it by ear: 0.4 dB a step,
+-20 dB, 5.0 = 0 dB. The USB comparison (a clean capture, near linear) fits best with about +6 dB more
input, but the fit is flat (-16..-18.5 dB from +3 to +12 dB): not a measurement.
To measure later: a 200 Hz sine from the Mac's headphone jack, its AC volts read on a meter, then
into the guitar input, read as dBFS on USB 3 (podgo/record_podgo.py); 0 dBFS = dBu + (-dBFS).

## Names on the unit, and the donor amp (2026-11-08)

- Entry 0 holds a model's name twice: its amp browser item (48 bytes, name at +14, 26 chars) and its
  Table 2 row (44 bytes, short name at +4, 16 chars, then kind and 3 knob counts). `podgo_model.entry0`
  finds both by name index and stock name and writes "NAM A2 Lite". Knob names are not in Entry 0: the
  unit shows Entry 3's (Input, High Cut, Output, Model, Mid Freq, Q, Polarity): checked on the unit
  with the Plexi donor.
- The donor is a build option (`build_podgo.py --donor elektrik|plexi`), default **Line 6 Elektrik**
  (model 46, name index 0xda, own blob), so Brit Plexi Brt stays a normal amp. Elektrik has 11 float
  knobs (no Hum): Sag = Mid Freq, Ripple = Q, Bias unused, BiasX = Polarity (POD Go Edit's default
  Bias 0.6 would invert; BiasX 0.5 is normal). The kernel is unchanged (it reads by pid).
  `--donor plexi` reproduces the earlier build exactly (payload md5 d1909d4c...).
- POD Go Edit keeps its own model list (amp.models): it still names the block after the donor.

## IR length on import (2026-11-08)

Question: does POD Go Edit / the unit keep only 1,024 samples of an imported IR (POD Go IRs are
1,024-sample)? A NAM IR needs 8 + 1,871 + 72 samples. Offline check against the unit's recording
(`build/rec_b32_slot4.wav`, a clean capture in slot 4): the full model fits the output to -18.6 dB; the same
model with every word past IR sample 1,024 zeroed (855 weights: the later layers) fits only to
-6.1 dB. So the unit plays the whole model: the import keeps at least the ~1,950 samples used.

## Preset sweep (2026-11-08)

`podgo/preset_sweep.py` (the Stomp's Test A): per user preset (setlist 1, 128), select it, 2 s, write
the test preset into the edit buffer (NAM on Elektrik's amp block, preset id 27, Model 0.03 = IR slot 4,
every other block off), 1 s, record 3 s of USB 1 with the guitar silent. Nothing saved.
POD Go protocol: hx_ctl works with --pid 0x424b (12-entry block list: input, 10 blocks, output; the amp
block kind 17). A preset write after a full preset read on the same connection stalls ("device window
closed"): the sweep opens a fresh connection per step.
Forward 0..127 on the Elektrik build (payload md5 e82d814a): 128 loaded, 0 flagged. Baseline mean
5.314e-4, sd 1.5e-7; max |mean - baseline| 2.9e-10, max sd 1.52e-7, max peak 7.2e-7.
Not covered: NAM beside stock blocks, knob moves after a preset change, POD Go Edit drags, a long run.
Open: Elektrik's Table 1 DSP cost is 1825 (Plexi 2550; NAM declared 2275 on the Stomp): the unit may
admit presets heavier than the DSP can run with NAM in them.

## DSP clock and NAM's cost (2026-11-08)

- `nam_multi.py --meter 1` (cycles of a call, read from USB with the 0.5 marker at exactly 0.500, so unity
  gain): a 16-sample half-call takes 37,075 cycles (median; 99%: 44.5k; max 50.2k). The Stomp: 41.3k.
- `--meter 4` (new: the cycles between consecutive calls' starts; a pair of halves is one 32-sample period):
  262,145 cycles a period, so the POD Go's SHARC runs at **393.216 MHz** (16 x 24.576 MHz), not 450.
- NAM = 74,150 / 262,144 = **28.3%** of the DSP a period (99%: ~34%).
- Cost: at the Stomp's ~13 cycles a unit per 16 samples (26 per 32), 2,852 units. Entry 0 Table 1
  (0x28001e10) row of name index 0xda (Elektrik, preset id 27): 1825 -> **2850** (`podgo_model.DSP_COST`).
  POD Go Edit's DSP meter still uses its own 18.25 for the block; the unit's admission is the 2850.
- Build payload md5 db97facd (Elektrik donor, cost 2850, block32 kernel; full check passes).

## Release candidate (2026-11-08)

`release/POD_Go_v2.50.0_NAM_A2_Lite_Elektrik.hxf` (payload md5 db97facd...): Elektrik donor, cost 2850,
block32 kernel. On the unit from RAM: sounds right (owner), names and knobs right, 128-preset sweep clean,
heaviest admissible preset (NAM + drive + delay + reverb + more) clean. Changes Entries 0, 2, 3, 4 only;
the bootloader (Entry 1) is untouched, so update mode (hold Page > at power-on) and the stock .hxf recover.

## Installed (2026-11-08)

The owner installed `release/POD_Go_v2.50.0_NAM_A2_Lite_Elektrik.hxf` (file md5 61920a6c...) with Line 6
Updater. After it: 128 presets present, NAM (preset id 27) loads, its idle output mean 5.314e-4 as in
every RAM run (slot 4). Recovery stays: Page > at power-on, stock .hxf.

## Phase 2: fixed blocks (2026-11-08, edit-buffer tests on the installed NAM firmware)

Blocks are an ordered chain of 10 positions (preset[0][22][1..10]); a block's type is its kind (body key 9):
1 mono effect (drives, mods, and also the stock wah 239 and volume 224), 8 stereo effect (delays, reverbs),
9 FX loop (119), 17 amp, 15 amp's cab (125), 26 cab/IR, 23 EQ (470..472). "Fixed" blocks are only the
stock presets' contents: the owner's jailbreak presets ("6 blocks free", "FREEDOM" = all 10 empty) load.
`podgo/phase2_try.py` writes chains on FREEDOM's base and reads back what the unit kept (nothing saved):

| test | blocks | cost | kept |
|---|---|---|---|
| NAM + 3 | 4 | 5475 | yes |
| 5, 6, 7 cheap effects | 5..7 | 1525..2175 | yes |
| 8 cheap effects | 8 | 2325 | **no** (whole chain dropped) |
| NAM + 7 cheap effects | 8 | 5025 | yes |
| NAM + 4 (heavy) | 5 | 7975 | yes |
| NAM + 6 | 7 | 7700 | yes |
| NAM + 5 / + 6 / + 7 | 6..8 | 8500..9125 | **no** |
| two amps / two EQs / two cabs / two FX loops | | | **no** |
| two wahs + two volumes | 4 | 972 | yes |
| NAM + cab/IR | 2 | 3100 | yes |

Rules on 2.50 (edited presets, no firmware change): every block can be removed; at most one each of
amp (17), cab (15/26), EQ (23) and FX loop (9); up to 7 effects of kinds 1 and 8 (wahs and volumes
count as ordinary effects); blocks' Table 1 costs up to about 8,000..8,500 (7,975 kept, 8,500 dropped).
A rejected chain is dropped whole. Stock fixed blocks hold 150 (volume) + 336 (wah) + 200 (loop) +
250 (cab) + 300 (EQ) = 1,236 units; leaving them out frees them for effects.
Firmware candidates: EQ models as ordinary effects (kind 23 -> 1/8: several EQs), a higher effect count,
a second amp or cab (DSP harness memory to check). The 9,000 budget itself is the DSP's real limit.

### EQs as effects (2026-11-08)

- The unit re-types a block from the model's browser item type (btype = preset kind): an EQ block sent as
  kind 1 or 8 comes back as 23, and two kind-23 EQs are still refused.
- The fixed EQ block's models are `HD2_EQ_STATIC_*` (browser items 0x17fa3.., btype 23). Five of them also
  exist as ordinary effects, in the effects browser's EQ list (items 0x152d3.., btype 1): Simple EQ (preset
  id 116, cost 200), Low and High Cut (114, 225), Low/High Shelf (445, 225), Tilt (447, 200), 10 Band
  Graphic (113, 300). Same host composites and blob sizes as the STATIC ones (0x600009, 0x60005c).
- On the unit: Simple EQ + 10 Band + Low/High Cut (as effects) + the fixed Parametric in one chain: kept;
  NAM with an effect EQ before and after: kept. So several EQs need no firmware.
- Only Parametric and Cali Q Graphic exist as STATIC (fixed EQ) only. `HD2_EQParametricStereo` (model 1)
  has a graph but no browser item and a zero Table 1 row. Making them effects means new browser items
  (a grown list: the kind of Entry 0 growth that has hung this unit) or re-typing the STATIC items, which
  would make stock presets' fixed EQ count as an effect (a 7-effect preset + EQ would then be dropped).

## Splash screen (2026-11-08, found, not changed)

The boot screen's background is in **Entry 1 (the bootloader)**: 480x272 RGB565, little-endian, at payload
offset 0x579c..0x4539c (pointer 0x1400579c at 0x20dc; the bootloader runs at 0x14000000). 19 colours: the
red glow and the black shape; the Line 6 logo itself is not in it (drawn from somewhere else).
Exported: `splash/POD_Go_splash_original_480x272.png`. Every build so far leaves Entry 1 alone, which is
what keeps update mode (Page > at power-on) and recovery working. Before writing Entry 1: find whether
Line 6 Updater rewrites it, what checks it, and whether the LPC43xx ROM's USB DFU (1fc9:000c) is still
reachable with a bad bootloader.

### The app's splash graphics (2026-11-08): the safe route

The full boot screen (logo, "POD GO", "How-to videos" line) is an app graphic, not the bootloader's:
Entry 7 is the graphics index (546 names, null-separated from 4404; 48-byte records from 12812:
word 2 = Entry 8 index, words 5/6 = width/height, word 7 = 16 bpp, masks 0xf807e01f = RGB565), Entry 8 the
pixels (count at word 2, then {size, offset} pairs from byte 24; raw RGB565, rows mirrored left-right).
`Splash` (record 307, Entry 8 offset 0x1d0398), `Splash_Wireless` (328, 0x261cdc), `Splash_Bootloader`
(314, 0x212218): 480x272 each. The app draws "Firmware 2.50.0" over the bottom (E0 string at 0xa0762).
Replacing the pixels in Entry 8 changes no size or offset and leaves the bootloader alone; the bootloader's
own background frame (Entry 1, above) still shows first, briefly. Exports in `splash/` (gitignored: Line 6
artwork, never published).
- 2026-11-08: the owner's "NAM A2 Edition" Splash_Wireless (`podgo/splash.py`, `build_podgo.py --splash-wireless
  IMG`) ran from RAM and showed at start-up. Only Entry 8's splash bytes change (0x261cdc..0x2a1adc).
  `tools/hxf_ram.py` now also knows the installed NAM release's app (crc 0xa2399a2e: same code, its data
  segment differs), so RAM runs work with `--stock release/POD_Go_v2.50.0_NAM_A2_Lite_Elektrik.hxf`.
- Release `release/POD_Go_v2.50.0_NAM_A2_Lite_Edition.hxf` (file md5 70472599..., payload 83191dbd...): the
  installed NAM release plus both owner splash screens (`--splash`, `--splash-wireless`). Against the installed
  release only Entry 8's two splash regions differ; full kernel check passes. Personal build: contains Line 6
  artwork, not for publishing.
- 2026-11-08: correction: the Edition release was NOT installed then (the owner pressed the wrong button). The
  check run after it (128 presets, NAM loads, idle mean 5.3142e-4) cannot tell the two releases apart: only Entry 8
  differs. Its app data segment equals the Elektrik release's, so `hxf_ram.py` knows both.

## NAM preset templates (2026-11-08)

`podgo/make_templates.py BASE.pgp OUT_DIR` writes POD Go Edit presets from a POD Go Edit 2.x export (the owner's
"Freed Preset.pgp"): NAM Blank (volume, NAM: 3,000 units), NAM Essentials (volume, wah, Minotaur, NAM, Simple
Delay, Plate: 5,411), NAM Full Board (volume, Deluxe Comp, Minotaur, NAM, Simple EQ, Chorus, Vintage Digital,
Hall: 7 effects, 6,725). No cab, FX loop or fixed EQ. Each chain was written to the unit's edit buffer and
kept whole. .pgp layout learned from exports: @type 0 effect, 1 amp, 5 stereo delay/reverb/mod; footswitch
@fs_index 1..6 = FS A..F, 9 = the expression pedal (volume on controller 2, wah on controller 1 with the toe).
Model is stored 0..1: 0.03 = IR slot 4 (shown 0.3). Gotcha: Entry 3 int params' defaults are int bits in a float
word (Ratio 3 reads 4.2e-45): convert by type (2 int, 1 bool) or the unit drops the chain.

## Block helper (2026-11-08)

`podgo/blocks.py` (status / list / add / remove / restore) edits the unit's edit buffer: any model, including the
amp, cab/IR and FX loop categories the unit only offers on fixed blocks. Tested on FREEDOM: NAM, then a modern
cab (1x12 Cali EXT, kind 26), a legacy cab/IR (kind 15), a Mono FX Loop at block 5 and its removal: all kept;
a second cab and a second amp are refused before writing. Gotchas: a preset stores only knob parameters (a cab
model's type-6 IrData at slot 1001 must be left out, or the unit drops the chain); cab names exist as modern
(26, 250 units) and legacy (15, 600) models, and amp names as amp and preamp (HD2_Preamp*): the helper labels
preamps and picks the modern cab unless `add ir NAME`.
