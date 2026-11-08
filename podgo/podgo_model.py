#!/usr/bin/env python3
"""NAM A2 Lite on the POD Go 2.50 as an amp, on Brit Plexi Brt's identity (docs/PODGO_PORT_MAP.md):
Entry 4 (the NAM host graph) and Entry 3 (NAM's parameters on model 74), the Plexi knob layout.

The POD Go counterpart of tools/effects.py's entry4/entry3: kit_patch_amp's generic insertion code,
with this unit's numbers where it has the HX Stomp's (620 stock models and blobs, not 864; the state
records' constant; the Amp harness 0x600007 and its model placeholder 0x60000b).

Every knob keeps Brit Plexi Brt's slot, type (float 0..1) and range, so POD Go Edit, which knows
that model, keeps NAM blocks and their values. The kernel (nam_multi.py --podgo --plexi) decodes
Master as Model, Sag as Mid Freq, Hum as Q and Ripple as Polarity.
"""
import inspect
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import kit_patch_amp as kp      # noqa: E402

N_STOCK = 620
STATE_CONST = 0x5cd54                    # word 1 of every stock state record (the Stomp's 0x80b98)
HOST_MODEL, HOST_COMP = 'HD2_AmpLine6Clarity', 0x600114   # in port -> amp sub-composite -> out port
HARNESS, PLACEHOLDER, PLACEHOLDER_MEMBER, PLACEHOLDER_DM = 0x600007, 0x60000b, 3, 0x5c4
BLOB0_MAX = 0x5fff1                      # podgo_e2.BLOB0_WORDS
# A composite no model blob, no composite and no Blob 0 root member uses, and the application names
# nowhere: NAM's host composite is written over it, so Blob 0 keeps its size and composite count
# (a grown Blob 0 hangs the POD Go's UI, on the unit 2026-11-07). 1,751 words, NAM's needs 64.
SPARE_COMP = 0x60011c
# No SDRAM through the graph: raising the Amp harness placeholder's 0x800 SDRAM words hangs the
# POD Go at boot (on the unit, 2026-11-07); the kernel uses fixed per-slot SDRAM (--static-sdram).
INSTANCE = {'dm_words': 0x303, 'pm_words': 0x147, 'sdram_words': 0}
NAME, DISPLAY = 'HD2_AmpNAMLitePG', 'NAM A2 Lite'
# DSP cost (Entry 0 Table 1, the unit's 9,000-unit admission budget): measured on the unit
# 2026-11-08 (nam_multi.py --meter 1 and 4): the DSP runs at 393.216 MHz, 262,144 cycles a
# 32-sample period; NAM takes 74,150 a period (median; 99%: ~89k) = 28.3%. At the HX Stomp's
# measured ~13 cycles a unit per 16 samples (docs/research/NAM_LITE_DSP_LOAD.md), 26 per 32: 2,852.
DSP_COST = 2850
TAB1_VADDR = 0x28001e10                 # Table 1: 12-byte rows {name index, preset id u16, 0 u16, cost}

# (slot, source param, pid, display name on the unit or None, default): slots and order as
# Brit Plexi Brt's; pids are the kernel's DM(pid, I0) (100, 101: read by nothing).
PLEXI_LAYOUT = (
    (1, 'Drive', 5, 'Input', 0.5),
    (2, 'Bass', 8, None, 0.5),
    (3, 'Mid', 9, None, 0.5),
    (4, 'Treble', 10, None, 0.5),
    (5, 'Presence', 11, 'High Cut', 1.0),
    (6, 'ChVol', 6, 'Output', 0.5),
    (7, 'Master', 7, 'Model', 0.0),
    (8, 'Sag', 19, 'Mid Freq', 0.48),
    (9, 'Hum', 20, 'Q', 0.0),
    (10, 'Ripple', 15, 'Polarity', 0.0),
    (11, 'Bias', 100, None, None),
    (12, 'BiasX', 101, None, None),
)
# Line 6 Elektrik: 11 float knobs (no Hum). POD Go Edit's defaults: Bias 0.6 (would invert as
# Polarity), BiasX 0.5 (normal), so Polarity is on BiasX and Bias is the unused knob.
ELEKTRIK_LAYOUT = (
    (1, 'Drive', 5, 'Input', 0.5),
    (2, 'Bass', 8, None, 0.5),
    (3, 'Mid', 9, None, 0.5),
    (4, 'Treble', 10, None, 0.5),
    (5, 'Presence', 11, 'High Cut', 1.0),
    (6, 'ChVol', 6, 'Output', 0.5),
    (7, 'Master', 7, 'Model', 0.0),
    (8, 'Sag', 19, 'Mid Freq', 0.48),
    (9, 'Ripple', 20, 'Q', 0.0),
    (10, 'Bias', 100, None, None),
    (11, 'BiasX', 15, 'Polarity', 0.0),
)
# name: (model, Entry 3 model id = blob, name index, the stock display name, knob layout)
DONORS = {
    'plexi': ('HD2_AmpBritPlexiBrt', 74, 0x11c, 'Brit Plexi Brt', PLEXI_LAYOUT),
    'elektrik': ('HD2_AmpLine6Elektrik', 46, 0xda, 'Line 6 Elektrik', ELEKTRIK_LAYOUT),
}
DEFAULT_DONOR = 'elektrik'


