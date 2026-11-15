#!/usr/bin/env python3
"""Six snapshots, step (c): the footswitch screen's snapshot tiles, made from the user's own firmware.

    python3 podgo/snap6_ui.py STOCK.hxf OUT_DIR [--png]

The stock tiles (`Play_Snapshot1..4`, `..Sel`: 174x64) are a flat background with a camera badge in the middle
and the snapshot number drawn in it. Six equal columns need 154-px tiles, and 5 and 6 need badges of their own:
each new tile is the stock tile's background with its badge copied in, the number redrawn for 5 and 6.
Built at build time from the firmware given (Line 6 artwork: never published, OUT_DIR stays in build/).

OUT_DIR gets recs.bin (48-byte Entry 7 style records), ents.bin ({size, offset} per image) and pix.bin (RGB565,
little-endian, rows mirrored left-right, as Entry 8 keeps them), which snap6.s includes. docs/research/SNAPSHOTS_6.md.
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, 'tools'), HERE]

TILE_W, TILE_H = 154, 64
IMG_ID0, ENT8_0 = 546, 0x1000          # ids past the stock 546 images; Entry 8 indexes past the stock ones


def stock_images(hxf):
    """hxf: a .hxf path, or the L6IA bytes already loaded from one."""
    import kit_patch_amp as kp
    import patch_amp as pa
    data = hxf if isinstance(hxf, (bytes, bytearray)) else pa.load_l6ia_from_any(hxf)[0]
    e7, e8 = kp.get_entry_swapped(data, 7), kp.get_entry_swapped(data, 8)
    names = [n.decode('latin1') for n in e7[4404:12812].split(b'\0')[:546]]

    def get(name):
        k = names.index(name)
        r = struct.unpack_from('<12I', e7, 12812 + 48 * k)
        w, h = r[5], r[6]
        size, off = struct.unpack_from('<2I', e8, 24 + 8 * r[2])
        assert size == w * h * 2, name
        return np.frombuffer(e8[off:off + size], '<u2').reshape(h, w)[:, ::-1].copy(), r
    return get


def to_rgb(a):
    return np.stack([(a >> 11 & 31) * 255 // 31, (a >> 5 & 63) * 255 // 63, (a & 31) * 255 // 31], -1).astype('uint8')


def to_565(rgb):
    r, g, b = (rgb[..., i].astype(np.uint16) for i in range(3))
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def badge_box(a):
    ys, xs = np.nonzero(a != a[0, 0])
    return ys.min(), ys.max() + 1, xs.min(), xs.max() + 1


DIGITS = {      # 9x14, 1-px strokes like the stock numbers
    5: ["..######.", "..#......", "..#......", "..#......", ".#.......", ".#.###...", ".##...#..",
        ".......#.", "........#", "........#", "........#", ".#.....#.", "..#...#..", "...###..."],
    6: [".....##..", "....#....", "...#.....", "..#......", "..#......", ".#..###..", ".#.#...#.",
        ".##.....#", ".#......#", ".#......#", ".#......#", "..#....#.", "...#..#..", "....##..."],
}


def redigit(a, a_other, digit):
    """Badge `a` (snapshot 4's) with its number replaced by `digit`; a_other (snapshot 1's) locates the number
    (where the two badges differ). The number is one colour; it is erased inside the circle and redrawn."""
    diff = a != a_other
    ys, xs = np.nonzero(diff)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1      # both numbers' box, inside the circle
    fill = np.bincount(a_other[diff]).argmax()                           # where 4 has strokes, 1 has none
    ink = np.bincount(a[diff & (a != fill)]).argmax()
    while y0 > 0 and (a[y0 - 1, x0:x1] == ink).any():                   # the strokes 1 and 4 share run on
        y0 -= 1
    while y1 < a.shape[0] and (a[y1, x0:x1] == ink).any():
        y1 += 1
    num = np.zeros_like(diff)
    num[y0:y1, x0:x1] = a[y0:y1, x0:x1] == ink
    ny, nx = np.nonzero(num)
    y0, x0 = ny.min(), nx.min()
    assert (ny.max() - y0 + 1, nx.max() - x0 + 1) == (14, 9), f'the stock number is {ny.max() - y0 + 1}x{nx.max() - x0 + 1}'
    out = a.copy()
    out[num] = fill
    for r, row in enumerate(DIGITS[digit]):
        for c, ch in enumerate(row):
            if ch == '#':
                out[y0 + r, x0 + c] = ink
    return out


def tile(get, n, sel):
    """Snapshot n's tile (1..6), TILE_W wide, from the stock tile of n (or of 4 for 5 and 6)."""
    suf = 'Sel' if sel else ''
    src, _ = get(f'Play_Snapshot{min(n, 4)}{suf}')
    if n > 4:
        other, _ = get(f'Play_Snapshot1{suf}')
        src = redigit(src, other, n)
    y0, y1, x0, x1 = badge_box(src)
    out = np.full((TILE_H, TILE_W), src[0, 0], np.uint16)
    w = x1 - x0
    nx = (TILE_W - w) // 2 + (x0 - (src.shape[1] - w) // 2)                     # keep the badge's offset from centre
    out[y0:y1, nx:nx + w] = src[y0:y1, x0:x1]
    return out


def icon(get, n, red):
    """The top-right snapshot icon for 5 or 6 (34x23), from the stock icon of 4."""
    suf = 'Red' if red else ''
    return redigit(get(f'Icon_Snapshot4{suf}')[0], get(f'Icon_Snapshot1{suf}')[0], n)


def images(hxf):
    """(recs, ents, pix, imgs): images IMG_ID0.. : tiles 1-6, selected tiles 1-6, icons 5 6, red icons 5 6."""
    get = stock_images(hxf)
    _, rec_tile = get('Play_Snapshot1')
    _, rec_icon = get('Icon_Snapshot1')
    imgs = [tile(get, n, False) for n in range(1, 7)] + [tile(get, n, True) for n in range(1, 7)]
    imgs += [icon(get, 5, False), icon(get, 6, False), icon(get, 5, True), icon(get, 6, True)]
    recs, ents, pix = b'', b'', b''
    for k, a in enumerate(imgs):
        h, w = a.shape
        r = list(rec_tile if k < 12 else rec_icon)
        r[2] = r[3] = r[9] = ENT8_0 + k
        r[5], r[6] = w, h
        recs += struct.pack('<12I', *r)
        body = a[:, ::-1].astype('<u2').tobytes()
        ents += struct.pack('<2I', len(body), len(pix))
        pix += body
    return recs, ents, pix, imgs


def build(hxf, out_dir, png=False):
    recs, ents, pix, imgs = images(hxf)
    os.makedirs(out_dir, exist_ok=True)
    for name, b in (('recs.bin', recs), ('ents.bin', ents), ('pix.bin', pix)):
        open(os.path.join(out_dir, name), 'wb').write(b)
    if png:
        from PIL import Image
        sheet = np.zeros((3 * TILE_H + 12, 6 * (TILE_W + 4), 3), np.uint8)
        for k, a in enumerate(imgs):
            y, x = (k // 6) * (TILE_H + 6), (k % 6) * (TILE_W + 4)
            sheet[y:y + a.shape[0], x:x + a.shape[1]] = to_rgb(a)
        Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(
            os.path.join(out_dir, 'tiles.png'))
    return len(imgs)


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    n = build(a[0], a[1], '--png' in a)
    print(f'{n} images in {a[1]}')
