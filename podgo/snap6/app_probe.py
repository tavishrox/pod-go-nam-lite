#!/usr/bin/env python3
"""The companion app's USB access to snapshots 5 and 6, tried from the computer (docs/research/COMPANION_APP.md).

    python3 podgo/snap6/app_probe.py read            the current preset: with and without the app's marker
    python3 podgo/snap6/app_probe.py rename5 NAME    set snapshot 5's name in the edit buffer (no save)

Needs a POD Go running a six-snapshot build with the app hooks, and POD Go Edit closed.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))
import hx_ctl  # noqa: E402

RECSZ, NAME, COLOR = 0x28c, 0x27e, 0x27c
APP = {0x7a: 1}


def section(blob):
    """(offset, holder, mask, [records]) of key 14 in an edit-buffer blob, or None."""
    k = blob.find(b'\x87\x0e\xc5')
    if k < 0:
        return None
    ln = struct.unpack_from('>H', blob, k + 3)[0]
    holder, mask = blob[k + 5], blob[k + 6]
    n = bin(mask).count('1')
    recs = [blob[k + 9 + i * RECSZ: k + 9 + (i + 1) * RECSZ] for i in range(n)]
    assert ln == 4 + n * RECSZ + 2, (ln, n)
    return k, holder, mask, recs


def name(rec):
    return rec[NAME:NAME + 11].split(b'\0')[0].decode('latin1')


def main():
    a = sys.argv[1:]
    with hx_ctl.HxCtl(False, 8.0, 0x424b) as c:
        cur = c.current()
        print(f"preset {cur['preset']} {cur['name']!r}")
        plain = c.get_preset_blob()
        app = c.ed.request(hx_ctl.CMD_GET_EDITBUF, APP, timeout=8)
        print(f'read without the marker: {len(plain)} B, key 14 {"present" if section(plain) else "absent"}')
        s = section(app)
        print(f'read with the marker:    {len(app)} B, key 14 {"present" if s else "absent"}')
        if not s:
            return
        k, holder, mask, recs = s
        slots = [i for i in range(3) if mask >> i & 1]
        for i, r in zip(slots, recs):
            print(f'  stored record for snapshot {i + 4}: name {name(r)!r}, colour {r[COLOR]}')
        print(f'  holder (in slot 4 now): snapshot {holder + 1}')
        if a[:1] == ['rename5']:
            if 1 not in slots:
                sys.exit('snapshot 5 is not in the store (it is in slot 4, or empty): select another snapshot first')
            new = a[1].encode('latin1')[:10].ljust(11, b'\0')
            at = k + 9 + slots.index(1) * RECSZ + NAME
            blob = app[:at] + new + app[at + 11:]
            c.set_preset_blob(blob)
            back = section(c.ed.request(hx_ctl.CMD_GET_EDITBUF, APP, timeout=8))
            got = [name(r) for i, r in zip([i for i in range(3) if back[2] >> i & 1], back[3]) if i == 1] if back else []
            print(f'after writing: snapshot 5 is named {got}')


if __name__ == '__main__':
    main()
