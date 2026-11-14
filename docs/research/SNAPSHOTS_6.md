# Six snapshots on the POD Go (2.50): first look (2026-11-13)

Read-only study of the stock 2.50 app (Entry 0, code segment 6 at `0x28c58ba0`), compared with the
Helix Floor 3.80 app (8 snapshots). Nothing built or run yet.

## Wanted (owner's design)

Long-press MODE enters a 6-snapshot mode. In it, the six switches select snapshots in order: bottom row
left to right 1-2-3, top row left to right 4-5-6. Bank Up/Dn act as snapshot switches too (exact role to settle).

## What the firmware does

- **Snapshot manager object**: `0xd28` bytes, zeroed and built by `0x28cb9130` (called once from
  `0x28c5f914`), vtable `0x28cb7bad`, with a second object at `0x282c6f00`.
- **Four snapshot records of `0x28c` bytes each** live inside that object. `0x28cb7878` sets their
  defaults: `for n in 1..4` (`cmp r5,#5` at `0x28cb792c`) writes the name "SNAPSHOT n" (+0xca in a
  record) and clears 64 seven-byte controller entries per record (stride 7 from +0x18).
- Fields right after the array: `+0xa3c..+0xa47` (three words set to 0x01010101: per-snapshot bytes,
  4 to a word), `+0xa49` count, `+0xa4a`, `+0xa4b` current snapshot, `+0xa4c`.
- **The count 4 is compiled in, not a setting.** About 25 functions in `0x28cb7300..0x28cb9a00` use
  the record size `0x28c` and the tail offsets, with loop limits `cmp #4/#5`
  (`0x28cb7be6 0x28cb7c76 0x28cb7e30 0x28cb80d0 0x28cb8114 0x28cb820a 0x28cb82b0 0x28cb833e 0x28cb83d2
  0x28cb8446 0x28cb85a2 0x28cb953a 0x28cb97a0`) and `cmp #3` (`0x28cb88e2 0x28cb8ad6 0x28cb8b7e
  0x28cb8c96`). Outside that module, `+0xa4b` is read at `0x28c8af14` and `0x28cb62c8`, and `+0xa3c` at
  `0x28ca5168`, `0x28ca5ba0`.
- Helix Floor 3.80 has the same design sized for 8: records of `0x2d4` bytes, loop `+0xc..+0x16ac`
  (8 records), object `0x1a48` bytes (`0x280dc178`, names at `0x280d9a68`). Its code is a later
  refactor, so it is a guide to what changes, not a patch to copy.
- Strings present: "Snapshot Mode Switches", "Snap Up/Dn", "Bank Up/Dn", "Prst Up/Dn" (shared Helix
  menu tables; which ones the POD Go shows is unchecked).

## What 6 snapshots needs

1. **The object**: grow it by 2 x `0x28c` and move the tail fields, or put records 5-6 in a separate
   block of free RAM and redirect the record address calculation (`mla r, #0x28c, idx, base`) to it for
   idx 4-5. The second is far fewer edits. Every loop limit above goes from 4 to 6.
2. **Per-snapshot data held elsewhere**: block bypass and parameter values per snapshot (the 7-byte
   controller entries hold them per record, but bypass may be in the `+0xa3c` bytes: three words of 4
   bytes = 12 entries). Not yet mapped.
3. **Saving presets**: how a preset is written to flash, and whether a preset slot has room for two
   more records. Not yet found. Without it, snapshots 5-6 are lost at power-off.
4. **POD Go Edit**: presets it reads and writes have exactly `snapshot0..snapshot3`. Expect it to drop
   or refuse 5-6. Option: keep 5-6 in their own store on the unit, keyed by preset number, so the
   editor never sees them (survives editing, but not backups or .pgp export).
5. **Footswitches and display**: the long-press on MODE, the 6-switch layout, LEDs and the snapshot
   view's four tiles. New UI code: the largest part.
6. **MIDI**: CC69 snapshot select (values 0-3 plus next/previous) should reach 5-6.

## Plan

A RAM-run build in steps, each tested on the unit before the next:
(a) six records in RAM, selectable through a temporary debug hook, sound changes correctly;
(b) find and extend preset save/load; (c) footswitch mode and display; (d) POD Go Edit behaviour.
Step (a) shows within a day or two whether the core holds; (b) and (d) decide whether it's worth it.

## Step (a) on the unit (2026-11-13, from RAM, stock 2.50 base)

