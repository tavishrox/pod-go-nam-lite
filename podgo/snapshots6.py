#!/usr/bin/env python3
"""Six snapshots for the POD Go 2.50: hold MODE for a six-snapshot footswitch mode (bottom row 1 2 3, top row
4 5 6, Bank Up/Down as snapshot switches), with snapshots 5 and 6 saved inside the preset (build_podgo.py
--snapshots6, or on its own here).

    python3 podgo/snapshots6.py POD_Go_v2.50.0_0x6e984472.hxf [-o OUT.hxf] [--base RELEASE.hxf] [--debug]
    python3 podgo/snapshots6.py STOCK.hxf --update-code     re-assemble the committed code (podgo/snap6/)

The code (podgo/snap6/snap6.s) is committed assembled (podgo/snap6/snap6_code.bin, snap6_syms.json: no Line 6
artwork, so the web page needs no assembler); its tile and icon images are drawn at build time from the
firmware file given (snap6_ui.py) and appended. Code, store and images go after the application's code segment
at 0x28ce4100 (after --model-names's cave, so both can go in one build), and the stock code is changed in the
places listed below (STOCK). --base puts the changes on a built release instead of stock (only its Entry 0
changes; the stock file is still read for the images). --debug assembles a test build that adds a debug key
to POD Go Edit's reads (needs arm-none-eabi binutils; not for POD Go Edit or an install).
Run it from RAM first (tools/hxf_ram.py run ... --writes ram). docs/research/SNAPSHOTS_6.md.
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, HERE)

SEG6_DST, SEG6_LEN = 0x28c58ba0, 0x8b418
CAVE_VA = 0x28ce4100
SRC = os.path.join(HERE, 'snap6', 'snap6.s')
BIN = os.path.join(ROOT, 'build', 'snap6', 'snap6.bin')     # holds the tile images: build/ only, never published
SYMS_JSON = os.path.join(ROOT, 'build', 'snap6', 'snap6.syms.json')   # hook addresses, from the link (assemble)
CODE_BIN = os.path.join(HERE, 'snap6', 'snap6_code.bin')     # committed: the release assembly up to img_recs
CODE_SYMS = os.path.join(HERE, 'snap6', 'snap6_syms.json')
HOOKS = ('sel_hook', 'reset_hook', 'st_feac', 'st_fa6c', 'ser_hook', 'des_hook',
         'wrap_7944', 'wrap_8040', 'wrap_8240', 'wrap_84a8',
         'fs_hook', 'draw_hook', 'cur_virt', 'vname', 'mask_stub', 'rec_hook', 'idx_hook', 'open_hook',
         'sh_fs', 'sh_x', 'sh_y', 'sh_tx', 'sh_ty', 'sh_img', 'sh_snap', 'sh_c2t', 'sh_sel',
         'cur_true', 'vcolor', 'sh_led', 'icon_n', 'icon_r', 'app_dec', 'app_rd')
IMG_DIR = os.path.join(ROOT, 'build', 'snap6_img')   # tile images from the user's firmware (snap6_ui.py)
# step (c): b.w / bl to a hook {address: (symbol, stock bytes, bl?)}
UI_JUMPS = {0x28cae5bc: ('fs_hook', 'f0b50c46', False),    # footswitch events
            0x28c9a320: ('draw_hook', '2de9f04f', False),  # the footswitch screen
            0x28c9a914: ('cur_virt', '1ef022fa', True),    # its current snapshot (bl 0x28cb8d5c)
            0x28c9aa58: ('vname', '1ef0b4f9', True),       # a tile's name (bl 0x28cb8dc4)
            0x28c9aa82: ('mask_stub', '0923eb40', False),  # the tiles it skips
            0x28c7d498: ('rec_hook', 'e9b1421c', False),   # image record
            0x28c7d5b4: ('idx_hook', '70b5134c', False),   # Entry 8 index
            0x28c7d608: ('open_hook', '70b582b0', False),  # Entry 8 open
            0x28cac23a: ('cur_virt', '0cf08ffd', True),    # snapshot LEDs: the current one (bl 0x28cb8d5c)
            0x28cac264: ('vcolor', '0cf016fb', True),      # ... a snapshot's colour (bl 0x28cb8894)
            0x28cac29e: ('vcolor', '0cf0f9fa', True),
            0x28c9b246: ('cur_true', '1df089fd', True),    # top-right icon: the current one (bl 0x28cb8d5c)
            0x28c9b98e: ('cur_true', '1df0e5f9', True),
            0x28c9c5c8: ('cur_true', '1cf0c8fb', True)}
UI_BYTES = {0x28cac280: ('042c', '062c')}               # snapshot LEDs: loop over six (cmp r4, #4 -> #6)
# literal pool words of the screen / snapshot-switch code pointing at tables: {address: (symbol, stock word)}
UI_POOLS = {0x28c9a9e8: ('sh_y', 0x28ce11f4), 0x28c9aa00: ('sh_x', 0x28ce11dc), 0x28c9aa0c: ('sh_tx', 0x28ce1224),
            0x28c9aa10: ('sh_ty', 0x28ce1254), 0x28c9ad34: ('sh_img', 0x28ce12b0), 0x28c9ad38: ('sh_snap', 0x28ce12f8),
            0x28c9ad3c: ('sh_c2t', 0x28ce1284), 0x28c9ad40: ('sh_sel', 0x28ce12a0), 0x28cad3f8: ('sh_fs', 0x28ce239c),
            0x28cac31c: ('sh_led', 0x28ce23ec),                                     # snapshot -> LED
            0x28c9b470: ('icon_n', 0x280110a4), 0x28c9b474: ('icon_r', 0x280110b4),  # top-right icon tables
            0x28c9bca0: ('icon_n', 0x280110a4), 0x28c9bca4: ('icon_r', 0x280110b4),
            0x28c9bffc: ('icon_n', 0x280110a4), 0x28c9c654: ('icon_n', 0x280110c4),
            0x28c9c658: ('icon_r', 0x280110d4), 0x28c9cb60: ('icon_n', 0x280110c4)}
# the companion app: editor command 0x16's registration literals {address: (symbol, stock Thumb pointer)}
APP_PTRS = {0x28c8d068: ('app_rd', 0x28c8b1a1),        # its handler
            0x28c8d06c: ('app_dec', 0x28c88821)}       # its parameter decoder (stock: return 0)
SELECT, RESET, CC69_CMP = 0x28cb88a4, 0x28cb7878, 0x28cb6496
SER, DES = 0x28cb916c, 0x28cb984c                       # snapshot section writer / reader
SAVE0, SAVE1 = 0x28c9604a, 0x28c96176                   # bl 0x28c8feac / bl 0x28c8fa6c: preset to the store
MIRROR = {0x28cb7944: ('wrap_7944', '2de9f047'), 0x28cb8040: ('wrap_8040', '2de9f04f'),   # knob set per snapshot
          0x28cb8240: ('wrap_8240', '2de9f04f'), 0x28cb84a8: ('wrap_84a8', '2de9f04f')}   # or not: all records
STOCK = {SELECT: '2de9f04f', RESET: '2de9f043', CC69_CMP: '032c', SER: '2de9f04f', DES: '2de9f04f',
         **{va: b for va, (_, b) in MIRROR.items()}, **{va: b for va, (_, b, _) in UI_JUMPS.items()},
         **{va: struct.pack('<I', w).hex() for va, (_, w) in UI_POOLS.items()},
         **{va: a for va, (a, _) in UI_BYTES.items()},
         **{va: struct.pack('<I', w).hex() for va, (_, w) in APP_PTRS.items()}}
STOCK_MD5 = 'e0ea3e1ed32f0f353b79f6ad39631838'
OUT_NAME = 'POD_Go_v2.50.0_6Snap.hxf'                   # six snapshots on stock, nothing else (the page's "only" choice)
BUILT_MD5 = 'e96852fe987acd896ca16bddfc3ea868'                                      # that build's .hxf: web/pod-go/firmware-worker.js compares


def assemble(stock, debug=True):
    """snap6.s linked at CAVE_VA (needs arm-none-eabi binutils), with the tile images made from `stock`
    (build/snap6_img); writes snap6.bin."""
    import snap6_ui
    snap6_ui.build(stock, IMG_DIR)
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        o, elf = os.path.join(t, 's.o'), os.path.join(t, 's.elf')
        subprocess.run(['arm-none-eabi-as', '-mcpu=cortex-m4', '-mthumb', '-I', IMG_DIR]
                       + (['--defsym', 'DEBUG=1'] if debug else []) + [SRC, '-o', o], check=True)
        subprocess.run(['arm-none-eabi-ld', f'-Ttext={CAVE_VA:#x}', '-e', 'sel_hook', o, '-o', elf], check=True)
        nm = subprocess.run(['arm-none-eabi-nm', elf], capture_output=True, text=True, check=True).stdout
        got = {l.split()[2]: int(l.split()[0], 16) for l in nm.splitlines() if l.split()[-1] in HOOKS + ('img_recs',)}
        assert set(got) == set(HOOKS) | {'img_recs'} and got['sel_hook'] == CAVE_VA, f'symbols: {got}'
        subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', elf, BIN], check=True)
        json.dump(got, open(SYMS_JSON, 'w'), indent=1)
    return open(BIN, 'rb').read(), got


def update_code(stock):
    """Re-assemble the release (no debug) build and commit its code part: everything before the images."""
    full, syms = assemble(stock, debug=False)
    n = syms['img_recs'] - CAVE_VA
    open(CODE_BIN, 'wb').write(full[:n])
    json.dump(syms, open(CODE_SYMS, 'w'), indent=1, sort_keys=True)
    open(CODE_SYMS, 'a').write('\n')
    print(f'{CODE_BIN}: {n} B of code and data; images ({len(full) - n} B) come from the firmware at build time')


def code_with_images(stock_data):
    """The committed code with the tile images drawn from stock_data (the stock L6IA bytes): (bytes, syms)."""
    import snap6_ui
    code = open(CODE_BIN, 'rb').read()
    syms = json.load(open(CODE_SYMS))
    assert syms['img_recs'] - CAVE_VA == len(code), 'snap6_code.bin and snap6_syms.json disagree'
    recs, ents, tiles, pix, _ = snap6_ui.images(stock_data)
    return code + recs + ents + tiles + pix, syms


def thumb_bw(src, dst, link=False):
    off = dst - (src + 4)
    s, i1, i2 = (off >> 24) & 1, (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    return struct.pack('<2H', 0xf000 | (s << 10) | ((off >> 12) & 0x3ff),
                       (0xd000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7ff))


def entry0(e0, code, SYMS, log=print):
    """Entry 0 (swapped payload, stock 2.50 code segment, with or without --model-names's cave), with `code`
    (code_with_images, or a --debug assembly) and its symbols."""
    import patch_amp as pa
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments(e0)
    hdr, poff, slen, dst, nxt = segs[6]
    assert dst == SEG6_DST and SEG6_LEN <= slen <= CAVE_VA - SEG6_DST and len(e0) - nxt < 4, \
        'Entry 0 is not the 2.50 layout'
    fo = lambda va: pa._e0_vaddr_to_foff(segs, va)
    stock = dict(STOCK)
    stock[SAVE0] = thumb_bw(SAVE0, 0x28c8feac, True).hex()
    stock[SAVE1] = thumb_bw(SAVE1, 0x28c8fa6c, True).hex()
    for va, want in stock.items():
        got = bytes(e0[fo(va): fo(va) + len(want) // 2])
        assert got == bytes.fromhex(want), f'Entry 0 at {va:#x} is {got.hex()}, not {want}'
    e0[fo(SELECT): fo(SELECT) + 4] = thumb_bw(SELECT, SYMS['sel_hook'])
    e0[fo(RESET): fo(RESET) + 4] = thumb_bw(RESET, SYMS['reset_hook'])
    e0[fo(CC69_CMP)] = 5                                   # cmp r4, #5
    e0[fo(SER): fo(SER) + 4] = thumb_bw(SER, SYMS['ser_hook'])
    e0[fo(DES): fo(DES) + 4] = thumb_bw(DES, SYMS['des_hook'])
    e0[fo(SAVE0): fo(SAVE0) + 4] = thumb_bw(SAVE0, SYMS['st_feac'], True)
    e0[fo(SAVE1): fo(SAVE1) + 4] = thumb_bw(SAVE1, SYMS['st_fa6c'], True)
    for va, (sym, _) in MIRROR.items():
        e0[fo(va): fo(va) + 4] = thumb_bw(va, SYMS[sym])
    for va, (sym, _, link) in UI_JUMPS.items():
        e0[fo(va): fo(va) + 4] = thumb_bw(va, SYMS[sym], link)
    for va, (sym, _) in UI_POOLS.items():
        struct.pack_into('<I', e0, fo(va), SYMS[sym])
    for va, (_, b) in UI_BYTES.items():
        e0[fo(va): fo(va) + len(b) // 2] = bytes.fromhex(b)
    for va, (sym, _) in APP_PTRS.items():
        struct.pack_into('<I', e0, fo(va), SYMS[sym] | 1)
    pad = CAVE_VA - (dst + slen)
    out = e0[:nxt] + b'\x00' * pad + code
    out += b'\x00' * ((-len(out)) & 3)
    n = slen + pad + len(code)
    struct.pack_into('<3I', out, hdr, n, dst, poff + n)
    struct.pack_into('<I', out, 4, len(out))
    log(f'[+] Entry 0: six snapshots (hold MODE), 5 and 6 saved with the preset ({len(code)} B at {CAVE_VA:#x})')
    return bytes(out)


def make_image(stock_data, log=print):
    """The L6IA image of stock 2.50 with six snapshots and nothing else (the web page calls this too)."""
    import kit_patch_amp as kp
    import l6ia
    code, syms = code_with_images(stock_data)
    image, _, _ = l6ia.rebuild_archive(stock_data, {0: entry0(kp.get_entry_swapped(stock_data, 0), code, syms, log=log)})
    return image


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        sys.exit(__doc__)
    stock = a[0]
    md5 = hashlib.md5(open(stock, 'rb').read()).hexdigest()
    if md5 != STOCK_MD5:
        sys.exit(f'{stock}: MD5 {md5}, not POD_Go_v2.50.0_0x6e984472.hxf')
    if '--update-code' in a:
        return update_code(stock)
    out = a[a.index('-o') + 1] if '-o' in a else os.path.join(ROOT, 'build', OUT_NAME)
    import kit_patch_amp as kp
    import l6ia
    import patch_amp
    stock_data, _ = patch_amp.load_l6ia_from_any(stock)
    code, syms = assemble(stock, debug=True) if '--debug' in a else code_with_images(stock_data)
    base = a[a.index('--base') + 1] if '--base' in a else stock     # --base: a built release (e.g. the NAM one)
    data = patch_amp.load_l6ia_from_any(base)[0] if base != stock else stock_data
    image, _, _ = l6ia.rebuild_archive(data, {0: entry0(kp.get_entry_swapped(data, 0), code, syms)})
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img = out[:-4] + '.l6ia'
    open(img, 'wb').write(image)
    py = sys.executable
    rep = subprocess.run([py, os.path.join(ROOT, 'tools', 'l6ia_verify.py'), img], capture_output=True, text=True).stdout
    if 'ALL OK' not in rep:
        sys.exit('snapshots6.py: the image failed its checksum check\n' + rep)
    subprocess.run([py, os.path.join(ROOT, 'tools', 'hxf.py'), 'pack', img, out, '--donor', base], check=True)
    got = hashlib.md5(open(out, "rb").read()).hexdigest()
    plain = '--base' not in a and '--debug' not in a
    print(f'Done: {out} (MD5 {got}' + ((', the project build' if got == BUILT_MD5 else ', NOT the project build: please report')
                                      if plain else '') + ')')
    print(f'Run it from RAM: python3 tools/hxf_ram.py run {os.path.relpath(out, ROOT)} --stock <the .hxf installed> --writes ram')


if __name__ == '__main__':
    main()
