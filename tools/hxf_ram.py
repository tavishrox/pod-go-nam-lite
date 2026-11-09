#!/usr/bin/env python3
"""hxf_ram.py - run a built HX Stomp (or HX Stomp XL) .hxf from RAM, writing nothing to the
eMMC: try the firmware before installing it. A power-cycle brings back what is
installed. How it works: RAM_RUN.md. The setup page (web/index.html) does the
same in the browser, over WebUSB.

    # Page Right at power-up (update mode), then:
    dfu-util -d 1fc9:000c -a 0 -D tools/ramboot/firmware-ramboot.dfu
    python3 tools/hxf_ram.py run build/HX_Stomp_v3.80.0_NAM_A2_Lite.hxf \\
        --stock HX_Stomp_v3.80.0_0x103966115.hxf

    python3 tools/hxf_ram.py plan FIRMWARE --stock STOCK.hxf [--out DIR]
                                         the same checks and layout, no unit
    python3 tools/hxf_ram.py info        what the loader reports

The changed firmware's application (entry 0) is loaded whole, checked the way
the stock bootloader checks it. Every other entry is compared with the stock
.hxf sector by sector; the sectors that differ become an overlay in SDRAM, and
two 8-byte jumps put into the application send its eMMC reads and writes
through src/ramboot/ramboot_hook.c, which serves those sectors from SDRAM. This
needs the unit's eMMC to hold the stock firmware given with --stock (or this
same build): `run` checks that first (CRC of every sector the overlay leaves to
the card, per changed entry) when the loader could start the eMMC, unless
--no-emmc-check.

Writes the application makes (presets, settings, imported IRs) go to SDRAM by
default and are gone at power-off (--writes ram); --writes pass lets those
outside the overlay reach the card.
"""
import argparse
import json
import os
import struct
import sys
import time
import zlib

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)

SECTOR = 512
VID, PID = 0x1209, 0x0001
PRODUCTS = {0x0006: "HX Stomp", 0x000B: "HX Stomp XL", 0x0007: "POD Go"}   # .hxf HEAD word at 0x0A

# src/ramboot/ramboot.h (web/ramrun.js keeps a copy too: keep the three the same)
RB_VERSION = 1
RB_HOOK_BASE, RB_STAGE_BASE, RB_DESC, RB_FREE_END = 0x29000000, 0x29E00000, 0x29EFF000, 0x29F00000
REQ_INFO, REQ_ADDR, REQ_DATA, REQ_LEN, REQ_CRC, REQ_EMMC_CRC, REQ_GO, REQ_CMD = 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 2
GO_KEY, CHUNK = 0x60B0, 4096
DESC_MAGIC, MAX_COPIES = 0x47425852, 16

# src/ramboot/ramboot_hook.c's header (format version 1)
HOOK_MAGIC = 0x48425852
H_READ, H_WRITE, H_CARD, H_RCONT, H_WCONT, H_TABLE, H_MODE, H_PSLOTS, H_PDATA, H_PSECT = (
    0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C)

# The stock 3.80 applications, by the CRC of entry 0: their two eMMC functions and
# the card struct their literal names (RAM_RUN.md). Each begins push.w {r4-r11, lr};
# ldr r5, [pc, #512]; ldr.w r3, [r5, #0x248]. The XL's is the same code at other
# addresses (found by matching the Stomp's bytes; not yet run on an XL).
APPS = {
    0x2B81E740: ("HX Stomp", {"read": (0x28da5354, 0x28da555c), "write": (0x28da5708, 0x28da5910)}, 0x281d0eac),
    0xF8CD14D3: ("HX Stomp XL", {"read": (0x28da82d4, 0x28da84dc), "write": (0x28da8688, 0x28da8890)}, 0x281d211c),
    # POD Go 2.50 (docs/PODGO_PORT_MAP.md): the same two functions, found by their prologue (the only
    # two hits); both literals hold the card struct 0x28230740. Not yet run on a POD Go.
    0xE0891668: ("POD Go", {"read": (0x28c6aa04, 0x28c6ac0c), "write": (0x28c6adb8, 0x28c6afc0)}, 0x28230740),
    # POD Go 2.50 with NAM A2 Lite installed (release/POD_Go_v2.50.0_NAM_A2_Lite_Elektrik.hxf): only its
    # data segment (0x28001a7c: names, Table 1 cost) differs from stock; the code segment is the same bytes.
    0xA2399A2E: ("POD Go", {"read": (0x28c6aa04, 0x28c6ac0c), "write": (0x28c6adb8, 0x28c6afc0)}, 0x28230740),
}
PROLOGUE = bytes.fromhex("2de9f04f804dd5f84832")

