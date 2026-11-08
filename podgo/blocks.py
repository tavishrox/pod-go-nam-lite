#!/usr/bin/env python3
"""Add or remove any block in the POD Go's current preset from the Mac: amps, cabs, IRs and FX loops too,
which the POD Go and POD Go Edit only offer on their fixed blocks.

    python3 podgo/blocks.py status                 # the preset on the unit: its blocks and DSP use
    python3 podgo/blocks.py list amp|cab|ir|loop|eq|fx [WORD]   # models you can add, with their cost
    python3 podgo/blocks.py add [amp|cab|ir|loop|eq|fx] MODEL [--at N]   # first empty block, or block N
    python3 podgo/blocks.py remove N               # empty block N
    python3 podgo/blocks.py restore FILE           # write back a preset kept before a change

MODEL is a name as the unit shows it ("1x12 Cali EXT", "1024-sample IR", "Mono FX Loop") or a preset id.
Changes go to the edit buffer only, like editing on the unit: press SAVE on the POD Go (or in POD Go Edit)
to keep them. Before each change the preset is kept in build/blocks_undo/. The unit's own rules decide:
at most one amp, one cab or IR, one EQ and one FX loop, up to 7 other effects, and about 8,000 cost units
of blocks (docs/PODGO_PORT_MAP.md, Phase 2). A change the unit refuses is undone and reported.
Quit POD Go Edit first (it holds the USB connection). Needs the stock firmware file for the model data:
../POD_Go_v2.50.0_0x6e984472.hxf (or $PODGO_HXF).
"""
import copy
import json
import os
import pickle
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import hx_ctl  # noqa: E402

PID = 0x424b
STOCK = os.environ.get('PODGO_HXF', os.path.join(ROOT, '..', 'POD_Go_v2.50.0_0x6e984472.hxf'))
CACHE = os.path.join(ROOT, 'build', 'blocks_catalog.pkl')
UNDO = os.path.join(ROOT, 'build', 'blocks_undo')
TAB1 = 0x28001e10                     # Entry 0 Table 1: {name index, preset id, 0, cost}
NAM = (27, 2850, 'NAM A2 Lite')       # the NAM firmware's model on Elektrik's preset id, and its cost
KINDS = {1: 'effect', 8: 'effect (stereo)', 9: 'FX loop', 13: 'FX loop (stereo)', 15: 'IR', 17: 'amp',
         23: 'EQ (fixed)', 26: 'cab'}
ONE_OF = {17: 'amp', 15: 'cab/IR', 26: 'cab/IR', 23: 'fixed EQ', 9: 'FX loop', 13: 'FX loop'}
GROUPS = {'amp': {17}, 'cab': {26}, 'ir': {15}, 'loop': {9, 13}, 'eq': {23}, 'fx': {1, 8}}


def session():
    return hx_ctl.HxCtl(False, 8.0, PID)


def catalog():
    """{preset id: (name, kind, cost, [param types], [defaults])} from the stock firmware's tables."""
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, 'rb'))
    import kit_patch_amp as kp
    import patch_amp
    data, _ = patch_amp.load_l6ia_from_any(STOCK)
    info = kp.parse_entry3_full(kp.get_entry_swapped(data, 3))
    e0 = kp.get_entry_swapped(data, 0)
    import effects
    t1 = kp._e0_vaddr_to_foff(effects._segs(e0), TAB1, 12)
    rows, k = {}, 0
    while True:
        ni, pid, z, cost = struct.unpack_from('<IHHI', e0, t1 + 12 * k)
        if ni == 0 and pid == 0 and k > 5:
            break
        rows[ni] = (pid, cost)
        k += 1
    out = {}
    for m in info['models']:
        ni = m['words'][2]
        if ni not in rows:
            continue
        pid, cost = rows[ni]
        i = e0.find(struct.pack('<Ii', ni, -1))
        if i < 4:
            continue                              # not in any browser list: not offered by the unit
        btype, _, _, ipid = struct.unpack_from('<IIiH', e0, i - 4)
        if ipid != pid:
            continue
        name = e0[i + 10: i + 36].split(b'\0')[0].decode('latin1')

        def val(p):
            v = p.get('default') or 0.0
            if p.get('type') == 2:
                return struct.unpack('<i', struct.pack('<f', v))[0]
            if p.get('type') == 1:
                return bool(v)
            return float(v)
        if m['name'].startswith('HD2_Preamp'):
            name += ' (preamp)'                   # the same name as its full amp
        # a preset stores only the knobs: no data fields (type 6, e.g. a cab's IrData at slot 1001)
        out[pid] = (name, btype, cost, [val(p) for p in m['params'] if p.get('type') != 6 and p['slot'] < 1000])
    n, c, names = NAM[0], NAM[1], NAM[2]
    if n in out:
        out[n] = (names, out[n][1], c, out[n][3])
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump(out, open(CACHE, 'wb'))
    return out


def read():
    with session() as hx:
        blob = hx.get_preset_blob()
    with session() as hx:
        cur = hx.current()
    return blob, cur


def chain(sec, cat):
    rows = []
    for p, b in enumerate(hx_ctl.blocks(sec)):
        if 1 <= p <= 10:
            if b.get(19) == 6:
                pid = b[20][24][25]
                name, kind, cost, _ = cat.get(pid, (f'model {pid}', b[20][9], 0, None))
                rows.append((p, pid, name, b[20][9], cost, b[20][10]))
            else:
                rows.append((p, None, '', None, 0, None))
    return rows


