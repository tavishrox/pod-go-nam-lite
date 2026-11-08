#!/usr/bin/env python3
"""Boot-screen graphics for the POD Go 2.50 (docs/PODGO_PORT_MAP.md, "The app's splash graphics").

    python3 podgo/splash.py preview IMAGE OUT.png      # what the unit will show (480x272, RGB565)

Entry 7 indexes the app's graphics, Entry 8 holds their pixels: raw RGB565, little-endian, each row
mirrored left-right. `replace(e7, e8, name, image)` writes an image over a 480x272 graphic in place
(same size, same offset): nothing else in the firmware moves. The bootloader is never touched.
"""
import struct
import sys

import numpy as np

W, H = 480, 272
E7_NAMES, E7_RECORDS, E7_COUNT = 4404, 12812, 546
SPLASHES = ('Splash', 'Splash_Wireless')


def _index(e7, e8, name):
    names = [n.decode('latin1') for n in e7[E7_NAMES:E7_RECORDS].split(b'\0')[:E7_COUNT]]
    k = names.index(name)
    r = struct.unpack_from('<12I', e7, E7_RECORDS + 48 * k)
    assert (r[5], r[6], r[7], r[8]) == (W, H, 16, 0xf807e01f), f'{name}: {r}'
    size, off = struct.unpack_from('<2I', e8, 24 + 8 * r[2])
    assert size == W * H * 2, (name, size)
    return off


def to_rgb565(path):
    """The image fitted to 480x272 (black bars if its shape differs), error-diffused to RGB565.
    Returns (uint16 array HxW, the RGB the unit will show)."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    s = min(W / im.width, H / im.height)
    w, h = max(1, round(im.width * s)), max(1, round(im.height * s))
    canvas = Image.new('RGB', (W, H), (0, 0, 0))
    canvas.paste(im.resize((w, h), Image.LANCZOS), ((W - w) // 2, (H - h) // 2))
    a = np.asarray(canvas, dtype=np.float64)
    levels = np.array([31, 63, 31], dtype=np.float64)
    out = np.zeros((H, W, 3), dtype=np.int64)
    for y in range(H):                                  # Floyd-Steinberg, per channel's step
        for x in range(W):
            old = np.clip(a[y, x], 0, 255)
            q = np.round(old * levels / 255)
            out[y, x] = q
            err = old - q * 255 / levels
            if x + 1 < W: a[y, x + 1] += err * 7 / 16
            if y + 1 < H:
                if x > 0: a[y + 1, x - 1] += err * 3 / 16
                a[y + 1, x] += err * 5 / 16
                if x + 1 < W: a[y + 1, x + 1] += err * 1 / 16
    px = (out[..., 0] << 11 | out[..., 1] << 5 | out[..., 2]).astype(np.uint16)
    shown = (out * 255 / levels).round().astype(np.uint8)
    return px, shown


def replace(e7, e8, name, path):
    """Entry 8 with graphic `name` replaced by the image at `path` (stored mirrored)."""
    assert name in SPLASHES, name
    off = _index(e7, e8, name)
    px, _ = to_rgb565(path)
    e8 = bytearray(e8)
    e8[off: off + W * H * 2] = px[:, ::-1].astype('<u2').tobytes()
    return bytes(e8)


def main():
    a = sys.argv[1:]
    if len(a) != 3 or a[0] != 'preview':
        sys.exit(__doc__)
    from PIL import Image
    _, shown = to_rgb565(a[1])
    Image.fromarray(shown).save(a[2])
    print(f'wrote {a[2]}: {W}x{H}, RGB565 as the unit shows it')


if __name__ == '__main__':
    main()
