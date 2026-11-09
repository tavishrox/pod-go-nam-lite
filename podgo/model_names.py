"""The NAM block's Model knob shows the slot and its IR's name ("4 Mesa JP2C") instead of 0.3.

Two parts (build_podgo.py --model-names):
  Entry 3: the Model knob's displayType becomes 'dynamicList' (stock: only IR Select has it, an int
           knob). The knob stays a float 0..1 for the DSP and for POD Go Edit; only the text changes.
  Entry 0: the value formatter (0x28cc8f20) picks its float text by display type through a TBH table
           at 0x28cc9072; entry 12 (dynamicList) pointed at the plain-number path. It now points at a
           108-byte cave appended to segment 6 (the app's code), which writes "<slot> <IR name>":
           slot = TRUNC(100 v + 0.5) + 1 as the kernel decodes it, the name from the app's own IR
           table (IR_NAMES, slot 1..128; the record's +0x49 is an id, not the name), bounded by the text's size. Out of range or a short
           buffer: the stock path.
UI only: the knob's value, the DSP and presets are unchanged. docs/PODGO_PORT_MAP.md "Model names".
"""
import struct

SEG6_DST, SEG6_LEN = 0x28c58ba0, 0x8b418     # stock 2.50
CAVE_VA = SEG6_DST + SEG6_LEN                 # 0x28ce3fb8: nothing in the app refers to it
TBH = 0x28cc9072                              # tbh [pc, r3, lsl #1] at 0x28cc906e, r3 = display type - 1
DYNAMIC_LIST = 12
STOCK_ENTRY = (0x28cc928e - TBH) // 2         # the plain-number path
EXIT, DEFAULT = 0x28cc8f6c, 0x28cc928e
ITOA, STRNCPY = 0x28c706d4, 0x28c704d4
IR_NAMES = 0x282c6f9c     # the app's IR table (0x282c6f94, 0x78 bytes a slot): each name at +8, as 0x28cbdf30 reads it
# Stock bytes at the places the cave relies on: the table's site, its exits and the three helpers.
STOCK = {0x28cc906e: 'dfe813f0',                    # tbh [pc, r3, lsl #1]
         0x28cc8f6c: '0020', 0x28cc928e: 'f7ee007a',   # movs r0,#0 ; vmov.f32 s15,#1.0
         0x28c706d4: '70b5', 0x28c704d4: '0346',
         0x28cbdf3e: '064b', 0x28cbdf58: '9c6f2c28'}    # 0x28cbdf30's ldr r3,=IR_NAMES and its literal

# work_irname/cave.s, assembled (arm-none-eabi-as) with the five branches as placeholders: those are
# encoded here for CAVE_VA.
CAVE = bytes.fromhex(
    '0c2e2cd3dfed177a68ee277ab6ee007a77ee877afdeee77a17ee904a0134012c1ddb802c1bdc20462946'
    '00f021f8'                                  # 0x2a bl ITOA
    '2f18202207f8012bb6eb0008a8f10208601ec0eb0010084901ebc00138464246'
    '00f010f8'                                  # 0x4e bl STRNCPY
    'ab19002203f8012c'
    '00f007b8'                                  # 0x5a b.w EXIT
    '00f006b8'                                  # 0x5e b.w DEFAULT
    '00bf'                                      # nop
    '0000c842'                                  # .float 100.0
    '9c6f2c28')                                 # .word IR_NAMES
BRANCHES = ((0x2a, ITOA, True), (0x4e, STRNCPY, True), (0x5a, EXIT, False), (0x5e, DEFAULT, False))


def thumb_branch(src, dst, link):
    """Thumb-2 B.W (T4) or BL at src to dst."""
    off = dst - (src + 4)
    assert off % 2 == 0 and -(1 << 24) <= off < (1 << 24), f'{src:#x} -> {dst:#x} out of range'
    s, i1, i2 = (off >> 24) & 1, (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    return struct.pack('<2H', 0xf000 | (s << 10) | ((off >> 12) & 0x3ff),
                       (0xd000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7ff))


def cave(va=CAVE_VA):
    b = bytearray(CAVE)
    for at, dst, link in BRANCHES:
        b[at: at + 4] = thumb_branch(va + at, dst, link)
    assert len(b) % 4 == 0 and struct.unpack_from('<fI', b, len(b) - 8) == (100.0, IR_NAMES)
    return bytes(b)


def entry0(e0, log=print):
    """Entry 0 (swapped payload) with the cave appended to segment 6 and the table entry moved."""
    import patch_amp as pa
    e0 = bytearray(e0)
    segs = pa._parse_e0_segments(e0)
    hdr, poff, slen, dst, nxt = segs[6]
    assert (dst, slen) == (SEG6_DST, SEG6_LEN) and len(e0) - nxt < 4 and not any(e0[nxt:]), \
        'Entry 0 is not the stock 2.50 layout'
    fo = lambda va: pa._e0_vaddr_to_foff(segs, va)
    for va, want in STOCK.items():
        got = bytes(e0[fo(va): fo(va) + len(want) // 2])
        assert got == bytes.fromhex(want), f'Entry 0 at {va:#x} is {got.hex()}, not {want}'
    at = fo(TBH + 2 * (DYNAMIC_LIST - 1))
    assert struct.unpack_from('<H', e0, at)[0] == STOCK_ENTRY, 'the dynamicList table entry is not stock'
    code = cave()
    new = (CAVE_VA - TBH) // 2
    assert new <= 0xffff
    struct.pack_into('<H', e0, at, new)
    out = e0[:nxt] + code                       # segment 6 is the last: the entry ends with it, then padding
    out += b'\x00' * ((-len(out)) & 3)
    struct.pack_into('<3I', out, hdr, slen + len(code), dst, poff + slen + len(code))
    struct.pack_into('<I', out, 4, len(out))
    log(f'[+] Entry 0: Model knob shows "<slot> <IR name>" (cave {len(code)} B at {CAVE_VA:#x})')
    return bytes(out)


def model_meta(meta):
    """The Model knob's Entry 3 meta with displayType dynamicList (the cave's marker)."""
    out = [(k, t, 'dynamicList' if k == 'displayType' else v) for k, t, v in meta]
    assert ('displayType', 7, 'dynamicList') in out
    return out