Build: `podgo/snapshots6.py` (stock + `podgo/snap6/snap6.s`): slot 4 is a window for snapshots 4, 5 and 6;
the stock select (0x28cb88a4) and reset (0x28cb7878) are wrapped, CC69 accepts 4 and 5. MIDI from the Mac:
`podgo/snap6/cc69.py N`.
- Booted and ran normally. CC69 1 and 4 work through the wrapper.
- First select of 5: a copy of the current snapshot, named "SNAPSHOT 5" on the 4th tile.
- Sequence 2, 5, 1, 6, 4, 5, 6, 4 (no edits on the unit): 5 came back as 2, 6 as 1, 4 as 4 (owner:
  "I think they matched"; a recheck with very different snapshots would make it certain).
- A preset reload clears 5 and 6 (by design; seen when the owner changed preset mid-test).
Next: (b) saving them with the preset, (c) footswitches and screen, (d) POD Go Edit.

## Step (b): how presets are kept (2026-11-13, read-only)

- **Serializer** `0x28cb916c(mgr, stream, flag)` writes the snapshot section as MessagePack: map(6)
  {6: current, 7: count of 9-byte entries, 8: count of 7-byte entries, 9: 12, 10: **fixarray(4)** (`0x94`
  hard-coded at `0x28cb923c`) of map(8) per snapshot, 13: array(12) block flags}. `flag` changes the
  per-snapshot content (flag 1 adds the raw 171-byte (0xab) str16 of the 9-byte entries).
  Callers: `0x28c8fa6c` (flag 1, from `0x28c960e0`) and `0x28c8feac` (flag 0, from `0x28c95fb4` and the
  editor handler `0x28c8b1a0`). The edit buffer read over USB (`hx_ctl get_preset_blob`, what POD Go Edit
  gets) has key 10 = map6 as above with per-snapshot keys 0,1,2,3,4,5,11,12.
- **Deserializer** `0x28cb984c(mgr, buf, len)` calls the reset (`0x28cb7878`) first, then parses. It must
  not be given 6 snapshots as is (records would land past the four).
- **Storage** is a small numbered-file store, not a FAT: open `0x28c6f8c8(volume, id, mode 0 read / 1 write,
  file)`, read `0x28c6f994`, write `0x28c6fa90`, seek `0x28c6fa04`, close `0x28c6f910`, on top of the
  eMMC write `0x28c6adb8`. Presets are variable-length "l6-helix" MessagePack files.
- Options: (A) put snapshots 5 and 6 in the preset file under an extra key that only the storage
  serialization writes; (B) a separate numbered file of our own. A leaves the file store's own logic
  alone and keeps 5/6 with the preset (and in raw backups, if backups copy the files); B is invisible to
  everything but means creating files ourselves.

## Step (b) built (2026-11-13): option A, inside the preset

- **Which writes**: a save writes the preset twice through the same snapshot writer, `0x28c95fb4` (flag 0,
  store object `0x282b7c44`) and `0x28c960e0` (flag 1, `0x282b7cc0`). Both are called together from
  `0x28c961cc` and `0x28c96470`. The loader finds the snapshot section by the preset's offset table (entry
  `+0x24`) and hands `0x28cb984c` everything from there to the end of the file (`0x28c90290`, `0x28c90540`;
  load buffer `0x282a5e10`, 0x5000 bytes).
- **Format**: only on those two saves (their `bl`s at `0x28c9604a` / `0x28c96176` go through `st_feac` /
  `st_fa6c`, which set a flag), and only when snapshots 5/6 exist, the section starts
  `87 0e c5 LL LL holder mask 00 00 [records] 86 06 ...`: a valid MessagePack map(7) whose first key, 14, is a
  bin holding the stored 0x28c-byte records. The bin's last byte is the stock writer's own map(6) header,
  so the loader hook hands the stock reader the bytes from that `0x86` on, then refills the store.
  POD Go Edit's reads (`0x28c8b1a0`) never set the flag; presets with nothing in the store save byte-for-byte stock.
- Up to two records are saved (the one in slot 4 is saved as snapshot 4 by the stock code): +1.3 KB per preset.
- Offline: `snap6.s` save/load hooks emulated (unicorn) against stubs: editor bytes unchanged, save layout,
  generic MessagePack parse, load restore, stock preset, corrupt length. All pass.
- Not yet: whether POD Go Edit backups copy key 14 (they would if they copy the stored file as is).