# The stock bootloader's check of entry 0 (0x14005d60, 0x140021d0)
APP_MAGIC, APP_MAX = 0x230B0C5E, 0x400000
ALLOWED = ((0x10000000, 0x10020000), (0x10080000, 0x10092000), (0x20000000, 0x20010000), (0x28000000, 0x29F00000))

# Where each entry's payload starts on the eMMC, and where the next partition
# begins (Line 6 Updater's partition table).
PART_START = (0x0, 0x8001, 0x8802, 0x8c03, 0x940c, 0x11005, 0x11406, 0x19407, 0x19c08,
              0x11f753, 0x120956, 0x1209f7, 0x120a98, 0x1a14da, 0x222856)
PAYLOAD = tuple(s + 1 for s in PART_START)
PART_END = PART_START[1:] + (None,)

# The POD Go's partitions are not known from any file: `hxf_ram.py layout` finds where each stock
# entry's payload starts on the card (read only) and writes them here.
LAYOUT_DIR = os.path.join(TOOLS, "..", "podgo")
LAYOUT_FILE = {"POD Go": os.path.join(LAYOUT_DIR, "emmc_layout_podgo_2.50.json")}


def use_layout(unit):
    """Point PAYLOAD / PART_END at the unit's partitions (the Stomp's are built in)."""
    global PAYLOAD, PART_END
    if unit not in LAYOUT_FILE:
        PAYLOAD, PART_END = tuple(s + 1 for s in PART_START), PART_START[1:] + (None,)
        return
    path = LAYOUT_FILE[unit]
    if not os.path.exists(path):        # fine while no entry but the application changes (overlay() checks)
        PAYLOAD = PART_END = None
        return
    lay = json.load(open(path))
    pay = lay["payload"]
    PAYLOAD = tuple(pay)                    # None: not located (overlay() refuses to change it)
    ends = []
    for i in range(len(pay)):               # each payload follows a 1-sector sub-header
        nxt = next((p for p in pay[i + 1:] if p is not None), None)
        ends.append(nxt - 1 if nxt is not None else None)
    PART_END = tuple(ends)


def fail(msg):
    sys.exit(f"hxf_ram: {msg}")


# ------------------------------------------------------------------ firmware

def load(path, stock=False, any_count=False):
    """The entries of an .hxf or L6IA file, in the eMMC's (little-endian) form."""
    import hxf
    import l6ia
    raw = open(path, "rb").read()
    if raw[:4] == b"FORM":
        ch = {c: b for c, p, s, b in hxf._chunks(raw)}
        product = struct.unpack_from(">H", ch[b"HEAD"], 0x0A)[0]
        if product not in PRODUCTS:
            fail(f"{path}: product {product:#06x} is not one this tool knows")
        data = zlib.decompress(ch[b"data"])
    elif raw[:4] == b"L6IA":
        if stock:
            fail(f"{path}: --stock must be the unit's stock .hxf (its HEAD names the product)")
        data = raw
    else:
        fail(f"{path}: neither an .hxf nor an L6IA archive")
    ents = l6ia.parse(data)
    if not any_count and PAYLOAD is not None and len(ents) != len(PAYLOAD):
        fail(f"{path}: {len(ents)} entries, the unit's layout has {len(PAYLOAD)}")
    return [l6ia.swap32(data[e["payload_off"]: e["payload_off"] + e["payload_len"]]) for e in ents]


def unit_of(path):
    """The product an .hxf's HEAD names."""
    import hxf
    raw = open(path, "rb").read()
    if raw[:4] != b"FORM":
        fail(f"{path}: --stock must be the unit's stock .hxf (its HEAD names the product)")
    ch = {c: b for c, p, s, b in hxf._chunks(raw)}
    product = struct.unpack_from(">H", ch[b"HEAD"], 0x0A)[0]
    if product not in PRODUCTS:
        fail(f"{path}: product {product:#06x} is not one this tool knows")
    return PRODUCTS[product]


