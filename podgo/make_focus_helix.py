#!/usr/bin/env python3
"""Build web/pod-go/focus-helix.json: what MORF-X needs to work with a Helix (and the HX family).

  models: {Helix model number: [symbol, parameter order]} for every model in HX Edit's Helix.sym, so
          MORF-X names any block on the unit and maps parameters by name.
  sets:   five-tone sets for Helix models the POD Go file (focus-defaults.json) doesn't already have,
          from Line 6's Focus View files (matched by name, as focus_extras.py does) or our own gentle
          sets (the EQs and two Victoria delays, from focus_extras.py). Same shape as focus-defaults.json.

Usage: python3 podgo/make_focus_helix.py <Res/focus-view-xy-defaults> <Helix.sym>
Helix.sym is Line 6's file from the user's own HX Edit install (Contents/Resources/Helix.sym).
"""
import glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from focus_extras import KEYS, SKIP, OURS, QUANTIZE  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'web', 'pod-go')


def category_of(path):
    return os.path.basename(os.path.dirname(path))


def main(res, sym_path):
    sym = json.load(open(sym_path))
    podgo = json.load(open(os.path.join(HERE, 'focus-defaults.json')))['sets']
    files = {os.path.basename(f)[:-5]: f for f in glob.glob(os.path.join(res, '*', '*.json'))}
    models, sets, l6, ours = {}, {}, 0, 0
    for n, m in enumerate(sym):
        s, order = m['symbol'], m['parameters']
        models[n] = [s, order]
        if s in podgo or any(k in s for k in SKIP):
            continue
        base = re.sub(r'^(HD2_|VIC_|Victoria_|L6SPB_)', '', s)
        hit = next((c for c in (base, base + 'V2') if c in files), None)
        if hit:
            f = json.load(open(files[hit]))
            keep = [p for p in order if p in f['params']]
            if not keep:
                continue
            sets[s] = {'category': category_of(files[hit]), 'modelName': f['modelName'],
                       'params': {p: f['params'][p]['behavior'] for p in keep},
                       'regions': {k: {'name': f['regions'][k]['name'], **{p: f['regions'][k][p] for p in keep if p in f['regions'][k]}}
                                   for k in KEYS}}
            l6 += 1
            continue
        mine = next((o for o in OURS if re.search(o[0], s)), None)
        if mine:
            names, regions = mine[3]()
            if set(names) <= set(order):
                sets[s] = {'category': mine[2], 'modelName': mine[1], 'source': 'toneshift',
                           'params': {p: 'quantize' if p in QUANTIZE else 'interpolate' for p in names}, 'regions': regions}
                ours += 1
    out = {'about': "MORF-X on a Helix: every Helix model (number -> symbol and parameter order, from HX Edit's "
                    "Helix.sym) and five-tone sets for the models focus-defaults.json doesn't cover "
                    "(Line 6 Focus View defaults, or ours marked source: toneshift).",
           'models': models, 'sets': sets}
    with open(os.path.join(HERE, 'focus-helix.json'), 'w') as fh:
        json.dump(out, fh, separators=(',', ':'))
    covered = sum(1 for s, _ in models.values() if s in podgo or s in sets)
    amps = [s for s, _ in models.values() if re.match(r'HD2_(Amp|Preamp)', s)]
    print(f'{len(models)} Helix models; extra sets: {l6} Line 6 + {ours} ours; with tones: {covered}; '
          f'amps and preamps with tones: {sum(1 for a in amps if a in podgo or a in sets)}/{len(amps)}')


if __name__ == '__main__':
    main(*sys.argv[1:])