## Step (b) on the unit (2026-11-13, RAM, debug build)

- First try lost the whole save: both loaders hand `0x28cb984c` the section from its key byte `0a`, not
  from the map. Fixed (the bin now ends `0a 86`); seen with the debug record (key 15 on editor reads).
- Save and reload then worked: debug record showed both writers wrapped, the extra record written, and
  the load restoring holder + store (`magic 1 restored 1`).
- Switching 5 -> 4 kept 5's change: the stock select only applies what differs from the record it leaves.
  Fixed by lending slot 3 (index 2) the outgoing snapshot during the switch.
- Still open (seen on the unit):
  1. **Edits are written back late.** A block toggled on snapshot 4 isn't in its record until the next
     switch, and then it lands in slot 4, which by then holds 5. When does the stock code write it, and to
     which index? Probe build prepared (record bytes at entry / before / after the stock select).
  2. **Unused snapshots** (record +0x277 = 0) get a copy of the one you leave (stock 0x28cb73dc). With
     every snapshot saved once first, the owner found 4/5 switching right.
  3. **Adding snapshot control to a knob** (here reverb mix on snapshot 1) updates the four records only;
     the stored 5/6 miss the new value (snapshot 4 showed `None`), and switching to 5 then half-failed:
     slot 4 swapped, the stock select didn't complete, and the slot couldn't be selected from the unit.
     The functions that add/remove controller entries (e.g. `0x28cb8040`, loops `cmp lr, #4`) must also
     update the store, or the store must be kept in the same layout by them.

### Later the same day

- **"Edits written late" was the owner's Snapshot Edits = Discard setting.** On stock snapshots 1-4 alone,
  a delay turned on in snapshot 2 was gone after 2 -> 1 -> 2. Unsaved edits never reach a record; save on
  each snapshot (the owner's habit) is what Discard expects. Recall not yet tested.
- **New per-snapshot knobs** (the hang): `0x28cb7944` / `0x28cb8040` / `0x28cb8240` / `0x28cb84a8` add or
  remove a controller entry in all four records. They're now wrapped (`mirror` in `snap6.s`): run as usual,
  then again on `shadow`, a copy of the manager whose records 1-3 hold the store. On the unit: the reverb mix
  made per-snapshot with 5 in use reached the fourth tile (0.14 everywhere), and 4 -> 5 -> 1 switched normally.
- `0x28cb7944` also writes a value into the current record alone when the entry exists (48 calls in that
  test). The shadow's current is now its slot 4 copy (thrown away), so values on the current snapshot can't
  reach the store. Checked on the unit: snapshot 4 saved at 0.0 and held in the store; the same knob turned
  up on snapshot 1 (36 mirrored calls); 4 and 5 still 0.0 afterwards.

## Step (c): the screen (2026-11-13, read-only)

- The footswitch view (`0x28c9a320`) is already a 3x2 grid of six tiles, one per switch: x `0x28ce11dc`
  {5, 123, 302}, y `0x28ce11f4` {111, 181}. Snapshot mode (setting 0x14 = 2) skips tiles 0 and 3 (mask 9 at
  `0x28c9aa82`: Bank Up/Down) and maps tiles to snapshots with `0x28ce12f8` {-, 2, 3, -, 0, 1}; the current
  snapshot's tile is `0x28ce1284` {4, 5, 1, 2}, its highlighted image `0x28ce12a0`, normal images `0x28ce12b0`.
  Names come from `0x28cb8dc4(mgr, idx)`, the current snapshot from `0x28cb8d5c` (26 callers).
- Tile and icon images are whole pictures with the camera badge number drawn in (Entry 7 index, Entry 8 pixels):
  `Play_Snapshot1..4` and `..Sel` (174x64), `Play_BankUp/DownShort` etc (113x64, the left column),
  `Icon_Snapshot1..4` and `..Red` (34x23, top right). There are none for 5 and 6, nor short snapshot tiles,
  and no unused images of those sizes to reuse.
- Entry 8 is followed by entries 9-16 (54 MB): growing it is fine for a real install but too big a change
  for a RAM run. Option: build the new images at build time from the user's own firmware (like the splash
  overlay: never published) and serve ids past 545 from the code cave by hooking the image lookup.