def show(sec, cat, title):
    rows = chain(sec, cat)
    used = [r for r in rows if r[1] is not None]
    fx = sum(1 for r in used if r[3] in (1, 8))
    cost = sum(r[4] for r in used)
    print(title)
    for p, pid, name, kind, c, on in rows:
        print(f'  {p:2d}  ' + (f'{name:24s} {KINDS.get(kind, kind):16s} {c:5d}  {"on" if on else "off"}'
                               if pid is not None else '-- empty --'))
    print(f'  effects {fx}/7, DSP {cost} of about 8,000 units (amp, cab/IR, EQ and FX loop: one each)')


def find(cat, word):
    if word.isdigit() and int(word) in cat:
        return int(word)
    group, _, rest = word.partition(' ')
    kinds = GROUPS.get(group.lower())
    if kinds:
        word = rest
    pool = {p: v for p, v in cat.items() if kinds is None or v[1] in kinds}
    hits = [pid for pid, v in pool.items() if v[0].lower() == word.lower()]
    hits = hits or [pid for pid, v in pool.items() if word.lower() in v[0].lower()]
    if len(hits) > 1 and kinds is None and {cat[p][1] for p in hits} == {15, 26}:
        hits = [p for p in hits if cat[p][1] == 26]          # a cab name: the modern cab (250 units);
        print('(the modern cab; "add ir NAME" picks the legacy cab/IR, 600 units)')   # legacy: "ir"
    if len(hits) != 1:
        names = ', '.join(sorted(cat[p][0] for p in hits)[:12])
        sys.exit(f'"{word}": {"no model" if not hits else str(len(hits)) + " models"} match' +
                 (f' ({names})' if hits else '') + '. Try: blocks.py list cab ' + word.split()[0])
    return hits[0]


def new_block(pid, cat, template):
    name, kind, cost, vals = cat[pid]
    b = copy.deepcopy(template)
    b[19] = 6
    b[20] = {24: {23: False, 25: pid, 26: -1}, 9: kind, 10: True,
             11: {2: len(vals), 3: len(vals), 4: list(vals)}, 12: {2: 0, 3: 0, 4: []}}
    return b


def write(magic, sec, blob_before, what):
    os.makedirs(UNDO, exist_ok=True)
    keep = os.path.join(UNDO, time.strftime('%Y%m%d-%H%M%S') + '.bin')
    open(keep, 'wb').write(blob_before)
    with session() as hx:
        hx.set_preset_blob(hx_ctl.encode_preset(magic, sec), settle=2.0)
    with session() as hx:
        _, got = hx.get_preset()
    want = [(b[20][24][25] if b.get(19) == 6 else None) for b in hx_ctl.blocks(sec)]
    have = [(b[20][24][25] if b.get(19) == 6 else None) for b in hx_ctl.blocks(got)]
    if want != have:
        with session() as hx:
            hx.set_preset_blob(blob_before, settle=2.0)
        sys.exit(f'The POD Go refused {what} (over a limit: one amp, one cab/IR, one EQ, one FX loop, '
                 '7 effects, about 8,000 units). The preset is as it was.')
    print(f'Done: {what}. Press SAVE on the POD Go to keep it (undo file: {os.path.relpath(keep, ROOT)}).')
    return got


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ('status', 'list', 'add', 'remove', 'restore'):
        sys.exit(__doc__)
    cat = catalog()
    if a[0] == 'list':
        kinds = GROUPS.get(a[1] if len(a) > 1 else 'fx', {1, 8})
        word = ' '.join(a[2:]).lower()
        for pid, (name, kind, cost, _) in sorted(cat.items(), key=lambda x: (x[1][1], x[1][0])):
            if kind in kinds and word in name.lower():
                print(f'  {name:28s} {KINDS.get(kind, kind):16s} cost {cost:5d}   id {pid}')
        return
    if a[0] == 'restore':
        blob = open(a[1], 'rb').read()
        with session() as hx:
            hx.set_preset_blob(blob, settle=2.0)
        print('Restored. Press SAVE on the POD Go to keep it.')
        return
    blob, cur = read()
    magic, sec = hx_ctl.decode_preset(blob)
    if a[0] == 'status':
        show(sec, cat, f'Preset {cur["preset"] + 1} "{cur["name"]}" (edit buffer):')
        return
    bl = hx_ctl.blocks(sec)
    if a[0] == 'remove':
        n = int(a[1])
        if not (1 <= n <= 10) or bl[n].get(19) != 6:
            sys.exit(f'block {n} is empty or not a block (1..10)')
        name = cat.get(bl[n][20][24][25], ('that block',))[0]
        bl[n] = {19: 8, 20: None}
        got = write(magic, sec, blob, f'removed {name} from block {n}')
        show(got, cat, 'Now:')
        return
    at = int(a[a.index('--at') + 1]) if '--at' in a else None
    word = ' '.join(x for i, x in enumerate(a[1:], 1) if x != '--at' and (i < 2 or a[i - 1] != '--at'))
    pid = find(cat, word)
    name, kind, cost, _ = cat[pid]
    rows = [r for r in chain(sec, cat) if r[1] is not None]
    if kind in ONE_OF and any(ONE_OF.get(r[3]) == ONE_OF[kind] for r in rows):
        art = 'an' if ONE_OF[kind][0] in 'aeiouAEIOU' else 'a'
        sys.exit(f'This preset already has {art} {ONE_OF[kind]}: the POD Go allows one. Remove it first.')
    free = [p for p in range(1, 11) if bl[p].get(19) != 6]
    if at is None:
        if not free:
            sys.exit('No empty block: remove one first.')
        at = free[0]
    elif at not in free:
        sys.exit(f'Block {at} is not empty.')
    bl[at] = new_block(pid, cat, bl[at])
    got = write(magic, sec, blob, f'added {name} ({KINDS.get(kind, kind)}, {cost} units) at block {at}')
    show(got, cat, 'Now:')


if __name__ == '__main__':
    main()
