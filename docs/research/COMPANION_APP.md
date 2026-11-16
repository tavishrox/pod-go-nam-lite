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

## Set one parameter (2026-11-15, from POD Go Edit; confirmed on the unit)

For the Morph Pad (`web/pod-go/morph.html`), which needs to turn a knob live. POD Go Edit's Mac binary keeps
its symbols, so the path is readable: `PodGoEditBufferContext::setParam` -> `PodGoEditorService::setObjectParam
(objectId, dsp, index, value)` -> `PodGoCmdDispatcher::DispatchCommand(6, 0x1e, params)`.

- **Editor command 0x1e** (firmware: decoder 0x28c879e5, handler 0x28c8c27d), params
  `{0x62: grid position, 0x1d: dsp, 0x1a: 0, 0x1c: parameter index, 0x77: value}`.
  POD Go Edit's dictionary keys carry an ordering tag in the high 16 bits (0x1001d, 0x2001a, ...); only the low
  byte goes on the wire (load preset is built the same way as 0x6b, 0x1006c and is sent as {0x6b, 0x6c}).
- `0x1d` true = a model ("DSP") parameter, its index from `HelixSymbolTable::lookupParam(model, name)`, i.e.
  the place in the model's parameter list (amps: Drive 0, Bass 1, Mid 2, Treble 3, Presence 4, ChVol 5,
  Master 6, ...). False = the editor's "V params" (`LookupVParamIndex`).
- Value: the L6Variant from the model definition; knobs are 0..1 floats (Drive 0.5 shows 5.0). The probe sends
  float32.
- Grid position: object ids by grid position come from the unit (`ObjectInfo` +0x6c); in setObjectParam
  object 0xff -> 0 (input), 0xfd -> 11 (output), the blocks in between. **Command 0x2d `{0x62: pos}`**
  (`getObjectInfo`) reads what is at a position without changing anything.
- After a set, POD Go Edit ignores notifications 0x3e9 and 0x1e for 1 s: the unit reports the change back.
- Also seen: recall snapshot = 0x58 `{0x5c: n}`.

Test (`podgo/param_probe.py`, edit buffer only, nothing saved): `info` to find the amp's grid position,
`listen` while turning Drive on the unit, `set POS 0 0.5`, then `sweep POS 0 0.2 0.8 3` for smoothness at
30 messages a second.

Parameter names per model: POD Go Edit's `Resources/PodGo.sym` (JSON, 627 models). It is Line 6's file: read
it from the user's own install or get the order from the unit; never commit or publish it.

### On the unit (2026-11-15, preset 45 "NAM Essentials", POD Go Edit closed)

- `info` (0x2d) works for positions 0..11. The reply is `{13: pos, 24: {19: type, 20: {...}}}`. Blocks have type 6:
  `20.25` is the model number, `20.10` is on/off, and `20.11.4` is the list of current parameter values in index
  order. Empty slots return None, 0 is the input and 11 the output. The amp (model 27) was at grid position 5;
  its `.pgp` `@position` is 3, so ask the unit rather than work it out from the file.
- `set 5 0 0.65` (Drive): reply `{102: seq, 103: 0, 104: <the params echoed>}`. A float32 value is accepted. The
  notify channel then sends `{105: 30, 106: {..., 106: <same params>}}` (notification 0x1e), and `info` reads
  Drive back as 0.65.
- `sweep 5 0 0.2 0.8 3`: 91 messages in 3.03 s, every one status 0, with one echo per message. Drive was put back
  to 0.5 afterwards. Whether the glide sounds smooth (no zipper noise) still needs a listen.
- For the Morph Pad: read the slot list with 0x2d, send 0x1e per changed knob at up to 30 Hz, and update the
  display from the 0x1e notifications so knob turns on the unit show up too.

### Morph Pad on the unit (web/pod-go/morph.html, local only)

`podgo-usb.js` gained `slotInfo(pos)`, `setParam(pos, index, value)` (value always sent as float32, so 0 and 1
go out as floats; bytes checked against param_probe.py) and `onNotify(fn)`. The pad finds the amp with 0x2d,
sends nothing until the pad is moved, queues every request one at a time (they share the editor stream), keeps
the values read at connect for "Put the amp back", rescans when a preset loads (event 4), and treats a 0x1e echo
more than 1 s after its own send as a knob turned on the unit.

Knob order differs between amps: of 214 amp and preamp models in POD Go Edit's list, 58 use Drive, Bass, Mid,
Treble, Presence, ChVol, Master as indices 0-6; 44 have no Presence and put Master at 4, and the rest vary.
The unit's model number is the model's place in `PodGo.sym` (checked on all seven blocks of preset 45). The page
lets the user load their own `PodGo.sym` and keeps only the amp knob-name lists in that browser; without it, it
assumes the common order and says so. Nothing from the file ships with the page.

### Line 6's Focus View data, as a guide (2026-11-15; the files stay outside the repo)

The user keeps Line 6 Stadium's Focus View defaults outside the repo (`../../Res/focus-view-xy-defaults/<category>/<Model>.json`,
674 models). Update, same day: the owner decided these defaults may ship (public, built-in preset data, not sold);
the 460 POD Go models' sets are in `web/pod-go/focus-defaults.json` with each model's POD Go number and parameter
order. The NAM firmware's model 27 (NAM A2 Lite in Elektrik's place) never gets Elektrik's tones, and its Master
(the capture) is fixed.
Shape: `{modelName, params: {Name: {id, behavior}}, regions: {origin, x_min_y_min, x_min_y_max, x_max_y_min,
x_max_y_max}}`, each region a `name` plus a value for every parameter. What it teaches:

- Five tones per model, centre plus four corners, as the Morph Pad already does; each tone has its own name.
- Every parameter of the model is set, not just the seven main knobs (Sag, Ripple, Bias, BiasX, Hum, switches).
- Three behaviours: `interpolate` (blend; float), `quantize` (switches and selectors; bool or int, so pick, don't
  blend) and `exclude` (leave alone: Stadium's cab EQ internals).
- Values are the device's own units: 0..1 for knobs, dB and Hz for EQ bands and thresholds, bool and int for switches.
- Model names are the POD Go's symbols without `HD2_`; 213 of the POD Go's 214 amp and preamp models have a set,
  and 460 of its 627 models in all. Parameter names match `PodGo.sym` exactly, but Stadium's `id`s do not always
  match the POD Go's order (79 models have extra Stadium parameters), so map by name, never by id.

### Morph Pad rebuilt around tone sets per model (2026-11-15)

- On the unit, 0x1e also takes an integer (a selector: the Simple Delay's SyncSelect1, 6 -> 8) and a boolean (a
  switch: TempoSync1, True -> False). Each reads back with 0x2d and was restored. So every parameter type can be
  set live; send each in the type the unit holds it in (0x2d's values carry it: float32, int, bool).
- `podgo-usb.js`: `MP.decode(body, typed)` returns floats as F32 objects (a float 0.0 stays distinct from an int
  0), and `slotInfo` uses it to return `types` beside `values`. `setParam(pos, index, value, asInt)` sends a boolean
  as a boolean, an integer when asked, and any other number as float32.
- `morph.html`: a tone set per model, in the tone-file shape described above. The page lists every block on the unit, picks the
  model's set (the user's own edits, else imported files, else our starter amp tones), and blends each parameter
  by its behaviour: blend (`interpolate`), pick the tone with the most weight (`quantize`), or leave (`exclude`).
  A model with no set starts with all five tones as the block is; a block's model is named from the user's own
  `PodGo.sym`. Imported files, edits and the model list are kept in the browser's IndexedDB; nothing is shipped.
