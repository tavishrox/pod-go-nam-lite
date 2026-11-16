#!/usr/bin/env python3
"""Add Morph Pad tone sets to web/pod-go/focus-defaults.json for POD Go models that had none.

Two sources:
  1. Line 6 Focus View files whose names differ from the POD Go symbol (no HD2_ prefix, VIC_/Victoria_/L6SPB_
     prefixes, or a V2 file). The first build only looked for HD2_<name>, so these were missed.
  2. Our own gentle five-tone sets for the EQs and the two Victoria delays, which have no Focus file.
     Values stay well inside POD Go Edit's ranges (gains within +-3 dB or so).

Usage: python3 podgo/focus_extras.py <Res/focus-view-xy-defaults> <PodGo.sym> [focus-defaults.json]
PodGo.sym is Line 6's file from the user's own POD Go Edit install; it is read, never copied.
"""
import glob, json, os, re, sys

KEYS = ['origin', 'x_min_y_max', 'x_max_y_max', 'x_min_y_min', 'x_max_y_min']   # centre, TL, TR, BL, BR
SKIP = ('Cab', 'FXLoop', 'Send', 'Return', 'Looper', 'ImpulseResponse', 'AppDSP', 'Input', 'Output')


def tones(names, base, corners):
    """base: centre values; corners: [(region name, {param: value})] for TL, TR, BL, BR."""
    regions = {'origin': dict(name=base[0], **base[1])}
    for key, (nm, ch) in zip(KEYS[1:], corners):
        r = dict(base[1]); r.update(ch); regions[key] = dict(name=nm, **r)
    for r in regions.values():
        assert set(r) - {'name'} == set(names), (names, r)
    return regions


# ---- our own sets ----
def simple_eq():
    n = ['LowGain', 'MidFreq', 'MidGain', 'HighGain', 'Level']
    flat = {'LowGain': 0.0, 'MidFreq': 600.0, 'MidGain': 0.0, 'HighGain': 0.0, 'Level': 0.0}
    return n, tones(n, ('Flat', flat), [
        ('Bright', {'LowGain': -1.0, 'HighGain': 3.0, 'Level': -0.5}),
        ('Mid Push', {'MidFreq': 800.0, 'MidGain': 3.0, 'LowGain': -1.0, 'Level': -1.0}),
        ('Warm', {'LowGain': 2.0, 'HighGain': -2.0}),
        ('Scooped', {'LowGain': 2.0, 'MidFreq': 500.0, 'MidGain': -3.0, 'HighGain': 2.0}),
    ])


def graphic10():
    bands = ['31p25Hz', '62p5Hz', '125Hz', '250Hz', '500Hz', '1kHz', '2kHz', '4kHz', '8kHz', '16kHz']
    n = bands + ['Level']
    flat = {b: 0.0 for b in n}
    return n, tones(n, ('Flat', flat), [
        ('Bright', {'125Hz': -1.0, '4kHz': 2.0, '8kHz': 3.0, '16kHz': 2.0, 'Level': -0.5}),
        ('Mid Push', {'500Hz': 1.0, '1kHz': 3.0, '2kHz': 2.0, 'Level': -1.0}),
        ('Warm', {'62p5Hz': 1.0, '125Hz': 2.0, '250Hz': 1.0, '4kHz': -1.0, '8kHz': -2.0, '16kHz': -3.0}),
        ('Scooped', {'125Hz': 2.0, '250Hz': 1.0, '500Hz': -2.0, '1kHz': -3.0, '2kHz': -1.0, '4kHz': 1.0, '8kHz': 2.0}),
    ])


def cali_q():
    n = ['80Hz', '240Hz', '750Hz', '2200Hz', '6600Hz', 'Level']
    flat = {b: 0.0 for b in n}
    return n, tones(n, ('Flat', flat), [
        ('Bright', {'2200Hz': 2.0, '6600Hz': 3.0, 'Level': -0.5}),
        ('Mid Push', {'750Hz': 3.0, '2200Hz': 1.0, 'Level': -1.0}),
        ('Warm', {'80Hz': 2.0, '240Hz': 2.0, '6600Hz': -2.0}),
        ('Scooped', {'80Hz': 2.0, '750Hz': -3.0, '6600Hz': 2.0}),
    ])


def shelves():
    n = ['LowGain', 'LowFreq', 'HighGain', 'HighFreq', 'Level']
    flat = {'LowGain': 0.0, 'LowFreq': 300.0, 'HighGain': 0.0, 'HighFreq': 3000.0, 'Level': 0.0}
    return n, tones(n, ('Flat', flat), [
        ('Bright', {'LowGain': -1.0, 'HighGain': 3.0, 'Level': -0.5}),
        ('Mid Forward', {'LowGain': -2.0, 'LowFreq': 200.0, 'HighGain': -2.0, 'HighFreq': 5000.0, 'Level': 1.5}),
        ('Warm', {'LowGain': 2.0, 'LowFreq': 250.0, 'HighGain': -3.0, 'HighFreq': 3500.0}),
        ('Scooped', {'LowGain': 3.0, 'LowFreq': 200.0, 'HighGain': 3.0, 'HighFreq': 4000.0, 'Level': -1.5}),
    ])


