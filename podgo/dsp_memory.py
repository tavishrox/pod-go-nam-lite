#!/usr/bin/env python3
"""Static map of the POD Go 2.50 SHARC's memory use, for placing the NAM kernel (read only).

    python3 podgo/dsp_memory.py POD_Go_v2.50.0_0x6e984472.hxf

Prints (1) what the LDR boot stream initialises in internal Blocks 2 and 3, (2) every
`ureg = data32` immediate in the boot code that names Block 2, Block 3 or SDRAM, with the
valid register groups only (R, I, M, L, B), and (3) the Blob 0 buffer set-up.
VISA (compact) code: the high half of each 32-bit LDR word is the earlier 16-bit parcel
(checked: this finds the User IR store addresses 0x26758e / 0x26760e in the IR copy code).
Static only: run-time allocations that no constant names are not seen. docs/PODGO_PORT_MAP.md.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2blocks import e2_words, blocks           # noqa: E402
from e2insn import insns, imm32, visa_imm32_be   # noqa: E402

GROUP = {0x0: 'R', 0x1: 'I', 0x2: 'M', 0x3: 'L', 0x4: 'B'}


def reg(u):
    g = GROUP.get(u >> 4)
    return f'{g}{u & 15}' if g else None


def main():
    w = e2_words(sys.argv[1])
    print('LDR blocks touching Block 2 (0xc0000..0xc8000) and Block 3 (0xe0000..0xe8000), normal words:')
    for b in blocks(w):
        if b['tag'] in (1, 4) and (0xc0000 <= b['addr'] < 0xc8000 or 0xe0000 <= b['addr'] < 0xe8000):
            kind = 'zero' if b['tag'] == 1 else 'init'
            print(f"  {kind} {b['addr']:#x}..{b['addr'] + b['cnt']:#x}")
    hits = sorted(set(visa_imm32_be(w)) | set(imm32(insns(w))))
    print('\nImmediates naming Block 2/3 or SDRAM (valid R/I/M/L/B targets only):')
    for a, u, v in hits:
        r = reg(u)
        if r and (0xc0000 <= v < 0xc8000 or 0xe0000 <= v < 0xe8000 or 0x200000 <= v < 0x400000):
            print(f'  {a:#08x}  {r:4s} = {v:#x}')
    print('\nBlob 0 buffer: R0 = size, R0 = address (0x16aaad / 0x16aab5):')
    for a, u, v in hits:
        if a in (0x16aaad, 0x16aab5):
            print(f'  {a:#08x}  {reg(u)} = {v:#x}')


if __name__ == '__main__':
    main()
