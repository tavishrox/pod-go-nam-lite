#!/usr/bin/env python3
"""The POD Go 2.50's SHARC program (Entry 2) with NAM A2 Lite: the POD Go counterpart of
tools/patch_amp.py's `patch` and expand_sharc_blob0_buffer (docs/PODGO_PORT_MAP.md).

    python3 podgo/podgo_e2.py IN.hxf|IN.l6ia OUT.l6ia --asm build/nam_lite_podgo.asm

1. Blob 0 buffer: its size immediate (R0 = 0x57ff1 at VISA 0x16aaad, exactly stock Blob 0)
   becomes BLOB0_WORDS, and region A (0x25c3f2..0x2673fc), which the larger buffer would
   overlap, moves to free SDRAM (start M3 at 0x16cf9d and R4 at 0x16cfb0, end I3 at 0x16cfa7).
2. The kernel's .section pm/dm as LDR INIT blocks before FINAL_INIT (the Stomp's way).
3. Primitive 0x9c75 (registered at 0x200588, used by no stock model) pointed at the kernel, with
   the handler words of primitive 0x822's record (the HX Effects build copies the same one).

Every immediate is checked against its stock value (or this patch's own) before it is changed,
so a wrong firmware stops here.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
sys.path.insert(0, os.path.join(HERE, '..', 'tools', 'sharc'))
import l6ia            # noqa: E402
import patch_amp       # noqa: E402
import sasm            # noqa: E402

STOCK_BLOB0 = 0x57ff1
BLOB0_WORDS = 0x5fff1                     # +32k words of headroom: buffer 0x204400..0x2643f1
BLOB0_BUF = 0x204400
REGION_A = (0x25c3f2, 0x2673fc)           # stock place
REGION_A_NEW = (0x2c4000, 0x2cf00a)       # in the 0x2c31f6..0x300000 gap no constant names, below
STATIC_SDR = (0x2e0000, 0x2f8000)         # the kernel's per-slot SDRAM (nam_multi.py --static-sdram)
# On the unit (2026-11-07): region A moved to 0x2c4000 froze the UI (0x2c4000.. is used at run time by
# something no constant names); at 0x2d0000 it worked. NAM's graph now overwrites an unused composite
# (podgo_model.SPARE_COMP), so Blob 0 keeps its size: the buffer and region A stay stock by default.
GROW_BLOB0 = False
REGION_B = 0x2673fc                       # the next region: the buffer must end before it

# (VISA short address of the 0x0fXX parcel, register code, stock value, new value)
IMMEDIATES = (
    (0x16aaad, 0x00, STOCK_BLOB0, BLOB0_WORDS),          # R0 = Blob 0 buffer size
    (0x16cf9d, 0x23, REGION_A[0], REGION_A_NEW[0]),      # M3 = region A start
    (0x16cfa7, 0x13, REGION_A[1], REGION_A_NEW[1]),      # I3 = region A end
    (0x16cfb0, 0x04, REGION_A[0], REGION_A_NEW[0]),      # R4 = region A start (its clear)
)
BLOB0_ADDR_IMM = (0x16aab5, 0x00, BLOB0_BUF)             # checked, not changed

PRIM, PRIM_DESC, PRIM_TEMPLATE = 0x9c75, 0x200588, 0x822
TEMPLATE_WORDS = (0x60d8f2, 0x0, 0x60d956, 0x60d83f)
KERNEL_DM, KERNEL_PM = 0x91, 0x0d
PM_WINDOWS = ((0x0c4ef8, 0x0c5554), (0x0e302c, 0x0e5555))   # the unused tails (dsp_memory.py)
SDRAM_WINDOW = (0x2f8000, 0x300000)                         # where the kernel's SDRAM data may go
assert BLOB0_BUF + BLOB0_WORDS <= REGION_B
assert REGION_A_NEW[1] - REGION_A_NEW[0] == REGION_A[1] - REGION_A[0]
assert STATIC_SDR[1] <= SDRAM_WINDOW[0]


def _visa_slots(w):
    """{short address: (word index, 'hi'|'lo')} for every parcel of the INIT_L16 blocks."""
    out, i = {}, 384
    while i + 3 <= len(w):
        tag, cnt, addr = w[i:i + 3]
        n = {5: ((cnt + 1) & ~1) * 3 // 2, 4: cnt, 3: (cnt + 1) // 2, 6: cnt * 2, 0: 384,
             10: cnt, 9: cnt, 1: 0, 2: 0}[tag]
        if tag == 3:
            for k in range(n):
                out[addr + 2 * k] = (i + 3 + k, 'hi')       # the earlier parcel is the high half
                out[addr + 2 * k + 1] = (i + 3 + k, 'lo')
        if tag == 0:
            break
        i += 3 + n
    return out


def _get(w, slot):
    j, h = slot
    return w[j] >> 16 if h == 'hi' else w[j] & 0xFFFF


def _put(w, slot, v):
    j, h = slot
    w[j] = (w[j] & 0xFFFF) | v << 16 if h == 'hi' else (w[j] & 0xFFFF0000) | v


def visa_imm32(w, slots, a):
    """(register code, value) of the `ureg = data32` instruction whose first parcel is at a."""
    p0 = _get(w, slots[a])
    if p0 >> 8 != 0x0F:
        raise SystemExit(f'VISA {a:#x}: {p0:#06x} is not a ureg = data32 instruction')
    return p0 & 0xFF, _get(w, slots[a + 1]) << 16 | _get(w, slots[a + 2])


def set_visa_imm32(w, slots, a, value):
    _put(w, slots[a + 1], value >> 16)
    _put(w, slots[a + 2], value & 0xFFFF)


def patch_blob0_and_region(w):
    slots = _visa_slots(w)
    r, v = visa_imm32(w, slots, BLOB0_ADDR_IMM[0])
    assert (r, v) == BLOB0_ADDR_IMM[1:], f'Blob 0 buffer address: {r:#x} = {v:#x}'
    for a, reg, old, new in IMMEDIATES:
        r, v = visa_imm32(w, slots, a)
        if r != reg or v not in (old, new):
            raise SystemExit(f'VISA {a:#x}: register {r:#x} = {v:#x}, expected {reg:#x} = {old:#x}: '
                             'not the POD Go 2.50 SHARC program')
        set_visa_imm32(w, slots, a, new)
    return w


def _final_index(w):
    i = 384
    while True:
        tag, cnt, addr = w[i:i + 3]
        if tag == 0:
            return i
        i += 3 + {5: ((cnt + 1) & ~1) * 3 // 2, 4: cnt, 3: (cnt + 1) // 2, 6: cnt * 2,
                  10: cnt, 9: cnt, 1: 0, 2: 0}[tag]


def prim_record(w):
    """The registry (INIT_L32 at 0x200000) as {id: (address, words)}."""
    i = 384
    while not (w[i] == 4 and w[i + 2] == 0x200000):
        tag, cnt = w[i], w[i + 1]
        i += 3 + {5: ((cnt + 1) & ~1) * 3 // 2, 4: cnt, 3: (cnt + 1) // 2, 6: cnt * 2,
                  10: cnt, 9: cnt, 1: 0, 2: 0}[tag]
    tab = w[i + 3: i + 3 + w[i + 1]]
    return {tab[k]: (0x200000 + k, tab[k:k + 8]) for k in range(0, 0x600, 8)}


def patch_e2(e2_raw, asm_src, asm_name='kernel.asm', log=print):
    w = list(struct.unpack('<%dI' % (len(e2_raw) // 4), e2_raw))
    recs = prim_record(w)
    assert recs[PRIM][0] == PRIM_DESC, f'primitive {PRIM:#x} is not at {PRIM_DESC:#x}'
    assert tuple(recs[PRIM_TEMPLATE][1][1:5]) == TEMPLATE_WORDS, \
        f'primitive {PRIM_TEMPLATE:#x}: {[hex(x) for x in recs[PRIM_TEMPLATE][1]]}'
    if GROW_BLOB0:
        w = patch_blob0_and_region(w)
        log(f'[+] Entry 2: Blob 0 buffer {STOCK_BLOB0:#x} -> {BLOB0_WORDS:#x} words at {BLOB0_BUF:#x}; '
            f'region A {REGION_A[0]:#x}.. -> {REGION_A_NEW[0]:#x}..{REGION_A_NEW[1]:#x}')

    secs, syms = sasm.assemble(asm_src, asm_name)
    # the POD Go calls with 32 samples: the wrapper (nam_multi.py --block32) when the kernel has it
    entry = syms.get('NAM_ENTRY32', syms.get('CUSTOM_AMP_ENTRY', next(s.addr for s in secs if s.kind == 'pm')))
    ldr = []
    for s in secs:
        if s.kind == 'pm':
            assert any(lo <= s.addr and s.addr + len(s.words) <= hi for lo, hi in PM_WINDOWS), \
                f'PM section at {s.addr:#x}+{len(s.words):#x} outside the free Block 2/3 tails'
            ldr += patch_amp.pack_init_l48(s.addr, s.words)
            log(f'[+] Entry 2: {len(s.words)} instructions @ PM {s.addr:#x}')
        elif s.kind == 'dm':
            if s.addr >= 0x200000:
                assert SDRAM_WINDOW[0] <= s.addr and s.addr + len(s.words) <= SDRAM_WINDOW[1], \
                    f'SDRAM section at {s.addr:#x} outside {SDRAM_WINDOW}'
            else:
                assert 0xc08e4 <= s.addr < 0xc8000 or 0xe2560 <= s.addr < 0xe8000, \
                    f'DM section at {s.addr:#x} outside the free Block 2/3 tails'
            ldr += patch_amp.pack_init_l32(s.addr, s.words)
            log(f'[+] Entry 2: {len(s.words)} words @ DM {s.addr:#x}')
    ldr += patch_amp.pack_init_l32(PRIM_DESC, [PRIM, *TEMPLATE_WORDS, entry, KERNEL_DM, KERNEL_PM])
    log(f'[+] Entry 2: primitive {PRIM:#x} @ {PRIM_DESC:#x} -> kernel {entry:#x}')
    k = _final_index(w)
    out = w[:k] + ldr + w[k:]
    assert len(out) * 4 <= 0x80000, f'Entry 2 would be {len(out) * 4:#x} bytes; its partition holds 0x80000'
    return struct.pack('<%dI' % len(out), *out)


def main():
    a = sys.argv[1:]
    if len(a) < 4 or '--asm' not in a:
        sys.exit(__doc__)
    src, dst, asm = a[0], a[1], a[a.index('--asm') + 1]
    data, is_hxf = patch_amp.load_l6ia_from_any(src)
    ents = l6ia.parse(data)
    e2 = data[ents[2]['payload_off']: ents[2]['payload_off'] + ents[2]['payload_len']]
    new = patch_e2(e2, open(asm).read(), os.path.basename(asm))
    out, old_end, new_end = l6ia.rebuild_archive(data, {2: l6ia.swap32(new)})
    patch_amp.save_l6ia_to_any(out, dst, donor_hxf=src if is_hxf else None)
    print(f'[+] wrote {dst} (L6IA {old_end:#x} -> {new_end:#x} bytes)')


if __name__ == '__main__':
    main()