def tilt():
    n = ['Tilt', 'CenterFreq', 'Level']
    flat = {'Tilt': 0.5, 'CenterFreq': 1000.0, 'Level': 0.0}
    return n, tones(n, ('Flat', flat), [
        ('Tilt Up, Low Pivot', {'Tilt': 0.62, 'CenterFreq': 600.0}),
        ('Tilt Up, High Pivot', {'Tilt': 0.62, 'CenterFreq': 2000.0}),
        ('Tilt Down, Low Pivot', {'Tilt': 0.38, 'CenterFreq': 600.0}),
        ('Tilt Down, High Pivot', {'Tilt': 0.38, 'CenterFreq': 2000.0}),
    ])


def cuts():
    n = ['LowCut', 'HighCut', 'Level']
    open_ = {'LowCut': 19.9, 'HighCut': 20100.0, 'Level': 0.0}
    return n, tones(n, ('Open', open_), [
        ('Tight Lows', {'LowCut': 120.0}),
        ('Mid Focus', {'LowCut': 150.0, 'HighCut': 7000.0}),
        ('Soft Top', {'LowCut': 40.0, 'HighCut': 7500.0}),
        ('Narrow', {'LowCut': 250.0, 'HighCut': 5000.0, 'Level': 1.0}),
    ])


def parametric(q):
    n = ['LowFreq', 'LowQ', 'LowGain', 'MidFreq', 'MidQ', 'MidGain', 'HighFreq', 'HighQ', 'HighGain', 'LowCut', 'HighCut', 'Level']
    flat = {'LowFreq': 110.0, 'LowQ': q, 'LowGain': 0.0, 'MidFreq': 2000.0, 'MidQ': q, 'MidGain': 0.0,
            'HighFreq': 8000.0, 'HighQ': q, 'HighGain': 0.0, 'LowCut': 19.9, 'HighCut': 20100.0, 'Level': 0.0}
    return n, tones(n, ('Flat', flat), [
        ('Air', {'HighGain': 3.0, 'LowCut': 60.0, 'Level': -0.5}),
        ('Mid Push', {'MidFreq': 1200.0, 'MidQ': 1.0, 'MidGain': 3.0, 'LowCut': 80.0, 'Level': -1.0}),
        ('Warm', {'LowFreq': 120.0, 'LowGain': 2.0, 'HighFreq': 6000.0, 'HighGain': -2.0, 'HighCut': 12000.0}),
        ('Scooped', {'LowFreq': 100.0, 'LowGain': 2.0, 'MidFreq': 700.0, 'MidQ': 0.8, 'MidGain': -3.0,
                     'HighFreq': 6000.0, 'HighGain': 2.0}),
    ])


def euclidean():
    n = ['Step Time', 'Feedback', 'Steps', 'Fill', 'Rotate', 'Mix', 'LowCut', 'HighCut', 'Level', 'SyncSelect1', 'TempoSync1']
    base = {'Step Time': 0.136, 'Feedback': 0.0, 'Steps': 8, 'Fill': 3, 'Rotate': 0, 'Mix': 0.3,
            'LowCut': 80.0, 'HighCut': 20000.0, 'Level': 0.0, 'SyncSelect1': 6, 'TempoSync1': False}
    return n, tones(n, ('Three in Eight', base), [
        ('Sparse', {'Fill': 2, 'Feedback': 0.1, 'Mix': 0.25}),
        ('Busy', {'Fill': 5, 'HighCut': 8000.0}),
        ('Dark Steps', {'Feedback': 0.2, 'HighCut': 4000.0}),
        ('Twelve Step', {'Step Time': 0.12, 'Steps': 12, 'Fill': 5, 'Rotate': 1, 'HighCut': 10000.0}),
    ])


def shuffling():
    n = ['Time', 'Delay Div', 'Mix', 'Feedback', 'SliceFdbk', 'Shuffle', 'Octaves', 'Reverse', 'Seq Drift', 'Smoothing',
         'TempoSync1', 'SyncSelect1']
    base = {'Time': 1.0, 'Delay Div': 4, 'Mix': 0.3, 'Feedback': 0.3, 'SliceFdbk': 0.1, 'Shuffle': 0.5, 'Octaves': 0.1,
            'Reverse': 0.5, 'Seq Drift': 0.0, 'Smoothing': 0.1, 'TempoSync1': False, 'SyncSelect1': 6}
    return n, tones(n, ('Shuffle', base), [
        ('Light Shuffle', {'Shuffle': 0.25, 'Reverse': 0.2, 'Octaves': 0.0, 'Mix': 0.25}),
        ('Reverse Bits', {'Shuffle': 0.4, 'Reverse': 0.75}),
        ('Smooth', {'Shuffle': 0.3, 'Smoothing': 0.3, 'Feedback': 0.25, 'Mix': 0.25}),
        ('Octave Sparkle', {'Octaves': 0.35}),
    ])


