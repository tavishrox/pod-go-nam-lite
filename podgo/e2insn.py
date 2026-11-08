"""Decode the POD Go's SHARC 48-bit code (LDR tag 5 and tag 10 blocks) into (pm_addr, insn) pairs,
and list `ureg = data32` immediates (opcode 0x0f, type 17)."""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2blocks import e2_words, blocks


def insns(w):
    out = []
    for b in blocks(w):
        if b['tag'] not in (5,):
            continue
        raw = struct.pack('<%dI' % len(b['data']), *b['data'])
        for k in range(b['cnt']):
            out.append((b['addr'] + k, int.from_bytes(raw[6 * k:6 * k + 6], 'little')))
    return out


def imm32(code):
    for a, x in code:
        if (x >> 40) == 0x0f:
            yield a, (x >> 32) & 0xff, x & 0xffffffff


if __name__ == '__main__':
    w = e2_words(sys.argv[1])
    lo, hi = int(sys.argv[2], 0), int(sys.argv[3], 0)
    code = insns(w)
    print(len(code), 'instructions')
    for a, r, v in imm32(code):
        if lo <= v < hi:
            print(f'{a:#07x} ureg {r:#04x} = {v:#x}')


def visa_parcels(w):
    """(short_addr, parcel) for every 16-bit parcel of the INIT_L16 (tag 3) blocks: VISA code."""
    out = []
    for b in blocks(w):
        if b['tag'] != 3:
            continue
        raw = struct.pack('<%dI' % len(b['data']), *b['data'])
        for k in range(b['cnt']):
            out.append((b['addr'] + k, int.from_bytes(raw[2 * k:2 * k + 2], 'little')))
    return out


def visa_imm32(w):
    p = visa_parcels(w)
    for i in range(len(p) - 2):
        a, x = p[i]
        if (x >> 8) == 0x0f and p[i + 1][0] == a + 1 and p[i + 2][0] == a + 2:
            yield a, x & 0xff, (p[i + 1][1] << 16) | p[i + 2][1]


def visa_parcels_be(w):
    """(short_addr, parcel) of the INIT_L16 (tag 3) code, in execution order: the high half of
    each 32-bit LDR word is the earlier parcel (checked: finds the known IR store addresses)."""
    out = []
    for b in blocks(w):
        if b['tag'] != 3:
            continue
        for k, x in enumerate(b['data']):
            out.append((b['addr'] + 2 * k, x >> 16))
            out.append((b['addr'] + 2 * k + 1, x & 0xFFFF))
    return out


def visa_imm32_be(w):
    p = visa_parcels_be(w)
    for i in range(len(p) - 2):
        a, x = p[i]
        if (x >> 8) == 0x0f and p[i + 2][0] == a + 2:
            yield a, x & 0xff, (p[i + 1][1] << 16) | p[i + 2][1]
