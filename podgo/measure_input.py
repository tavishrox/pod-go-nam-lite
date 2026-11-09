#!/usr/bin/env python3
"""Measure the POD Go input's full-scale level (dBu) with a sine tone and a voltmeter.

    python3 podgo/measure_input.py --out-ch N [--level -20] [--secs 20] [--freq 200] [--volts V]

Plays a sine on output channel N of the AXE I/O (its Amp Out feeds the POD Go guitar input) and at the
same time records the POD Go's dry USB channels (3/4). While it plays, read the AC volts across the
POD Go input with the meter. Then rerun with --volts V (or give it now) to get:

    full scale dBu = 20 log10(Vrms / 0.775) - 20 log10(digital peak of the sine)

i.e. the dBu (RMS) of a sine whose peak just reaches digital full scale: the NAM input-level convention.
"""
import argparse
import math

import numpy as np
import sounddevice as sd

SR = 48000


def dev(prefix, key, n):
    return next(i for i, d in enumerate(sd.query_devices()) if d['name'].startswith(prefix) and d[key] >= n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-ch', type=int, required=True, help='AXE I/O output channel (1-based)')
    ap.add_argument('--level', type=float, default=-20, help='tone level, dBFS peak, at the AXE I/O')
    ap.add_argument('--secs', type=float, default=20)
    ap.add_argument('--freq', type=float, default=200)
    ap.add_argument('--volts', type=float, help='the meter reading (V AC RMS)')
    a = ap.parse_args()

    out = dev('AXE IO', 'max_output_channels', a.out_ch)
    nout = sd.query_devices(out)['max_output_channels']
    pod = dev('POD Go', 'max_input_channels', 4)

    t = np.arange(int(a.secs * SR)) / SR
    tone = (10 ** (a.level / 20) * np.sin(2 * np.pi * a.freq * t)).astype('float32')
    ramp = min(len(t) // 4, SR // 10)
    tone[:ramp] *= np.linspace(0, 1, ramp, dtype='float32')
    tone[-ramp:] *= np.linspace(1, 0, ramp, dtype='float32')
    play = np.zeros((len(t), nout), 'float32')
    play[:, a.out_ch - 1] = tone

    print(f'Playing {a.freq:g} Hz at {a.level:g} dBFS on AXE I/O out {a.out_ch} for {a.secs:g} s: read the meter now.')
    blocks = []                                 # its own stream: sd.play() would stop an sd.rec()
    with sd.InputStream(samplerate=SR, channels=4, dtype='float32', device=pod,
                        callback=lambda d, *_: blocks.append(d.copy())):
        sd.play(play, SR, device=out)
        sd.wait()
    rec = np.concatenate(blocks)[:len(t)]

    n = len(rec)
    mid = rec[n // 4: 3 * n // 4]                   # the steady middle half
    for ch in (2, 3):
        x = mid[:, ch]
        rms, peak = float(np.sqrt(np.mean(x ** 2))), float(np.abs(rec[:, ch]).max())
        line = f'POD Go ch{ch + 1} (dry): RMS {20 * math.log10(max(rms, 1e-9)):.2f} dBFS, peak {peak:.3f}'
        if peak > 0.98:
            line += '  CLIPPING: lower the level'
        if a.volts and rms > 0:
            dbu = 20 * math.log10(a.volts / 0.775)
            fs = dbu - 20 * math.log10(math.sqrt(2) * rms)
            line += f'\n  meter {a.volts:.4f} V = {dbu:.2f} dBu  ->  full scale {fs:.2f} dBu'
        print(line)


if __name__ == '__main__':
    main()