QUANTIZE = {'Delay Div', 'Steps', 'Fill', 'Rotate', 'SyncSelect1', 'TempoSync1'}
OURS = [   # (symbol pattern, model name, category, maker)
    (r'^HD2_EQ(_STATIC_)?Simple3Band', 'Simple EQ', 'eq', simple_eq),
    (r'^HD2_EQ(_STATIC_)?Graphic10Band', '10 Band Graphic', 'eq', graphic10),
    (r'^HD2_(EQ_STATIC_)?CaliQ', 'Cali Q Graphic', 'eq', cali_q),
    (r'^HD2_EQ(_STATIC_)?LowShelfHighShelf', 'Low/High Shelf', 'eq', shelves),
    (r'^HD2_EQ(_STATIC_)?SimpleTilt', 'Simple Tilt', 'eq', tilt),
    (r'^HD2_EQ(_STATIC_)?LowCutHighCut', 'Low and High Cut', 'eq', cuts),
    (r'^HD2_EQ_STATIC_Parametric', 'Parametric', 'eq', lambda: parametric(0.707)),
    (r'^HD2_EQParametric', 'Parametric', 'eq', lambda: parametric(0.7)),
    (r'^Victoria_EuclideanDelay', 'Euclidean Delay', 'delay', euclidean),
    (r'^Victoria_ShufflingDelay', 'Shuffling Glitch Delay', 'delay', shuffling),   # POD Go Edit: 'Glitch Delay', like VIC_DelayGlitch
]


def main(res, sym_path, out='web/pod-go/focus-defaults.json'):
    sym = json.load(open(sym_path))
    doc = json.load(open(out))
    sets = doc['sets']
    files = {os.path.basename(f)[:-5]: f for f in glob.glob(os.path.join(res, '*', '*.json'))}
    added_l6, added_ours, none = [], [], []
    for model, m in enumerate(sym):
        s, order = m['symbol'], m['parameters']
        if s in sets or any(k in s for k in SKIP):
            continue
        base = re.sub(r'^(HD2_|VIC_|Victoria_|L6SPB_)', '', s)
        hit = next((c for c in (base, base + 'V2') if c in files), None)
        if hit:
            f = json.load(open(files[hit]))
            keep = [p for p in order if p in f['params']]
            sets[s] = {'model': model, 'category': os.path.basename(os.path.dirname(files[hit])),
                       'modelName': f['modelName'] + (' (v1)' if hit == base + 'V2' and 'Preamp' in s else ''), 'order': order,
                       'params': {p: f['params'][p]['behavior'] for p in keep},
                       'regions': {k: {'name': f['regions'][k]['name'], **{p: f['regions'][k][p] for p in keep if p in f['regions'][k]}}
                                   for k in KEYS}}
            added_l6.append(f'{s} <- {hit}')
            continue
        mine = next((o for o in OURS if re.search(o[0], s)), None)
        if mine:
            names, regions = mine[3]()
            assert set(names) <= set(order), (s, set(names) - set(order))
            name = ('Fixed ' if '_STATIC_' in s else '') + mine[1]   # the fixed EQ slot's own models
            sets[s] = {'model': model, 'category': mine[2], 'modelName': name, 'order': order, 'source': 'toneshift',
                       'params': {p: 'quantize' if p in QUANTIZE else 'interpolate' for p in names}, 'regions': regions}
            added_ours.append(s)
            continue
        none.append(s)
    if 'HD2_DL4SweepEchoStereo' in sets:   # two Line 6 'Sweep Echo's in the picker; this one is the DL4's
        sets['HD2_DL4SweepEchoStereo']['modelName'] = 'DL4 Sweep Echo'
    doc['about'] = ("Five tones per model for the POD Go's models: Line 6 Focus View defaults, plus our own gentle sets "
                    "(marked source: toneshift) for the EQs and two delays that have none. "
                    "'order' is the POD Go's parameter order, 'model' its model number.")
    with open(out, 'w') as fh:
        json.dump(doc, fh, separators=(',', ':'))
    print(f'Line 6 sets added: {len(added_l6)}'); [print('  ', a) for a in added_l6]
    print(f'Our sets added: {len(added_ours)}'); [print('  ', a) for a in added_ours]
    print(f'Still none (non-morphable kinds skipped): {none}')
    print(f'Total sets: {len(sets)}')


if __name__ == '__main__':
    main(*sys.argv[1:])
