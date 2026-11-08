#!/usr/bin/env python3
"""Boot-screen graphics for the POD Go 2.50 (docs/PODGO_PORT_MAP.md, "The app's splash graphics").

    python3 podgo/splash.py preview IMAGE OUT.png      # what the unit will show (480x272, RGB565)
    python3 podgo/splash.py overlay STOCK.hxf OVERLAY.png Splash|Splash_Wireless OUT.png
                                                       # an overlay drawn on your own firmware's boot screen

An overlay is a transparent PNG (any size of the screen's shape) drawn over the stock boot screen taken from
the user's own firmware at build time, so artwork can be shared without sharing Line 6's (splash/README.md).

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


def stock_image(e7, e8, name):
    """The firmware's own boot screen `name` as an RGB image (the way round the unit shows it)."""
    from PIL import Image
    off = _index(e7, e8, name)
    a = np.frombuffer(e8[off: off + W * H * 2], '<u2').reshape(H, W)[:, ::-1]
    rgb = np.stack([(a >> 11 & 31) * 255 // 31, (a >> 5 & 63) * 255 // 63, (a & 31) * 255 // 31], -1)
    return Image.fromarray(rgb.astype(np.uint8), 'RGB')


def compose(base, overlay_path):
    """`base` (RGB, 480x272) with the overlay PNG fitted to the screen and drawn over it."""
    from PIL import Image
    ov = Image.open(overlay_path).convert('RGBA')
    s = min(W / ov.width, H / ov.height)
    w, h = max(1, round(ov.width * s)), max(1, round(ov.height * s))
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    layer.paste(ov.resize((w, h), Image.LANCZOS), ((W - w) // 2, (H - h) // 2))
    return Image.alpha_composite(base.convert('RGBA'), layer).convert('RGB')


def to_rgb565(path):
    """The image (a path or an RGB image) fitted to 480x272 (black bars if its shape differs), error-diffused
    to RGB565. Returns (uint16 array HxW, the RGB the unit will show)."""
    from PIL import Image
    im = (path if isinstance(path, Image.Image) else Image.open(path)).convert('RGB')
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


def replace(e7, e8, name, path, overlay=False):
    """Entry 8 with graphic `name` replaced by the image at `path` (stored mirrored); with overlay=True, the
    PNG at `path` drawn over the boot screen already in `e8` (the user's own firmware's)."""
    assert name in SPLASHES, name
    off = _index(e7, e8, name)
    px, _ = to_rgb565(compose(stock_image(e7, e8, name), path) if overlay else path)
    e8 = bytearray(e8)
    e8[off: off + W * H * 2] = px[:, ::-1].astype('<u2').tobytes()
    return bytes(e8)


def main():
    a = sys.argv[1:]
    from PIL import Image
    if len(a) == 5 and a[0] == 'overlay':
        sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..', 'tools'))
        import kit_patch_amp as kp
        import patch_amp
        data, _ = patch_amp.load_l6ia_from_any(a[1])
        _, shown = to_rgb565(compose(stock_image(kp.get_entry_swapped(data, 7), kp.get_entry_swapped(data, 8), a[3]), a[2]))
        Image.fromarray(shown).save(a[4])
        print(f'wrote {a[4]}: {a[2]} over {a[3]} from {a[1]}')
        return
    if len(a) != 3 or a[0] != 'preview':
        sys.exit(__doc__)
    _, shown = to_rgb565(a[1])
    Image.fromarray(shown).save(a[2])
    print(f'wrote {a[2]}: {W}x{H}, RGB565 as the unit shows it')


if __name__ == '__main__':
    main()