def use_donor(key):
    """Pick the amp NAM replaces (DONORS), for every function below."""
    global DONOR, DONOR_ID, DONOR_NI, DONOR_SHOWN, LAYOUT
    DONOR, DONOR_ID, DONOR_NI, DONOR_SHOWN, LAYOUT = DONORS[key]


use_donor(DEFAULT_DONOR)


def _patched(fn, *pairs):
    """kit_patch_amp's function `fn` with this unit's numbers: source text replacements."""
    src = inspect.getsource(fn)
    for a, b in pairs:
        assert a in src, (fn.__name__, a)
        src = src.replace(a, b)
    ns = dict(vars(kp))
    exec(src, ns)
    return ns[fn.__name__], ns


def params(e3, info):
    donor = kp.find_model(info, DONOR)
    slots = {p['name']: p['slot'] for p in donor['params']}
    spec = [(slot, DONOR, src, pid, disp, dflt) for slot, src, pid, disp, dflt in LAYOUT]
    out = kp.nam_params(e3, info, spec)
    names = [p['name'] for p in donor['params']]
    assert [p['name'] for p in out] == names, f'{DONOR_SHOWN} has {names}'
    assert all(p['type'] == 3 for p in out), 'every knob is a float'
    assert all(slots[p['name']] == p['slot'] for p in out), 'slots as the donor has them'
    return out


def overwrite_composite(b0, src_comp_id, dst_comp_id):
    """Blob 0 with composite dst rewritten as a relocated copy of src, inside dst's own words:
    nothing moves, nothing is added. The rest of dst's old words stay (nothing reads them)."""
    b0 = list(b0)
    ct = b0[0x10]
    hdr = lambda c: b0[ct + 7 * (c - 0x600000): ct + 7 * (c - 0x600000) + 7]
    s, d = hdr(src_comp_id), hdr(dst_comp_id)
    s_start, s_end = s[3], s[5] + 4 * s[4]
    d_start, d_end = d[3], d[5] + 4 * d[4]
    assert s_end - s_start <= d_end - d_start, 'the spare composite is too small'
    delta = d_start - s_start
    sl = list(b0[s_start: s_end])
    for m in range(s[2]):
        r = 20 * m
        c_rel = sl[r + 2] - s_start
        for j in range(sl[r + 1] >> 1):
            assert s_start <= sl[c_rel + 3 * j + 1] <= s_end
            sl[c_rel + 3 * j + 1] += delta
        for col in (2, 8, 10, 12):
            assert s_start <= sl[r + col] <= s_end
            sl[r + col] += delta
    b0[d_start: d_start + len(sl)] = sl
    i = ct + 7 * (dst_comp_id - 0x600000)
    b0[i: i + 7] = [s[0], s[1], s[2], s[3] + delta, s[4], s[5] + delta, s[6]]
    return b0


def spare_unused(info, w4, dirp, b0):
    """True if SPARE_COMP is unused by every model blob, composite and Blob 0 root member."""
    ct = b0[0x10]
    for m in info['models']:
        n, o = dirp[m['blob_index']]
        b = w4[o: o + n]
        if n > 3 and b[0] == 3 and b[b[2] + 1] == SPARE_COMP:
            return False
    for c in range(b0[0xf]):
        h = b0[ct + 7 * c: ct + 7 * c + 7]
        if any(b0[h[3] + 20 * k + 6] == SPARE_COMP for k in range(h[2])):
            return False
    return all(b0[b0[0xb] + 20 * k + 6] != SPARE_COMP for k in range(b0[0xa]))


