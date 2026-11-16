#!/usr/bin/env python3
"""Set one knob of the POD Go's edit buffer live over USB: the command the Morph Pad needs
(docs/research/COMPANION_APP.md, "Set one parameter").

    python3 podgo/param_probe.py info [N]                      what is at grid positions 0..N-1 (read only, 0x2d)
    python3 podgo/param_probe.py listen [SECONDS]              print the notify stream (turn a knob on the unit)
    python3 podgo/param_probe.py set POS INDEX VALUE           one knob: grid position, parameter index, 0..1
    python3 podgo/param_probe.py sweep POS INDEX FROM TO SECS  glide one knob, 30 messages a second

Another Line 6 unit: set HX_PID, e.g. HX_PID=0x4248 for a Helix Floor (0x4246 HX Stomp, 0x4253 XL).

Edit buffer only: nothing is saved (the preset shows as edited; reload it to undo). POD Go Edit closed.

The message, as POD Go Edit 2.x sends it (PodGoEditorService::setObjectParam -> DispatchCommand(service 6,
command 0x1e)): {0x62: grid position, 0x1d: True (a model "DSP" parameter; False = the editor's V params),
0x1a: 0, 0x1c: parameter index, 0x77: value}. The index is the parameter's place in the model's list
(amps: Drive 0, Bass 1, Mid 2, Treble 3, Presence 4, ChVol 5, Master 6, ...); knob values are 0..1 floats.
Grid position: POD Go Edit uses 0 for the input, 11 for the output and 1..10 for the block slots; command
0x2d {0x62: grid position} (PodGoEditorService::getObjectInfo) returns what is there, without changing anything.
"""
import os
import struct
import sys
import time

import msgpack

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import hx_ctl  # noqa: E402

CMD_SET_PARAM, CMD_OBJECT_INFO = 0x1e, 0x2d
K_POS, K_DSP, K_1A, K_INDEX, K_VALUE = 0x62, 0x1d, 0x1a, 0x1c, 0x77


def set_param(c, pos, index, value, dsp=True):
    """One knob; returns the unit's result. Float sent as float32, as an L6Variant float."""
    ch = c.ed
    ch.seq = (ch.seq + 1) & 0xFFFF
    params = {K_POS: pos, K_DSP: dsp, K_1A: 0, K_INDEX: index, K_VALUE: float(value)}
    req = msgpack.packb({hx_ctl.K_SEQ: ch.seq, hx_ctl.K_CMD: CMD_SET_PARAM, hx_ctl.K_PARAMS: params},
                        use_bin_type=False, use_single_float=True)
    with hx_ctl._Quiet(ch.verbose):
        ch._write(struct.pack('<HHI', 1, ch.svc, len(req)) + req)
        a, s, body = ch._read_msg(ch.timeout)
    rep = msgpack.unpackb(body, raw=True, strict_map_key=False)
    return rep


def show_notes(c, seconds):
    for m in c.nf.drain(seconds):
        print('  notify:', str(m)[:300])


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    with hx_ctl.HxCtl(False, 8.0, int(os.environ.get('HX_PID', '0x424b'), 0)) as c:
        cur = c.current()
        print(f"preset {cur['preset']} {cur['name']!r}")
        if a[0] == 'info':
            for pos in range(int(a[1]) if len(a) > 1 else 12):
                try:
                    print(f'  {pos:2d}:', str(c.ed.request(CMD_OBJECT_INFO, {K_POS: pos}))[:400])
                except hx_ctl.HxError as e:
                    print(f'  {pos:2d}: {e}')
        elif a[0] == 'listen':
            secs = float(a[1]) if len(a) > 1 else 15
            print(f'listening {secs:g} s: turn one knob on the unit now')
            show_notes(c, secs)
        elif a[0] == 'set':
            pos, index, value = int(a[1]), int(a[2]), float(a[3])
            print('reply:', set_param(c, pos, index, value))
            show_notes(c, 1.0)
        elif a[0] == 'sweep':
            pos, index, v0, v1, secs = int(a[1]), int(a[2]), float(a[3]), float(a[4]), float(a[5])
            n = max(1, int(secs * 30))
            t0 = time.monotonic()
            bad = 0
            for i in range(n + 1):
                rep = set_param(c, pos, index, v0 + (v1 - v0) * i / n)
                bad += rep.get(hx_ctl.K_STATUS) != 0
                time.sleep(max(0, t0 + (i + 1) / 30 - time.monotonic()))
            print(f'{n + 1} messages in {time.monotonic() - t0:.2f} s, {bad} not status 0; last reply {rep}')
            show_notes(c, 1.0)
        else:
            sys.exit(__doc__)


if __name__ == '__main__':
    main()