- Images are fetched by `0x28c7d498(id, record)` (48-byte Entry 7 record; fails for id >= count) and their
  pixels streamed through a file object from `0x28c7d5b4(index, {size, offset})` + `0x28c7d608` (Entry 8).
  Extra images can be served from the cave by hooking both (ids past 545, a fake file object).
- Tiles are a flat background plus the camera badge (number drawn in): new 154-px tiles for 1-6 can be made
  at build time from the user's own firmware. Equal widths (owner's choice): x 5, 164, 323.

## Step (c): the footswitches (2026-11-13, read-only)

- Switch ids: top row 0x0c 0x0d 0x0e 0x0f, bottom row 0x10 0x11 0x12 0x13 (0x0c / 0x10 = Bank Up / Down;
  0x0f / 0x13 the right-hand pair, TAP and MODE). Events: [ev+1] id, [ev+4] 1 press, 2 release, 4 hold.
- `0x28cae5bc` dispatches by footswitch mode: `0x28cacbcc`, `0x28cad5b4`, and snapshot mode `0x28cad098`.
  In snapshot mode a press of 0x0d/0x0e/0x11/0x12 looks up `0x28ce239c` {2, 3, -, -, 0, 1} (id - 0x0d) and
  calls select directly (`0x28cad0f2..0x28cad398`). Hook point for six: `0x28cad0e8` (ids 0x0c..0x12 but
  0x0f -> {3, 4, 5, -, 0, 1, 2}), and Bank Up/Down's release/hold actions must be skipped in six mode.
- Hold on 0x13 runs `0x28c5f674` (sets 0x200000 in `0x281257a0`): stock long-press action, to be checked.

## Step (c) built (2026-11-13): six mode, first cut (emulator only)

- Hold MODE (0x0f, top right; the owner confirmed holding it does nothing in stock) turns six mode on or off;
  the release after the hold is swallowed (`fs_hook` at `0x28cae5bc`). In six mode and the snapshot
  footswitch mode, Bank Up / Down select snapshots 4 / 1 (their release and hold are swallowed), and the stock
  handler's table (`0x28cad3f8` -> `sh_fs`) sends 0x0d 0x0e 0x11 0x12 to 5 6 2 3. Six mode off: stock.
- The footswitch screen reads its tile tables through `sh_` copies (nine literal pool words redirected),
  filled on each draw (`draw_hook`): stock, or in six mode equal columns (x 5/164/323, text 82/241/400), all six
  tiles (`mask_stub`), names of 4-6 from slot 4 / the store (`vname`), the current one 4-6 (`cur_virt`).
- New tile images 546..557 (154x64, `podgo/snap6_ui.py`: badges from the user's firmware, 5 and 6 redrawn as
  9x14 pixel numbers) are served by `rec_hook` / `idx_hook` / `open_hook` and a file object over the cave.
  Build outputs holding them stay in build/ (`build/snap6/snap6.bin`, `build/snap6_img/`).
- Emulator: 49 checks pass (steps a-c). Not yet: the top-right snapshot icon for 5 and 6.

### On the unit, then fixes (2026-11-13, evening)

