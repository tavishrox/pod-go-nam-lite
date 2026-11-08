"""The POD Go's SHARC program patch (podgo/podgo_e2.py), checked against the stock 2.50 file.

Needs PODGO_HXF=path/to/POD_Go_v2.50.0_0x6e984472.hxf (the file is not in this repository).
"""
import os
import struct
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "podgo"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "sharc"))

HXF = os.environ.get("PODGO_HXF")
pytestmark = pytest.mark.skipif(not HXF or not os.path.exists(HXF), reason="PODGO_HXF is not set")

ASM = """
.section pm 0x0c4ef8
CUSTOM_AMP_ENTRY:
    RTS;
    NOP;
.section dm 0xe4850
    .word 0x12345678
.section dm 0x2f8000
    .word 0x0badf00d
"""


@pytest.fixture(scope="module")
def stock_and_patched():
    import e2blocks
    import podgo_e2
    stock = e2blocks.e2_words(HXF)
    raw = struct.pack("<%dI" % len(stock), *stock)
    new = podgo_e2.patch_e2(raw, ASM, "t.asm", log=lambda *a: None)
    return stock, list(struct.unpack("<%dI" % (len(new) // 4), new))


def test_stream_parses_to_final(stock_and_patched):
    import e2blocks
    _, new = stock_and_patched
    bl = e2blocks.blocks(new)
    assert bl[-1]["tag"] == 0
    assert any(b["tag"] == 5 and b["addr"] == 0x0c4ef8 for b in bl)
    assert any(b["tag"] == 4 and b["addr"] == 0x2f8000 and b["data"][0] == 0x0badf00d for b in bl)


def test_stock_code_unchanged(stock_and_patched):
    """GROW_BLOB0 off (the default since the unit test of 2026-11-07): only LDR blocks are added."""
    import podgo_e2
    stock, new = stock_and_patched
    k = podgo_e2._final_index(stock)
    added = len(new) - len(stock)
    assert new[k + added:] == stock[k:]                     # FINAL_INIT and after: as stock
    assert new[:k] == stock[:k]


def test_grow_blob0_immediates():
    """The optional buffer patch still finds and changes exactly its four immediates."""
    import e2blocks
    import podgo_e2
    stock = e2blocks.e2_words(HXF)
    new = podgo_e2.patch_blob0_and_region(list(stock))
    diff = [i for i in range(len(stock)) if stock[i] != new[i]]
    assert 1 <= len(diff) <= 8
    slots = podgo_e2._visa_slots(new)
    for a, reg, old, want in podgo_e2.IMMEDIATES:
        assert podgo_e2.visa_imm32(new, slots, a) == (reg, want)
        assert podgo_e2.visa_imm32(stock, podgo_e2._visa_slots(stock), a) == (reg, old)


def test_hook_record(stock_and_patched):
    import e2blocks
    import podgo_e2
    _, new = stock_and_patched
    rec = [b for b in e2blocks.blocks(new) if b["tag"] == 4 and b["addr"] == podgo_e2.PRIM_DESC]
    assert len(rec) == 1
    assert rec[0]["data"] == [0x9c75, 0x60d8f2, 0, 0x60d956, 0x60d83f, 0x0c4ef8, 0x91, 0x0d]


def test_patch_is_idempotent_on_immediates():
    import e2blocks
    import podgo_e2
    once = podgo_e2.patch_blob0_and_region(list(e2blocks.e2_words(HXF)))
    assert podgo_e2.patch_blob0_and_region(list(once)) == once     # accepts its own values


def test_layout_constants():
    import podgo_e2
    assert podgo_e2.BLOB0_BUF + podgo_e2.BLOB0_WORDS <= podgo_e2.REGION_B
    assert podgo_e2.STATIC_SDR[1] <= podgo_e2.SDRAM_WINDOW[0] <= podgo_e2.SDRAM_WINDOW[1] <= 0x300000
