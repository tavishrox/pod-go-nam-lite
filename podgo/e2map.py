#!/usr/bin/env python3
"""Read-only map of the POD Go's SHARC boot stream (L6IA Entry 2).

Parses the LDR blocks the same way tools/patch_amp.py does for the HX Stomp
and prints every block with its address range translated to *normal-word*
addresses (so 48-bit PM, 32-bit DM and 16-bit short views of the same internal
RAM line up), plus a per-block occupancy summary for internal Blocks 0..3.
"""
import struct
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import l6ia  # noqa: E402

NW = {5: lambda c: ((c + 1) & ~1) * 3 // 2, 4: lambda c: c, 3: lambda c: (c + 1) // 2,
      6: lambda c: c * 2, 0: lambda c: 384, 10: lambda c: c, 9: lambda c: c,
      1: lambda c: 0, 2: lambda c: 0}
TAGNAME = {0: 'FINAL', 1: 'ZERO_L48?', 2: 'ZERO', 3: 'INIT_L16', 4: 'INIT_L32', 5: 'INIT_L48',
           6: 'INIT_L64', 9: 'tag9', 10: 'tag10'}


def load_e2(path):
    d = open(path, 'rb').read()
    if d[:4] == b'FORM':
        import zlib, hxf
        d = zlib.decompress([b for c, p, s, b in hxf._chunks(d) if c == b'data'][0])
    e = l6ia.parse(d)[2]
    return d[e['payload_off']: e['payload_off'] + e['payload_len']]


def blocks(e2):
    w = struct.unpack('<%dI' % (len(e2) // 4), e2)
    i, out = 384, []
    while i + 3 <= len(w):
        tag, cnt, addr = w[i:i + 3]
        if tag not in NW:
            raise SystemExit(f'desync at word {i}: tag {tag:#x}')
        out.append((i, tag, cnt, addr))
        if tag == 0:
            break
        i += 3 + NW[tag](cnt)
    return w, out


# ADSP-2146x/2148x 5 Mbit internal memory: block k normal-word base and 48-bit (PM) base
NORMAL = {0: 0x90000, 1: 0xB0000, 2: 0xC0000, 3: 0xE0000}
SIZES = {0: 0x10000 + 0x6000, 1: 0x10000 + 0x6000, 2: 0x8000, 3: 0x8000}  # rough; refined below


def to_normal(tag, addr, cnt):
    """Return (lo, hi) normal-word range, or None for external/unknown."""
    if tag in (5, 1):           # 48-bit view: 3 normal words per 2 instructions
        # PM 48-bit blocks: 0x80000 (b0), 0xA0000 (b1), 0xC0000 (b2), 0xE0000 (b3) start in normal space
        for base48, normbase in ((0x80000, 0x80000), (0xA0000, 0xA0000), (0xC0000, 0xC0000), (0xE0000, 0xE0000)):
            pass
        blk = (addr - 0x80000) // 0x20000 if 0x80000 <= addr < 0x100000 else None
        if blk is None:
            return None
        b48 = 0x80000 + 0x20000 * blk
        lo = b48 + (addr - b48) * 3 // 2
        hi = b48 + (addr + cnt - b48) * 3 // 2
        return lo, hi
    if tag in (3,):             # short-word view: 2 per normal word
        if 0x100000 <= addr < 0x200000:
            lo = (addr) // 2
            return lo, (addr + cnt + 1) // 2
        return None
    if 0x80000 <= addr < 0x100000:
        return addr, addr + cnt
    return None


def main():
    e2 = load_e2(sys.argv[1])
    w, bl = blocks(e2)
    print(f'{len(bl)} LDR blocks, {len(e2)} bytes')
    for n, (i, tag, cnt, addr) in enumerate(bl):
        rng = to_normal(tag, addr, cnt)
        r = f'normal {rng[0]:#07x}..{rng[1]:#07x}' if rng else ('external' if addr >= 0x200000 else '')
        print(f'#{n:3d} w{i:6d} {TAGNAME.get(tag, tag):9s} cnt={cnt:#8x} addr={addr:#09x} {r}')


if __name__ == '__main__':
    main()