- First runs: holding MODE toggled six mode but nothing used it. Setting 0x14 is "Snapshot Mode Switches", not
  the footswitch mode; 0x28121948 (the screen's object) + 0x3c isn't it either (reads 140). The footswitch page's
  own state is 0x2811ec58 (made with its handler at 0x28c5faf6), +0x3c = 1 stomp / 2 snapshot / 3 preset. With that:
  six switches worked (Bank Down selected snapshot 1) and the screen showed six tiles - but only after the next
  snapshot change, and the LED rings stayed on the stock layout.
- Fixed (emulator only): after the MODE hold the screen is redrawn and pushed out (`0x28c5e938`, as the stock
  handlers do) and the snapshot LEDs updated (`0x28cac230`). The LED routine loops over six (cmp at `0x28cac280`)
  through `sh_led` (pool `0x28cac31c`): stock 6 7 3 4 then the Bank LEDs 2 5 (no colour: off, as stock turns them
  off anyway); six mode 5 6 7 / 2 3 4. Colours of 4-6 from slot 4 / the store (`vcolor` at the two `0x28cb8894`
  calls). The top-right icon: Icon_Snapshot5/6 (+Red) made like the tiles, served as images 558-561; the icon
  tables (0x280110a4/b4/c4/d4, eight pool words) point at six-entry copies, and their three current-snapshot reads
  use the true current one (`cur_true`: 5 or 6 whenever slot 4 holds them, in either mode).
- Emulator: 55 checks; all 43 patched places disassemble as intended.

### Next on the unit (test plan)

1. Snapshot footswitch mode, hold MODE: the six-tile screen should appear at once, LEDs on the six layout.
2. Press each switch: bottom 1 2 3, top 4 5 6; the lit LED and the highlighted tile follow; top-right icon shows
   the number (5 and 6 included).
3. Hold MODE again: four tiles, stock LEDs, Bank Up/Down change bank again.
4. MIDI CC69 values 4 and 5 still select 5 and 6 (`podgo/snap6/cc69.py 5`).
5. Save on 5, reload the preset: 5 and 6 come back (done before; recheck with six mode on).
The test build is a debug build: POD Go Edit must not be connected (editor reads carry the debug key 15).
`podgo/snapshots6.py STOCK.hxf --no-debug -o ...` builds without it (emulator: editor reads are stock bytes;
all 55 checks pass); use that one for an editor test or a real install.

### Unit test (2026-11-14, RAM, debug build 9b00f648): all five steps passed

Six-tile screen and LEDs at once on the MODE hold; all six switches, LEDs, highlight and the top-right icon
right for 1-6; MODE hold back to four tiles, stock LEDs, Bank Up/Down change bank; CC69 5 and 6; save on 5/6 and
reload brings them back. As with 1-4 under Snapshot Edits = Discard, each snapshot's edits need a save while on it,
and a never-set-up snapshot starts as a copy of the one you came from (stock behaviour, not the patch).
Left: (d) POD Go Edit with the --no-debug build; a final memory check before any real install.

### Step (d): POD Go Edit (2026-11-14, RAM, --no-debug build 5e198d45)

- POD Go Edit connected and opened a preset with 4, 5 and 6 set up: normal, four snapshots (the fourth named
  after whichever of 4-6 is in slot 4).
- A change on snapshot 1 saved from POD Go Edit, then a preset reload on the unit: 4, 5 and 6 kept their
  settings. The editor's save goes through the unit's own save path, which writes the store too.
- Not tried: importing a .pgp from the computer or restoring a backup (they send a whole preset: expect 5 and 6
  to be lost, unless the backup copies the stored file as is), and preset copy/paste/move on the unit.

## Memory check for a real install (2026-11-14, read-only)

- **Nothing in the app uses SDRAM above its code.** No pc-relative literal or movw/movt pair in the app code
  (segment 6) names an address from 0x28ce3fb8 up; scanning every Entry 0 segment for words in
  0x28ce3fb8..0x2a000000 finds only instruction pairs that read as such numbers (0x28fff0f0 in segment 4 is the
  `udiv` at 0x2800015c; 0x28d1f8xx in segment 6 are `ldrb.w`), none loaded as addresses. The app's own areas end
  below its code (heap 0x283950c4..0x28b950c4, buffers to about 0x28c56b9c). Matches the 2026-11-07 RAM loader
  notes (nothing in 0x29000000..0x29F00000; the bootloader keeps its own variables at 0x29f00000).
- **The bootloader allows it.** Entry 1 checks every app segment's range (0x14001c64): 0x10000000..0x10020000,
  0x10080000..0x10092000, 0x20000000..0x20010000 and 0x28000000..0x29f00000. Segment 6 with the cave ends at
  0x28d20320 (about 1 MB below the limit); no other size check seen.
- **eMMC room.** Entry 0's payload starts at sector 1 and Entry 1's at 32770 (`podgo/emmc_layout_podgo_2.50.json`):
  a 16 MB slot for Entry 0, which grows from 698 KB to about 940 KB.
- Shrinking the tile images (they are mostly flat background; about 30 KB if drawn from the badges at read time)
  is possible but not needed for any limit found; left as an option.

### Where 5 and 6 survive (2026-11-14, RAM, --no-debug build, POD Go Edit connected)

| Action | 5 and 6 |
|---|---|
| Save on the unit, reload | kept |
| Save from POD Go Edit (edit on snapshot 1) | kept (the unit's own save path writes them) |
| Save to another slot on the unit | kept |
| Copy / paste in POD Go Edit's preset list | lost (the editor copies its four-snapshot view) |
| Export .pgp, import | lost |
| Backup / restore | not tested (owner skipped; a restore in a RAM run would overflow the 2 MB write pool) |

So: to copy or move a preset that uses 5 and 6, save it to the new slot on the unit itself.