def entry4(e4, info, nam):
    """Entry 4 rebuilt in the stock layout (directory at word 6, Blob 0 first, every stock blob
    after it in order) with the NAM host composite written over SPARE_COMP (Blob 0's size and
    composite count as stock) and the donor's own blob (74,
    used by no other model) replaced by the NAM host blob, so the count stays 620: a 621st blob,
    even one nothing names, hangs the POD Go's UI and preset handling (on the unit, 2026-11-07).
    The Amp harness stays stock."""
    w4 = struct.unpack('<%dI' % (len(e4) // 4), e4)
    assert w4[:2] == (0x28267e5e, 4) and w4[2] == N_STOCK and w4[3] == 6, \
        f'Entry 4 header {w4[:6]}: not POD Go 2.50 ({N_STOCK} blobs, directory at word 6)'
    dirp = [(w4[6 + 2 * k], w4[6 + 2 * k + 1]) for k in range(N_STOCK)]
    b0 = list(w4[dirp[0][1]: dirp[0][1] + dirp[0][0]])
    src = kp.find_model(info, HOST_MODEL)['blob_index']
    sb = w4[dirp[src][1]: dirp[src][1] + dirp[src][0]]
    assert sb[sb[2] + 1] == HOST_COMP, f'{HOST_MODEL} is not on composite {HOST_COMP:#x}'
    assert spare_unused(info, w4, dirp, b0), f'{SPARE_COMP:#x} is used'
    n0 = len(b0)
    b0 = overwrite_composite(b0, HOST_COMP, SPARE_COMP)
    comp = SPARE_COMP
    kp.nam_host_member(b0, comp, 0x9c75, **INSTANCE)
    assert len(b0) == n0
    err = kp.sharc_blob0_check(b0, n0)                # the stock buffer: Entry 2's GROW_BLOB0 off
    assert err is None, err
    donor_blob = kp.find_model(info, DONOR)['blob_index']
    assert donor_blob == DONOR_ID and sum(m['blob_index'] == donor_blob for m in info['models']) == 1
    blobs = [b0] + [list(w4[o: o + n]) for n, o in dirp[1:]]
    blobs[donor_blob] = kp.nam_host_blob(comp, nam)
    out = [0x28267e5e, 4, len(blobs), 6, 0, 0]
    cur, d = 6 + 2 * len(blobs), []
    for b in blobs:
        d += [len(b), cur]
        cur += len(b)
    out += d
    out[4] = d[1]
    for b in blobs:
        out += b
    out[5] = len(out)
    return struct.pack('<%dI' % len(out), *out), donor_blob, comp


def entry3(e3, blob, nam):
    info = kp.parse_entry3_full(e3)
    assert len(info['models']) == N_STOCK
    donor = kp.find_model(info, DONOR)
    assert (donor['model_id'], donor['words'][2]) == (DONOR_ID, DONOR_NI)
    d0 = donor['words']
    assert all(struct.unpack_from('<5I', e3, d0[10] + 20 * k)[1] == STATE_CONST for k in range(d0[6]))
    add3, _ = _patched(kp.add_model_entry3, ('864', str(N_STOCK)), ('0x80b98', hex(STATE_CONST)))
    out, new_id, _ = add3(e3, donor, NAME, DISPLAY, blob, nam)
    assert new_id == N_STOCK
    out = bytearray(out)
    h = struct.unpack_from('<10I', out, 0)
    mtab, gtab, gcnt = h[6], h[8], h[9]
    d_new = struct.unpack_from('<14I', out, mtab + 56 * new_id)
    d = list(struct.unpack_from('<14I', out, mtab + 56 * DONOR_ID))
    for k in (0, 1, 6, 7, 10, 11, 13):             # meta, states, parameters, blob; name and id stay
        d[k] = d_new[k]
    struct.pack_into('<14I', out, mtab + 56 * DONOR_ID, *d)
    assert h[7] == N_STOCK + 1 and new_id == N_STOCK
    struct.pack_into('<I', out, 7 * 4, N_STOCK)     # the copy's descriptor (the last) dropped: 620 models,
                                                    # as a 621st blob hangs the unit's UI (its data stays,
                                                    # model 74 points at it)
    for k in range(gcnt):                           # slot lists as stock: the copy out of every list
        lc, lo = struct.unpack_from('<2I', out, gtab + 32 * k + 20)
        lst = list(struct.unpack_from(f'<{lc}I', out, lo)) if lc else []
        if new_id in lst:
            new = [m for m in lst if m != new_id]
            struct.pack_into(f'<{len(new)}I', out, lo, *new)
            struct.pack_into('<I', out, gtab + 32 * k + 20, len(new))
    info2 = kp.parse_entry3_full(bytes(out))
    assert len(info2['models']) == N_STOCK
    m = info2['models'][DONOR_ID]
    assert (m['name'], m['displayName'], m['blob_index'], len(m['params'])) == (DONOR, DISPLAY, blob, len(nam))
    return bytes(out)


# Entry 0 (the application): the donor's two name strings, found by name index and name: its browser
# item (48 bytes: {type, name index, -1, preset id u16, name[26], ..}) and its Table 2 row (44 bytes:
# {name index, short name[16], kind, 3 counts, ..}). A preamp twin has its own name index. Knob names
# are not in Entry 0 (they come from Entry 3).
def entry0(e0):
    """Entry 0 with NAM's name in the amp browser and Table 2 (the block's name on the unit)."""
    import l6ia
    e0 = bytearray(e0)
    nm = DONOR_SHOWN.encode('latin1')
    ni_b = struct.pack('<Ii', DONOR_NI, -1)
    pos = [k for k in range(len(e0)) if e0.startswith(nm + b'\0', k)]
    items = [k - 14 for k in pos if e0[k - 10: k - 2] == ni_b]
    rows = [k - 4 for k in pos if struct.unpack_from('<I', e0, k - 4)[0] == DONOR_NI]
    assert len(items) == 1 and len(rows) == 1, f'{DONOR_SHOWN}: browser items {items}, Table 2 rows {rows}'
    it, r = items[0], rows[0]
    e0[it + 14: it + 40] = DISPLAY.encode('latin1')[:25].ljust(26, b'\0')
    n = len(LAYOUT)
    assert struct.unpack_from('<3I', e0, r + 24) == (n, n, n), f'Table 2 counts: {n} knobs'
    e0[r + 4: r + 20] = DISPLAY.encode('latin1')[:15].ljust(16, b'\0')
    import effects
    t1 = kp._e0_vaddr_to_foff(effects._segs(bytes(e0)), TAB1_VADDR, 12)
    rows = []
    k = 0
    while True:
        ni, pid, z, cost = struct.unpack_from('<IHHI', e0, t1 + 12 * k)
        if ni == 0 and pid == 0 and k > 5:
            break
        if ni == DONOR_NI:
            rows.append(k)
        k += 1
    assert len(rows) == 1, f'Table 1 rows for {DONOR_NI:#x}: {rows}'
    o = t1 + 12 * rows[0]
    ni, pid, z, cost = struct.unpack_from('<IHHI', e0, o)
    struct.pack_into('<IHHI', e0, o, ni, pid, z, DSP_COST)
    return bytes(l6ia.fix_internal_crcs(bytes(e0)))


def build(l6ia_bytes, log=print):
    """{entry: new payload (little-endian, as rebuild_archive takes them)} for Entries 3 and 4."""
    e3 = kp.get_entry_swapped(l6ia_bytes, 3)
    e4 = kp.get_entry_swapped(l6ia_bytes, 4)
    info = kp.parse_entry3_full(e3)
    nam = params(e3, info)
    new_e4, blob, comp = entry4(e4, info, nam)
    log(f'[+] Entry 4: NAM host blob {blob} on composite {comp:#x} (Amp harness {HARNESS:#x} as stock)')
    new_e3 = entry3(e3, blob, nam)
    log(f'[+] Entry 3: model {DONOR_ID} ({DONOR}) carries {DISPLAY}: {len(nam)} knobs in its layout')
    new_e0 = entry0(kp.get_entry_swapped(l6ia_bytes, 0))
    log(f'[+] Entry 0: name index {DONOR_NI:#x} shown as {DISPLAY} (browser item and Table 2 row), DSP cost {DSP_COST}')
    return {0: new_e0, 3: new_e3, 4: new_e4}
