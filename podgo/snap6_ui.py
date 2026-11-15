#!/usr/bin/env python3
"""Six snapshots, step (c): the footswitch screen's snapshot tiles, made from the user's own firmware.

    python3 podgo/snap6_ui.py STOCK.hxf OUT_DIR [--png]

The stock tiles (`Play_Snapshot1..4`, `..Sel`: 174x64) are a flat background with a camera badge in the middle
and the snapshot number drawn in it. Six equal columns need 154-px tiles, and 5 and 6 need badges of their own:
each new tile is the stock tile's background with its badge copied in, the number redrawn for 5 and 6.
Built at build time from the firmware given (Line 6 artwork: never published, OUT_DIR stays in build/).

OUT_DIR gets recs.bin (48-byte Entry 7 style records), ents.bin ({size, offset} per image), tiles.bin and pix.bin
(the icons: RGB565, little-endian, rows mirrored left-right, as Entry 8 keeps them), which snap6.s includes.

Coloured tiles: the snapshot tiles aren't stored as pictures. tiles.bin holds each tile's description, the twelve
camera badges (background pixels marked) and a colour table; snap6.s draws a tile as it is read, its background in
the snapshot's LED colour exactly as stomp mode colours a block of that colour (Line 6's own two tile images per
colour): the deeper "Off" shade with white text when idle, as a bypassed block; the full colour with dark text when
active, as an engaged block (the screen draws the active snapshot's text dark); stock grey and white for Auto. Both footswitch views use them:
154-px tiles for six snapshots, 174-px ones (stock width) for four. docs/research/SNAPSHOTS_6.md.
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


STOCK_W = 174
MARK = 0x0001          # a badge pixel that takes the tile's background colour
SYNTH = 0x40000000     # an Entry 8 offset with this bit: a tile drawn by snap6.s, image k in bits 20..25
# images IMG_ID0 + k: 0-5 six-view tiles 1-6, 6-11 their selected versions, 12-15 icons 5, 6, 5 red, 6 red,
# 16-19 four-view tiles 1-4, 20-23 selected
TILES = [(154, n, 0) for n in range(6)] + [(154, n, 1) for n in range(6)] + [None] * 4 + \
        [(STOCK_W, n, 0) for n in range(4)] + [(STOCK_W, n, 1) for n in range(4)]
NIMG = len(TILES)
# LED colour (0 Auto, 1 White, 2 Red, 3 Dark Orange, 4 Light Orange, 5 Yellow, 6 Green, 7 Turquoise, 8 Blue,
# 9 Violet, 10 Pink, 11 Off) -> Line 6's tile image of that colour (Play_<name> / Play_<name>Off)
PALETTE = [None, 'Gray', 'Red', 'DarkOrange', 'LightOrange', 'Yellow', 'Green', 'Turquoise', 'Blue', 'Violet', 'Pink', None]


def _rgb(v):
    return np.array([(v >> 11 & 31) * 255 / 31, (v >> 5 & 63) * 255 / 63, (v & 31) * 255 / 31])


def _565(c):
    r, g, b = (int(round(min(255, max(0, x)))) for x in c)
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def colours(get, idle_bg, sel_bg):
    """[(idle, active)] RGB565 per LED colour."""
    out = []
    for k, name in enumerate(PALETTE):
        if k == 0:
            out.append((idle_bg, sel_bg))                    # Auto: stock
        elif k == 1:
            out.append((get('Play_GrayOff')[0][0, 0], 0xffff))   # White: grey (white text), white
        elif k == 11:
            out.append((_565((24, 24, 26)), get('Play_Gray')[0][0, 0]))   # Off: near black, grey
        else:                                                 # as stomp mode: Play_<colour>Off / Play_<colour>
            out.append((get(f'Play_{name}Off')[0][0, 0], get(f'Play_{name}')[0][0, 0]))
    return out


def _bg_mask(a, sel):
    """The tile's background pixels: every pixel of the background colour on an idle tile (the camera is an
    outline); on a selected tile only those reached from the edge (the number's white disc stays white)."""
    bg = a[0, 0]
    if not sel:
        return a == bg
    h, w = a.shape
    m = np.zeros((h, w), bool)
    stack = [(0, 0)]
    m[0, 0] = True
    while stack:
        y, x = stack.pop()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < h and 0 <= xx < w and not m[yy, xx] and a[yy, xx] == bg:
                m[yy, xx] = True
                stack.append((yy, xx))
    # the light edge pixels between the black camera and the white background (smoothing) go with the
    # background too, or they show as white specks on a coloured tile
    lum = (a >> 11 & 31) * 8 + (a >> 5 & 63) * 4 + (a & 31) * 8
    for _ in range(2):
        near = np.zeros_like(m)
        near[1:, :] |= m[:-1, :]; near[:-1, :] |= m[1:, :]; near[:, 1:] |= m[:, :-1]; near[:, :-1] |= m[:, 1:]
        m |= near & (lum >= 0.62 * lum[0, 0])
    return m


def badges(get):
    """[(w, h, x in a 174-px tile, y, pixels)] for snapshots 1-6 idle, then selected, then idle as stock (for Auto);
    MARK where background. On a coloured idle tile the camera and number are drawn white, as stomp mode draws its
    text on colour: the grey outline (smoothed into the grey background) becomes crisp white pixels."""
    out = []
    for sel in (0, 1, 2):
        for n in range(1, 7):
            suf = 'Sel' if sel == 1 else ''
            src, _ = get(f'Play_Snapshot{min(n, 4)}{suf}')
            if n > 4:
                src = redigit(src, get(f'Play_Snapshot1{suf}')[0], n)
            assert src.shape == (TILE_H, STOCK_W)
            y0, y1, x0, x1 = badge_box(src)
            crop = src[y0:y1, x0:x1].copy()
            assert not (crop == MARK).any()
            if sel == 0:                            # white where the outline (dimmer than the number) is drawn
                lum = lambda v: (v >> 11 & 31) * 8 + (v >> 5 & 63) * 4 + (v & 31) * 8
                lb, lm = lum(src[0, 0]), max(lum(v) for v in crop.ravel())
                a = (np.vectorize(lum)(crop) - lb) / max(1, lm - lb)
                crop = np.where(a >= 0.22, 0xffff, MARK).astype(np.uint16)
            else:
                crop[_bg_mask(src, sel == 1)[y0:y1, x0:x1]] = MARK
            out.append((x1 - x0, y1 - y0, x0, y0, crop))
    return out


def images(hxf):
    """(recs, ents, tiles, pix, preview): the 24 images' records and {size, offset}, tiles.bin, the icons' pixels,
    and preview tiles (one colour each) for --png."""
    get = stock_images(hxf)
    _, rec_tile = get('Play_Snapshot1')
    _, rec_icon = get('Icon_Snapshot1')
    idle_bg, sel_bg = get('Play_Snapshot1')[0][0, 0], get('Play_Snapshot1Sel')[0][0, 0]
    icons = [icon(get, 5, False), icon(get, 6, False), icon(get, 5, True), icon(get, 6, True)]
    bad = badges(get)
    pal = colours(get, idle_bg, sel_bg)
    recs, ents, pix, desc = b'', b'', b'', b''
    for k, t in enumerate(TILES):
        if t is None:
            a = icons[k - 12]
            h, w = a.shape
            r = list(rec_icon)
            body = a[:, ::-1].astype('<u2').tobytes()
            ents += struct.pack('<2I', len(body), len(pix))
            pix += body
            desc += bytes(8)
        else:
            w, n, sel = t
            h = TILE_H
            bw, bh, bx, by, _ = bad[n + 6 * sel]
            dx = bx if w == STOCK_W else (w - bw) // 2 + (bx - (STOCK_W - bw) // 2)   # as tile(): keep the offset
            r = list(rec_tile)
            ents += struct.pack('<2I', w * h * 2, SYNTH | k << 20)
            desc += struct.pack('<HBBBBBB', w, n, sel, n + 6 * sel, dx, by, 0)
        r[2] = r[3] = r[9] = ENT8_0 + k
        r[5], r[6] = w, h
        recs += struct.pack('<12I', *r)
    tint = b''.join(struct.pack('<2H', i, a) for i, a in pal)
    heads, bpix = b'', b''
    for bw, bh, _, _, crop in bad:
        heads += struct.pack('<BBHI', bw, bh, 0, len(bpix))
        bpix += crop.astype('<u2').tobytes()
    tiles = desc + tint + heads + bpix          # snap6.s: TD 0, TINT 8 * NIMG, BHEAD + 48, BPIX + 144
    assert len(desc) == 8 * NIMG and len(tint) == 48 and len(heads) == 144
    return recs, ents, tiles, pix, (bad, pal, icons)


def draw(bad, pal, w, n, sel, colour):
    """A tile as snap6.s draws it (for the preview and the tests)."""
    colour = colour if colour < 12 else 0
    bw, bh, bx, by, crop = bad[n + 6 * sel + (12 if colour == 0 and not sel else 0)]
    dx = bx if w == STOCK_W else (w - bw) // 2 + (bx - (STOCK_W - bw) // 2)
    bg = pal[colour][sel]
    out = np.full((TILE_H, w), bg, np.uint16)
    out[by:by + bh, dx:dx + bw] = np.where(crop == MARK, bg, crop)
    return out


def build(hxf, out_dir, png=False):
    recs, ents, tiles, pix, (bad, pal, icons) = images(hxf)
    os.makedirs(out_dir, exist_ok=True)
    for name, b in (('recs.bin', recs), ('ents.bin', ents), ('tiles.bin', tiles), ('pix.bin', pix)):
        open(os.path.join(out_dir, name), 'wb').write(b)
    if png:                                  # every LED colour, idle and active, in both widths
        from PIL import Image
        rows = []
        for c in range(12):
            row = [draw(bad, pal, 154, c % 6, sel, c) for sel in (0, 1)] + [draw(bad, pal, STOCK_W, c % 4, sel, c) for sel in (0, 1)]
            rows.append(np.concatenate([np.pad(to_rgb(a), ((2, 2), (2, 2), (0, 0))) for a in row], 1))
        sheet = np.concatenate(rows, 0)
        Image.fromarray(sheet).resize((sheet.shape[1] * 2, sheet.shape[0] * 2), Image.NEAREST).save(
            os.path.join(out_dir, 'tiles.png'))
    return NIMG


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    n = build(a[0], a[1], '--png' in a)
    print(f'{n} images in {a[1]}')