def app_of(e0):
    """The APPS entry (unit, eMMC functions, card) of a stock entry 0, or None.

    By the CRC of a known application; otherwise (a NAM build that adds code, e.g. --model-names)
    when both eMMC functions of a known POD Go application are there byte for byte at the same
    addresses, prologue and card literal included: the hook only needs those."""
    known = APPS.get(zlib.crc32(e0[0x34:struct.unpack_from("<I", e0, 4)[0]]))
    if known:
        return known
    try:
        segs = app_segments(e0)[0]
    except SystemExit:
        return None
    for unit, funcs, card in APPS.values():
        if unit != "POD Go":
            continue
        ok = True
        for start, _ in funcs.values():
            lit = ((start + 4 + 4) & ~3) + 0x200       # ldr r5, [pc, #512] after the 4-byte push.w
            try:
                ok &= (seg_read(segs, start, len(PROLOGUE)) == PROLOGUE and
                       struct.unpack("<I", seg_read(segs, lit, 4))[0] == card)
            except SystemExit:
                ok = False
        if ok:
            return unit, funcs, card
    return None


def app_segments(e0):
    """Entry 0's segments [(addr, bytes)] and entry point, with every check the bootloader makes."""
    if len(e0) < 0x34:
        fail("entry 0 is too short")
    h = struct.unpack_from("<13I", e0, 0)
    magic, size, crc, kind, nseg, entry = h[:6]
    if magic != APP_MAGIC or kind != 2:
        fail(f"entry 0: magic {magic:#x} / field {kind}: not an application image")
    if size > APP_MAX or size > len(e0):
        fail(f"entry 0: size {size:#x} (at most {APP_MAX:#x})")
    if crc == 0 or zlib.crc32(e0[0x34:size]) != crc:
        fail("entry 0: CRC does not match its header (the bootloader would stop here)")
    if h[8] & 1:
        fail("entry 0: flags bit 0 set (the bootloader refuses it)")
    segs, off = [], 0x34
    for _ in range(nseg):
        n, addr, _end = struct.unpack_from("<3I", e0, off)
        body = e0[off + 12: off + 12 + n]
        if len(body) != n or not any(lo <= addr and addr + n <= hi for lo, hi in ALLOWED):
            fail(f"entry 0: segment {addr:#x}+{n:#x} outside the bootloader's ranges")
        segs.append((addr, body))
        off += 12 + n
    if not any(a <= (entry & ~1) < a + len(b) for a, b in segs):
        fail(f"entry 0: entry point {entry:#x} is in no segment")
    return segs, entry


def seg_read(segs, addr, n):
    for a, b in segs:
        if a <= addr and addr + n <= a + len(b):
            return b[addr - a: addr - a + n]
    fail(f"{addr:#x}: not in the application")


def seg_patch(segs, addr, data):
    for i, (a, b) in enumerate(segs):
        if a <= addr and addr + len(data) <= a + len(b):
            segs[i] = (a, b[:addr - a] + data + b[addr - a + len(data):])
            return
    fail(f"{addr:#x}: not in the application")


