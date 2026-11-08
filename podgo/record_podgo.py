#!/usr/bin/env python3
"""Record the POD Go's four USB channels (1/2 processed output, 3/4 dry input) to a WAV, read only.

    python3 podgo/record_podgo.py OUT.wav [seconds]

Then `podgo/analyze_nam.py OUT.wav CAPTURE.nam` compares the processed output with the reference
NAM A2 run on the dry channel.
"""
import sys

import sounddevice as sd
import soundfile as sf


def main():
    out = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 8
    dev = next(i for i, d in enumerate(sd.query_devices()) if d['name'].startswith('POD Go') and d['max_input_channels'] >= 4)
    rec = sd.rec(int(secs * 48000), samplerate=48000, channels=4, dtype='float32', device=dev)
    sd.wait()
    sf.write(out, rec, 48000, subtype='FLOAT')
    peaks = abs(rec).max(axis=0)
    print(f'{out}: {secs} s, 4 channels; peaks ' + ', '.join(f'ch{k + 1} {p:.3f}' for k, p in enumerate(peaks)))


if __name__ == '__main__':
    main()
