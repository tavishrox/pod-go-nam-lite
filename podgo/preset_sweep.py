#!/usr/bin/env python3
"""Preset sweep on the POD Go (the HX Stomp's Test A, docs/research/STOMP_TEST_A_PRESET_SWEEP.md):
does any preset leave something running that disturbs NAM's memory?

    python3 podgo/preset_sweep.py OUT.jsonl [--first N] [--count N] [--rev] [--baseline-only]

Per preset i of setlist 1 (the user presets): select i and let it run 2 s; write the test preset
into the edit buffer (NAM A2 Lite alone, every other block off, Model = IR slot 4, knobs as below);
1.5 s; record 3 s of USB 1 (processed). With the guitar silent (volume down or unplugged), NAM
plays its bias plus amplified input noise: a steady level. Corrupted weights, rings, tables or
code move that level, add noise or silence it. Each preset is compared with baselines recorded
before the sweep.

Nothing is saved to the unit: presets are selected and the edit buffer written, as POD Go Edit
does before you press Save. The edit buffer at the start is kept in OUT.start.bin (restore it
with: python3 tools/hx_ctl.py --pid 0x424b load-preset OUT.start.bin).
Quit POD Go Edit first. Keep the Mac unlocked (macOS records no audio frames while locked).
"""
import json
import math
import os
import sys
import time

import numpy as np
import sounddevice as sd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import hx_ctl  # noqa: E402

PID = 0x424b
SETLIST, N_PRESETS = 1, 128
NAM_PID, AMP_KIND = 27, 17            # Line 6 Elektrik's preset id (Table 1), the amp block kind
# Elektrik's 11 knobs as NAM: Input, Bass, Mid, Treble, High Cut, Output, Model (0.03 = IR slot 4),
# Mid Freq, Q, (unused), Polarity
NAM_VALUES = [0.5, 0.5, 0.5, 0.5, 1.0, 0.5, 0.03, 0.48, 0.0, 0.5, 0.0]


def template(sec):
    """The edit buffer with NAM in the amp block and every other processing block off."""
    bl = hx_ctl.blocks(sec)
    amp = [i for i, b in enumerate(bl) if b.get(19) == 6 and b[20].get(9) == AMP_KIND]
    assert len(amp) == 1, f'amp blocks at {amp}'
    for i, b in enumerate(bl):
        if b.get(19) == 6:
            b[20][10] = False
    b = bl[amp[0]][20]
    b[24][25], b[24][26], b[10] = NAM_PID, -1, True
    b[11] = {2: len(NAM_VALUES), 3: len(NAM_VALUES), 4: list(NAM_VALUES)}
    return amp[0]


def device():
    return next(i for i, d in enumerate(sd.query_devices())
                if d['name'].startswith('POD Go') and d['max_input_channels'] >= 4)


def measure(dev, secs=3.0):
    x = sd.rec(int(secs * 48000), samplerate=48000, channels=4, dtype='float32', device=dev)
    sd.wait()
    y = x[4800:, 0].astype(np.float64)
    if not len(y) or not np.any(y):
        return dict(frames=int(len(y)), mean=0.0, sd=0.0, peak=0.0, silent=True)
    m = float(y.mean())
    return dict(frames=int(len(y)), mean=m, sd=float(y.std()), peak=float(np.abs(y - m).max()), silent=False)


def session():
    return hx_ctl.HxCtl(False, 8.0, PID)


def put_and_check(magic, sec, like, select=None):
    """(select preset `select` and wait 2 s, then) write the test preset; verify it on a fresh
    connection (a write after a full preset read on one connection stalls on the POD Go)."""
    with session() as hx:
        if select is not None:
            hx.select(select, SETLIST, settle=0.5)
            time.sleep(2.0)
        hx.set_preset_blob(hx_ctl.encode_preset(magic, sec, like=like), settle=1.5)
    with session() as hx:
        _, got = hx.get_preset()
    return any(e.get(19) == 6 and e[20][24][25] == NAM_PID and e[20][10] for e in hx_ctl.blocks(got))


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        sys.exit(__doc__)
    out = a[0]
    opt = lambda k, d: int(a[a.index(k) + 1]) if k in a else d
    first, count = opt('--first', 0), opt('--count', N_PRESETS)
    idx = list(range(first, min(N_PRESETS, first + count)))
    if '--rev' in a:
        idx.reverse()
    dev = device()
    with session() as hx:
        names = [n for _, n in hx_ctl.preset_names(hx.preset_list(SETLIST))]
    with session() as hx:
        start = hx.get_preset_blob()
    print(f'{len(names)} presets in setlist {SETLIST}', flush=True)
    open(out.rsplit('.', 1)[0] + '.start.bin', 'wb').write(start)
    magic, sec = hx_ctl.decode_preset(start)
    amp = template(sec)
    log = open(out, 'a')
    base = []
    for k in range(3):
        if not put_and_check(magic, sec, start):
            sys.exit('the test preset did not load with NAM in the amp block')
        time.sleep(1.0)
        base.append(measure(dev))
    log.write(json.dumps(dict(kind='baseline', amp_block=amp, runs=base)) + '\n')
    bm = [r['mean'] for r in base]
    bsd = max(r['sd'] for r in base)
    bpk = max(r['peak'] for r in base)
    tol_mean = max(5 * (max(bm) - min(bm)), 3 * bsd / math.sqrt(48000 * 2.9), 1e-5)
    print(f'baseline: mean {np.mean(bm):.3e} (+-{tol_mean:.1e}), sd {bsd:.3e}, peak {bpk:.3e}', flush=True)
    if any(r['silent'] for r in base):
        sys.exit('no audio from the POD Go (screen locked, or the block is silent)')
    flagged = 0
    for i in idx:
        name = names[i] if i < len(names) else ''
        try:
            ok = put_and_check(magic, sec, start, select=i)
            time.sleep(1.0)
            r = measure(dev)
        except Exception as e:                      # the unit stopped answering: stop here
            log.write(json.dumps(dict(kind='preset', i=i, name=name, error=str(e))) + '\n')
            print(f'{i:3d} {name:20s} ERROR {e}', flush=True)
            break
        why = []
        if not ok:
            why.append('NAM not loaded')
        if r['silent']:
            why.append('silent')
        if abs(r['mean'] - np.mean(bm)) > tol_mean:
            why.append('level moved')
        if r['sd'] > 2 * bsd + 1e-7:
            why.append('noise up')
        if r['peak'] > 4 * bpk + 1e-6:
            why.append('peaks')
        flagged += bool(why)
        log.write(json.dumps(dict(kind='preset', i=i, name=name, loaded=ok, flags=why, **r)) + '\n')
        log.flush()
        print(f'{i:3d} {name:20s} mean {r["mean"]:+.3e} sd {r["sd"]:.2e} peak {r["peak"]:.2e} '
              f'{"FLAG " + ", ".join(why) if why else "ok"}', flush=True)
    print(f'\n{len(idx)} presets, {flagged} flagged; the edit buffer holds the test preset '
          f'(restore: tools/hx_ctl.py --pid 0x424b load-preset {out.rsplit(".", 1)[0]}.start.bin)')


if __name__ == '__main__':
    main()
