#!/usr/bin/env python3
"""Select a snapshot on the POD Go over USB MIDI: CC69 on channel 1 (the POD Go's default).

    python3 podgo/snap6/cc69.py 5        # snapshot 5 (CC69 value 4); 1..6 on the Snap6 test build, 1..4 on stock

Needs mido with a backend (python-rtmidi). Value = snapshot - 1, as the stock CC69 (0..3) goes.
"""
import sys
import time

import mido

n = int(sys.argv[1])
assert 1 <= n <= 6, 'snapshot 1..6'
ch = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0
port = next(p for p in mido.get_output_names() if 'POD Go' in p)
with mido.open_output(port) as out:
    out.send(mido.Message('control_change', channel=ch, control=69, value=n - 1))
    time.sleep(0.05)
print(f'{port}: CC69 = {n - 1} (snapshot {n}) on channel {ch + 1}')