def overlay(stock, new):
    """[(sector, data)] for every sector of entries 1.. that differs from stock,
    and a line per changed entry."""
    out, notes = [], []
    for i in range(1, len(new)):
        a, b = stock[i], new[i]
        if a == b:
            continue
        if i == 1:
            fail("entry 1 (the bootloader) differs from stock: not something to run from RAM")
        if PAYLOAD is None or PAYLOAD[i] is None:
            fail(f"entry {i} differs from stock, and where it is on this unit's eMMC is not known yet: "
                 "with the loader running, hxf_ram.py layout --stock STOCK.hxf")
        room = (PART_END[i] - PAYLOAD[i]) * SECTOR if PART_END[i] else None
        if room is not None and len(b) > room:
            fail(f"entry {i}: {len(b):#x} bytes, its partition holds {room:#x}")
        n = 0
        for k in range(0, len(b), SECTOR):
            sb = b[k:k + SECTOR].ljust(SECTOR, b"\0")
            sa = a[k:k + SECTOR]
            if len(sa) < SECTOR or sa != sb:      # past stock's end the card holds nothing we know
                out.append((PAYLOAD[i] + k // SECTOR, sb))
                n += 1
        notes.append((i, len(a), len(b), n))
    return out, notes


def runs_of(sectors):
    runs = []
    for s, d in sorted(sectors):
        if runs and runs[-1][0] + len(runs[-1][1]) // SECTOR == s:
            runs[-1][1].extend(d)
        else:
            runs.append([s, bytearray(d)])
    return runs


def plan(firmware, stock_path, writes="ram", pool_sectors=4096, hook_bin=None):
    """Everything to load: regions [(addr, bytes, label)], the stock entries,
    the checks of the eMMC [(first sector, count, crc)] and a summary."""
    unit = unit_of(stock_path)
    use_layout(unit)
    stock, new = load(stock_path, stock=True), load(firmware)
    app = app_of(stock[0])
    if app is None:
        fail(f"{stock_path}: not an application this tool knows (HX Stomp/XL 3.80 or POD Go 2.50)")
    unit, emmc_funcs, card = app
    segs, entry = app_segments(new[0])
    if app_segments(stock[0])[0][-1][0] != segs[-1][0]:
        fail(f"{firmware} is not built from the {unit}'s firmware given with --stock")

    hook_bin = hook_bin or os.path.join(TOOLS, "ramboot", "ramboot-hook.bin")
    if not os.path.exists(hook_bin):
        fail(f"{hook_bin} missing (make -C src/ramboot)")
    hook = bytearray(open(hook_bin, "rb").read())
    if struct.unpack_from("<2I", hook, 0) != (HOOK_MAGIC, 1):
        fail(f"{hook_bin}: not a version 1 hook")

    # the two jumps: ldr.w pc, [pc, #0] and the hook's address
    for name, (fn, lit) in emmc_funcs.items():
        if seg_read(segs, fn, len(PROLOGUE)) != PROLOGUE or struct.unpack("<I", seg_read(segs, lit, 4))[0] != card:
            fail(f"the application's {name}_blocks at {fn:#x} is not the one this tool knows")
        target = struct.unpack_from("<I", hook, H_READ if name == "read" else H_WRITE)[0]
        seg_patch(segs, fn, bytes.fromhex("dff800f0") + struct.pack("<I", target))

    sectors, notes = overlay(stock, new)
    runs = runs_of(sectors)
    table = RB_HOOK_BASE + ((len(hook) + 15) & ~15)
    data = (table + 4 + 12 * len(runs) + 15) & ~15
    blob = bytearray(struct.pack("<I", len(runs)))
    at = data
    for s, d in runs:
        blob += struct.pack("<3I", s, len(d) // SECTOR, at)
        at += len(d)
    blob = blob.ljust(data - table, b"\0") + b"".join(bytes(d) for _, d in runs)
    pslots = (at + 15) & ~15
    pdata = (pslots + 4 * pool_sectors + SECTOR - 1) & ~(SECTOR - 1)
    end = pdata + SECTOR * pool_sectors
    if end > RB_STAGE_BASE:
        fail(f"overlay and pool end at {end:#x}, past {RB_STAGE_BASE:#x}: too much changed (or a smaller --pool)")
    struct.pack_into("<I", hook, H_CARD, card)
    struct.pack_into("<2I", hook, H_RCONT, emmc_funcs["read"][0] + 10 + 1, emmc_funcs["write"][0] + 10 + 1)
    struct.pack_into("<I", hook, H_TABLE, table)
    struct.pack_into("<I", hook, H_MODE, 0 if writes == "ram" else 1)
    struct.pack_into("<3I", hook, H_PSLOTS, pslots, pdata, pool_sectors)
    hook_region = bytes(hook).ljust(table - RB_HOOK_BASE, b"\0") + bytes(blob)
    hook_region = hook_region.ljust(pdata - RB_HOOK_BASE, b"\0")       # pool keys zero (pool data need not be sent)

    # SDRAM segments go straight to their place; SRAM ones are staged and copied at the jump
    regions, copies, stage = [], [], RB_STAGE_BASE
    for a, b in segs:
        b = b + bytes(-len(b) % 4)
        if a >= 0x28000000:
            if a < RB_FREE_END and a + len(b) > RB_HOOK_BASE:
                fail(f"application segment {a:#x}+{len(b):#x} overlaps the free SDRAM this tool uses")
            regions.append((a, b, f"segment {a:#010x}"))
        else:
            regions.append((stage, b, f"segment {a:#010x} (staged)"))
            copies.append((a, stage, len(b)))
            stage = (stage + len(b) + 15) & ~15
    if stage > RB_DESC or len(copies) > MAX_COPIES:
        fail("the SRAM segments do not fit the staging area")
    param = struct.unpack_from("<I", new[0], 0x18)[0]
    desc = struct.pack("<4I", DESC_MAGIC, entry, len(copies), param) + b"".join(struct.pack("<3I", *c) for c in copies)
    regions.append((RB_HOOK_BASE, hook_region, "hook, overlay table and sectors"))
    regions.append((RB_DESC, desc, "boot descriptor"))

    checks = []                                 # the sectors the overlay leaves to the card must be stock
    for i, la, lb, n in notes:
        full = la // SECTOR
        for k in range(0, full, 2048):
            c = min(2048, full - k)
            checks.append((PAYLOAD[i] + k, c, zlib.crc32(stock[i][k * SECTOR:(k + c) * SECTOR]), i))
    summary = {
        "entry": entry, "segments": [(a, len(b)) for a, b in segs], "changed": notes,
        "overlay_sectors": len(sectors), "runs": len(runs), "table": table, "pool": (pslots, pdata, pool_sectors),
        "end": end, "writes": writes, "unit": unit,
    }
    return regions, checks, summary


def describe(summary, checks):
    print(f"[+] {summary['unit']} application: entry {summary['entry']:#x}, " +
          ", ".join(f"{a:#x}+{n:#x}" for a, n in summary["segments"]))
    for i, la, lb, n in summary["changed"]:
        print(f"[+] entry {i}: {la:#x} -> {lb:#x} bytes, {n} sectors ({n * SECTOR / 1024:.0f} KiB) in the overlay")
    if not summary["changed"]:
        print("[+] no entry but the application differs from stock: no overlay")
    print(f"[+] overlay {summary['overlay_sectors']} sectors in {summary['runs']} runs at {summary['table']:#x}; "
          f"write pool {summary['pool'][2]} sectors; SDRAM used up to {summary['end']:#x}; writes: {summary['writes']}")
    print(f"[+] eMMC check: {sum(c for _, c, _, _ in checks)} stock sectors in {len(checks)} pieces")


# ------------------------------------------------------------------ device

class Loader:
    def __init__(self, wait=10):
        import usb.core
        end = time.time() + wait
        while True:
            self.dev = usb.core.find(idVendor=VID, idProduct=PID)
            if self.dev is not None or time.time() >= end:
                break
            time.sleep(0.2)
        if self.dev is None:
            fail("no loader on USB (1209:0001): put the unit in update mode (tools/hx_dfu_reboot.py, or the "
                 "update-mode button at power-up), then dfu-util -d 1fc9:000c -a 0 -D tools/ramboot/firmware-ramboot.dfu "
                 "(POD Go: firmware-ramboot-podgo.dfu)")
        try:
            self.dev.set_configuration()
        except Exception:
            pass
        info = bytes(self.dev.ctrl_transfer(0xC0, REQ_INFO, 0, 0, 64, timeout=2000))
        if info[:4] != b"RAMB":
            fail("the image on USB is not the RAM loader (another image of ours?)")
        f = struct.unpack_from("<12I", info, 4)
        self.info = dict(version=f[0], flags=f[1], core_mhz=f[2], emc_mhz=f[3], emmc_status=f[4],
                         emmc_sectors=f[5], sdram_bad_at=f[6], layout=f[7:11], chunk=f[11])
        if f[0] != RB_VERSION or tuple(f[7:11]) != (RB_HOOK_BASE, RB_STAGE_BASE, RB_DESC, RB_FREE_END) or f[11] != CHUNK:
            fail("the loader and this tool were built from different ramboot.h: load tools/ramboot/firmware-ramboot.dfu again")

    def out(self, req, arg=0, data=None, timeout=5000):
        self.dev.ctrl_transfer(0x40, req, arg & 0xFFFF, arg >> 16, data, timeout=timeout)

    def into(self, req, arg, n, timeout=5000):
        return bytes(self.dev.ctrl_transfer(0xC0, req, arg & 0xFFFF, arg >> 16, n, timeout=timeout))

    def write(self, addr, data, label):
        self.out(REQ_ADDR, addr)
        t0 = time.time()
        for k in range(0, len(data), CHUNK):
            self.out(REQ_DATA, 0, data[k:k + CHUNK])
            if k % (64 * CHUNK) == 0 or k + CHUNK >= len(data):
                done = min(k + CHUNK, len(data))
                print(f"\r    {label}: {done / 1024:.0f}/{len(data) / 1024:.0f} KiB ({time.time() - t0:.0f} s)",
                      end="", flush=True)
        print()
        self.out(REQ_ADDR, addr)
        self.out(REQ_LEN, len(data))
        got = struct.unpack("<I", self.into(REQ_CRC, 0, 4, timeout=30000))[0]
        if got != zlib.crc32(data):
            fail(f"{label}: CRC in SDRAM {got:#010x}, sent {zlib.crc32(data):#010x}")

    def emmc_crc(self, first, count):
        self.out(REQ_LEN, count)
        crc, status = struct.unpack("<2I", self.into(REQ_EMMC_CRC, first, 8, timeout=120000))
        if status:
            fail(f"eMMC read failed at sectors {first:#x}+{count:#x} (status {status:#x})")
        return crc


def cmd_info(args):
    d = Loader()
    i = d.info
    print(f"RAM loader v{i['version']}: SDRAM {'ok' if i['flags'] & 1 else 'FAILED at %#x' % i['sdram_bad_at']}, "
          f"core {i['core_mhz']} MHz, EMC {i['emc_mhz']} MHz; eMMC "
          f"{'%d sectors' % i['emmc_sectors'] if i['flags'] & 2 else 'not started (status %#x)' % i['emmc_status']}")


def cmd_plan(args):
    regions, checks, summary = plan(args.firmware, args.stock, args.writes, args.pool)
    describe(summary, checks)
    total = sum(len(b) for _, b, _ in regions)
    print(f"[+] {total / 1024:.0f} KiB to send in {len(regions)} regions")
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        meta = {"regions": [], "checks": checks, "summary": summary}
        for k, (a, b, label) in enumerate(regions):
            name = f"{k:02d}_{a:08x}.bin"
            open(os.path.join(args.out, name), "wb").write(b)
            meta["regions"].append({"addr": a, "file": name, "label": label})
        json.dump(meta, open(os.path.join(args.out, "plan.json"), "w"), indent=1)
        print(f"[+] written to {args.out}")


def cmd_run(args):
    regions, checks, summary = plan(args.firmware, args.stock, args.writes, args.pool)
    describe(summary, checks)
    d = Loader()
    i = d.info
    if not i["flags"] & 1:
        fail(f"the loader's SDRAM test failed at {i['sdram_bad_at']:#x}")
    print(f"[+] loader: core {i['core_mhz']} MHz, EMC {i['emc_mhz']} MHz")
    if checks and not args.no_emmc_check:
        if not i["flags"] & 2:
            print(f"[!] the loader could not start the eMMC (status {i['emmc_status']:#x}): not checked")
            checks = []
        t0 = time.time()
        for n, (first, count, crc, entry) in enumerate(checks):
            if d.emmc_crc(first, count) != crc:
                fail(f"entry {entry} on the eMMC (sectors {first:#x}+{count:#x}) is not the stock firmware "
                     f"given with --stock: the overlay would be wrong")
            print(f"\r    eMMC: {n + 1}/{len(checks)} pieces match stock ({time.time() - t0:.0f} s)", end="", flush=True)
        print()
    for a, b, label in regions:
        d.write(a, b, label)
    print("[+] all regions checked in SDRAM; starting the application")
    d.out(REQ_GO, GO_KEY)
    import usb.core
    end = time.time() + 5
    while time.time() < end and usb.core.find(idVendor=VID, idProduct=PID) is not None:
        time.sleep(0.2)
    if usb.core.find(idVendor=VID, idProduct=PID) is not None:
        fail("the loader is still on USB: it refused the boot descriptor")
    print("[+] started: the loader has left USB. A power-cycle returns to the stock firmware.")


def cmd_layout(args):
    """Find where each stock entry's payload starts on the card (read only), for a unit whose
    partition table no file gives (the POD Go). Each hit is checked over the entry's first
    2,048 sectors (or all of it), so entries that begin alike are not confused. Saved after
    every entry, so an interrupted run carries on."""
    unit = unit_of(args.stock)
    if unit not in LAYOUT_FILE:
        fail(f"{unit}: its layout is built in; nothing to find")
    stock = load(args.stock, stock=True, any_count=True)
    n = len(stock)
    path = LAYOUT_FILE[unit]
    lay = json.load(open(path)) if os.path.exists(path) else {}
    if lay.get("unit") != unit or len(lay.get("payload", [])) != n:
        lay = {"unit": unit, "stock": os.path.basename(args.stock), "payload": [None] * n}
    d = Loader()
    if not d.info["flags"] & 2:
        fail(f"the loader could not start the eMMC (status {d.info['emmc_status']:#x}): cannot look")
    card = d.info["emmc_sectors"]
    print(f"[+] eMMC: {card} sectors ({card * SECTOR / 2**30:.2f} GiB)")
    nsec = [(len(e) + SECTOR - 1) // SECTOR for e in stock]
    head = [zlib.crc32(e[:SECTOR].ljust(SECTOR, b"\0")) for e in stock]
    tests = [0]

    def is_entry(s, i):
        if s < 0 or s + nsec[i] > card:
            return False
        tests[0] += 1
        if d.emmc_crc(s, 1) != head[i]:
            return False
        c = min(len(stock[i]) // SECTOR, 2048)      # whole sectors only: a last partial one is
        return c <= 1 or d.emmc_crc(s, c) == zlib.crc32(stock[i][:c * SECTOR])   # padded with old data

    lo = 1
    for i in range(n):
        known = lay["payload"][i]
        if known is not None and known >= lo and is_entry(known, i):
            print(f"    entry {i:2d}: payload at sector {known:#x} (saved, checked)")
            lo = known + nsec[i]
            continue
        if len(stock[i]) < SECTOR:                  # no whole sector to recognise it by
            print(f"    entry {i:2d}: {len(stock[i])} bytes, smaller than a sector: skipped (never changed)")
            continue
        found = None
        cands = []
        if i < len(PART_START):
            cands.append(PART_START[i] + 1)                  # where the Stomp has it
        for step in (0x8000, 0x1000, 0x800, 0x400, 0x200, 0x100):
            base = (lo + step - 1) // step * step
            for k in range(64):
                for extra in range(0, i + 3):
                    cands.append(base + k * step + extra)
        seen = set()
        cands = sorted(c for c in cands if c >= lo and not (c in seen or seen.add(c)))
        t0 = time.time()
        for c in cands[:args.candidates]:
            if is_entry(c, i):
                found = c
                break
        if found is None:
            print(f"    entry {i:2d}: not at a round address; scanning {args.scan:#x} sectors from {lo:#x}")
            for s in range(lo, min(lo + args.scan, card)):
                if (s - lo) % 4096 == 0:
                    print(f"\r      at {s:#x} ({time.time() - t0:.0f} s)", end="", flush=True)
                if is_entry(s, i):
                    found = s
                    break
            print()
        if found is None:
            json.dump(lay, open(path, "w"), indent=1)
            fail(f"entry {i}: not found from sector {lo:#x} (raise --scan); entries before it are saved in {path}")
        lay["payload"][i] = found
        json.dump(lay, open(path, "w"), indent=1)
        print(f"    entry {i:2d}: payload at sector {found:#x} ({nsec[i]:#x} sectors; {time.time() - t0:.1f} s)")
        lo = found + nsec[i]
    print(f"[+] all {n} entries found ({tests[0]} reads); saved to {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("firmware", help="the .hxf (or L6IA) to run")
        p.add_argument("--stock", required=True, help="the stock 3.80 .hxf the unit holds (HX Stomp or HX Stomp XL)")
        p.add_argument("--writes", choices=("ram", "pass"), default="ram",
                       help="where the application's eMMC writes go (default: SDRAM only)")
        p.add_argument("--pool", type=int, default=4096, help="sectors of SDRAM for written sectors (default 4096)")
        if name == "plan":
            p.add_argument("--out", help="write the regions and plan.json here")
        else:
            p.add_argument("--no-emmc-check", action="store_true",
                           help="do not check that the eMMC holds the stock firmware first")
    sub.add_parser("info")
    p = sub.add_parser("layout", help="find the stock entries on the card (POD Go), read only")
    p.add_argument("--stock", required=True, help="the stock .hxf the unit holds")
    p.add_argument("--candidates", type=int, default=20000, help="round sector numbers to try first")
    p.add_argument("--scan", type=lambda v: int(v, 0), default=0x40000, help="sectors to scan one by one after that")
    args = ap.parse_args()
    {"plan": cmd_plan, "run": cmd_run, "info": cmd_info, "layout": cmd_layout}[args.cmd](args)


if __name__ == "__main__":
    main()
