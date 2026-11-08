#!/usr/bin/env python3
"""NAM preset templates for POD Go Edit (.pgp), for the NAM A2 Lite firmware (NAM on Line 6 Elektrik).

    python3 podgo/make_templates.py BASE.pgp OUT_DIR

BASE.pgp: any preset exported by POD Go Edit 2.x (its file layout, device id and app version are kept).
Each template leaves out the blocks NAM does not need (cab: captures include it; FX loop; fixed EQ), so
their DSP is free for effects. Every chain was checked on a unit (2026-11-08): it keeps all its blocks
(the unit drops a chain over 7 effects or about 8,000 cost units). Block settings are POD Go Edit's
defaults (its Resources/*.models), NAM's as podgo_model.ELEKTRIK_LAYOUT with Model 0.03 (IR slot 4; the unit shows 0.3).
"""
import copy
import glob
import json
import os
import sys

RES = "/Applications/Line6/POD Go Edit.app/Contents/Resources"
NAM = "HD2_AmpLine6Elektrik"
# Elektrik knob = NAM control: Drive Input, Presence High Cut, ChVol Output, Master Model (0.03 = slot 4, shown as 0.3),
# Sag Mid Freq, Ripple Q, Bias unused, BiasX Polarity (0.5 = normal)
NAM_VALUES = {"Drive": 0.5, "Bass": 0.5, "Mid": 0.5, "Treble": 0.5, "Presence": 1.0, "ChVol": 0.5,
              "Master": 0.03, "Sag": 0.48, "Ripple": 0.5, "Bias": 0.5, "BiasX": 0.5}
STEREO = {"delay.models", "reverb.models", "modulation.models"}     # @type 5 in POD Go Edit's exports
EXP_FS, EXP1, EXP2 = 9, 1, 2

# name: (description, [(model, footswitch index or None, enabled)], cost units on the unit)
TEMPLATES = {
    "NAM Blank": ("Volume pedal and NAM; 9 empty blocks for anything", [
        ("HD2_VolPanVolStereo", "exp", True), (NAM, None, True)], 3000),
    "NAM Essentials": ("Volume, wah, drive, NAM, delay, reverb; 4 empty blocks", [
        ("HD2_VolPanVolStereo", "exp", True), ("HD2_WahFasselStereo", "toe", False),
        ("HD2_DistMinotaurMono", 1, False), (NAM, None, True),
        ("HD2_DelaySimpleDelayStereo", 2, False), ("HD2_ReverbPlateStereo", 3, True)], 5411),
    "NAM Full Board": ("Volume, comp, drive, NAM, EQ, chorus, delay, reverb: 7 effects", [
        ("HD2_VolPanVolStereo", "exp", True), ("HD2_CompressorDeluxeCompMono", 1, False),
        ("HD2_DistMinotaurMono", 2, False), (NAM, None, True), ("HD2_EQSimple3BandStereo", 3, False),
        ("HD2_ChorusStereo", 4, False), ("HD2_DelayVintageDigitalStereoV2", 5, False),
        ("HD2_ReverbHallStereo", 6, True)], 6725),
}
LED = {1: 527360, 2: 67840, 3: 16723200, 4: 196619, 5: 67840, 6: 16723200}


def editor_models():
    out = {}
    for f in glob.glob(os.path.join(RES, "*.models")):
        for m in json.load(open(f)):
            if m.get("symbolicID"):
                out[m["symbolicID"]] = (os.path.basename(f), m)
    return out


def block(models, sid, pos, enabled):
    f, m = models[sid]
    b = {"@model": sid, "@position": pos, "@enabled": enabled, "@no_snapshot_bypass": False,
         "@type": 1 if sid == NAM else (5 if f in STEREO else 0)}
    for p in m["params"]:
        k = p["symbolicID"]
        if k.startswith("@"):
            if k == "@bypassvolume":
                b[k] = 1
            continue
        b[k] = NAM_VALUES[k] if sid == NAM else p["default"]
    return b, m.get("name", sid)


def make(base, models, name, desc, chain):
    d = copy.deepcopy(base)
    d["data"]["meta"]["name"] = name
    t = d["data"]["tone"]
    t.pop("irUuidTable", None)
    dsp = {k: v for k, v in t["dsp0"].items() if k in ("input", "output")}
    fsw, ctl, snap_ctl, flags = {}, {}, {}, {}
    for pos in range(10):
        key = f"block{pos}"
        if pos < len(chain):
            sid, fs, on = chain[pos]
            dsp[key], label = block(models, sid, pos, on)
            flags[key] = on
            if fs in ("exp", "toe"):
                fsw[key] = {"@fs_label": label, "@fs_enabled": fs == "exp", "@fs_index": EXP_FS,
                            "@fs_ledcolor": 65408 if fs == "exp" else 196619, "@fs_momentary": False}
                if fs == "toe":
                    fsw[key]["@fs_primary"] = True
                ctl[key] = {"Pedal": {"@min": 0, "@max": 1, "@controller": EXP2 if fs == "exp" else EXP1}}
                snap_ctl[key] = {"Pedal": {"@fs_enabled": False, "@value": 1}}
            elif fs:
                fsw[key] = {"@fs_label": label, "@fs_enabled": on, "@fs_index": fs, "@fs_ledcolor": LED[fs],
                            "@fs_primary": True, "@fs_momentary": False}
        else:
            dsp[key] = {"@position": pos}
            flags[key] = True
    t["dsp0"], t["footswitch"], t["controller"] = dsp, {"dsp0": fsw}, {"dsp0": ctl}
    for s in range(4):
        sn = t.get(f"snapshot{s}")
        if sn is None:
            continue
        sn["blocks"] = {"dsp0": dict(flags)}
        sn["controllers"] = {"dsp0": copy.deepcopy(snap_ctl)}
    t["global"]["@current_snapshot"] = 0
    t["global"]["@cursor_group"] = f"block{[c[0] for c in chain].index(NAM)}"
    return d


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    base = json.load(open(sys.argv[1]))
    assert base.get("schema") == "L6Preset" and base["data"]["meta"].get("application") == "POD Go Edit"
    models = editor_models()
    os.makedirs(sys.argv[2], exist_ok=True)
    for name, (desc, chain, cost) in TEMPLATES.items():
        assert sum(1 for c in chain if c[0] != NAM) <= 7 and cost <= 7900, name
        out = os.path.join(sys.argv[2], name + ".pgp")
        json.dump(make(base, models, name, desc, chain), open(out, "w"), indent=1)
        print(f"wrote {out}: {desc} ({cost} units)")


if __name__ == "__main__":
    main()
