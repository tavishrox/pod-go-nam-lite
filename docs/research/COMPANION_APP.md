# Companion app (WebUSB): what the POD Go's USB services offer (2026-11-15)

Goal: a web page (WebUSB, Chrome/Edge) that backs up and restores presets *with* snapshots 5 and 6, edits
snapshot names and LED colours (1-6), and later edits patches. Protocol layer: `tools/hx_ctl.py` (editor
service 6, librarian 2, notify 4; MessagePack requests {0x66 seq, 0x64 cmd, 0x65 params}).

## Command table (app 2.50, segment 6)

Each command is registered by a small stub (`push {r4,lr}; ... movs r0,#cmd; ...; bl register`) followed by
two literals: the handler and its parameter decoder. 120 stubs; the numbered ones, by handler group:

- Librarian (stubs 0x28c89dxx..0x28c8a2xx): 01-12, 67-71. 01 = preset list (known). 0x6a {0x6b: n} streams
  a settings group (tried with n = 1: 8 messages, 756 bytes, global settings and setlist names "Factory",
  "User"; no presets). 6f, 70, 71 open / write numbered files (not tried).
- Editor (stubs 0x28c8c4xx..0x28c8d0xx): 14-65. Known: 14 load preset, 15 set edit buffer, 16 get edit buffer
  (handler 0x28c8b1a0 -> serializer 0x28c8feac, flag 0), 17 current preset, 2b move block.
  **45, 46, 47** share handler 0x28c8ac74, which reaches the unit's own save (`0x28c96470`, and through it both
  snapshot writers `0x28c95fb4` / `0x28c960e0`): POD Go Edit's save. A save from the editor already keeps
  5 and 6 for that reason (confirmed on the unit, step d).
- Full list with handlers: produced by scanning segment 6 for the stub pattern (`bd10b004` epilogue, `movs r0,#n`
  before `strd`), kept with the session notes; re-run the scan to regenerate.

## What that means for the app

- Read: 0x16 (get edit buffer) never carries 5 and 6: our serializer hook only adds key 14 on the unit's two
  save writes. A backup through the editor service (load each preset with 0x14, read with 0x16) gets
  everything but 5 and 6.
- Write: 0x15 (set edit buffer) then 0x45/46/47 (save) goes through the unit's save path, so whatever is in
  the six-snapshot store when saving is written. Whether 0x15's parser reaches our loader hook (key 14) is
  not known yet.
- So a full backup/restore of 5 and 6 needed a small firmware addition to snap6.s (done, below):
  1. 0x16 carries key 14 when the app asks for it (a request flag only the app sends), so POD Go Edit's reads
     stay stock;
  2. 0x15 with key 14 refills the six-snapshot store, so the following save writes 5 and 6.
  Snapshot names and LED colours for 5 and 6 live in the same records (name +0x27e, colour +0x27c), so the
  same two paths cover them.
- Without the addition the app can still back up and restore everything POD Go Edit can, and edit names and
  colours of snapshots 1-4.

## Built and tried (2026-11-15, RAM over the installed ToneShift Edition Names Snap6 build)

`snap6.s` `app_dec` replaces command 0x16's parameter decoder (stock 0x28c88821 = `movs r0,#0; bx lr`, literal at
0x28c8d06c) and sets state+5 only for the parameters `81 7a 01` ({0x7a: 1}); `app_rd` replaces its handler
(literal 0x28c8d068, stock 0x28c8b1a1) and, when state+5 is set, raises the "storing" flag (state+4) for that
read, so the serializer hook writes key 14 exactly as a save does. Emulator: 55 old checks and 6 new ones pass.

On the unit (`podgo/snap6/app_probe.py`), preset 45 NAM Essentials on snapshot 1:
- read without the marker 3,603 B, no key 14 (stock); with it 4,917 B, key 14 holding the stored records of
  snapshots 4 and 5 (snapshot 6 was the one lent to slot 4);
- snapshot 5 renamed to "APP TEST" in that blob and sent with 0x15: read back as "APP TEST", and tile 5 on the
  unit's six-snapshot screen showed it. Not saved. So 0x15's parser reaches the loader hook: no write-side
  firmware change is needed; a save (0x45-0x47) after 0x15 writes whatever the store holds.

Next: the WebUSB page (hx_ctl's protocol in JavaScript): backup = for each preset, 0x14 load then 0x16 with
{0x7a: 1}; restore = 0x15 then save; snapshot names and colours = edit the records (name +0x27e, 11 bytes;
colour +0x27c) for 1-4 in the stock section and for 4-6 in key 14.

## The page, first version (2026-11-15)

`web/pod-go/podgo-usb.js` (hx_ctl.py's protocol in JavaScript: link with routing, streams with sequence,
window and heartbeat, the three service channels, MessagePack; encoding checked byte for byte against
Python's msgpack) and `web/pod-go/companion.html` (connect, back up every preset of the setlist to one
`.podgobackup` file: MessagePack {format, version, created, setlist, complete, presets: [{index, name, blob}]}).

Timing, measured on the unit: load preset (0x14) answers status 1 at once; the notify stream then sends
{0x69: 20, {0x66: seq}} (the request's completion), a few block/footswitch events, and **{0x69: 4, ...}**
when the preset has loaded, 0.3-0.42 s after the request; 0x16 then takes about 0.05 s. The page waits for
event 4 (fallback 0.5 s) instead of fixed delays: a full setlist in about a minute instead of about five.

On the unit (RAM, companion build), in Chrome: backup completed, presets with snapshots 5 and 6 marked.
With the installed (older) six-snapshot build the same backup completes without 5 and 6 (the marker is
ignored); the page says so.

## Restore (2026-11-15)

Save as: editor command **0x46** {0x6b setlist, 0x6c slot, 0x6d name} saves the edit buffer to that slot under
that name (decoder 0x28c88469 also defaults all three to the current preset; 0x45 saves keeping the slot's
name; handler 0x28c8ac74). Restore = load the slot (0x14), set edit buffer (0x15) with the backed-up blob,
save as (0x46). Tried with hx_ctl first (RAM run, writes in memory): NAM Essentials copied into slot 128 as
"RESTORE TEST", reloaded with its snapshot 5/6 records, the new name in the preset list. Then from the page in
Chrome: a preset restored from the backup file, 5 and 6 on the unit.

Backup files are MessagePack with string keys; the page's decoder returns string keys as strings (the first
try rejected every file).
