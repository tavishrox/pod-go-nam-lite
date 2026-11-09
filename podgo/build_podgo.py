#!/usr/bin/env python3
"""Build POD Go 2.50 firmware with NAM A2 Lite in the amp list, on Line 6 Elektrik's identity.

    python3 podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf [-o OUT.hxf] [--no-check]
        [--donor elektrik|plexi] [--edition] [--splash IMG] [--splash-wireless IMG] [--model-names]

--edition: the ToneShift Edition: boot screens with "NAM A2 Edition" lettering (art/nam-a2-edition/, by ToneShift), drawn over the boot screens
of your own firmware file (no Line 6 artwork is in this repository). --splash IMG: a whole 480x272 image.
--model-names (experimental): the NAM block's Model knob shows the slot and its IR's name (podgo/model_names.py).

Unofficial and experimental: try it from RAM first (tools/hxf_ram.py run OUT --stock STOCK).
Steps (docs/PODGO_PORT_MAP.md):
  1. tools/sharc/nam_multi.py --mid-sweep --podgo --plexi --static-sdram --block32: the kernel, checked
     in the simulator (--no-check skips that; the web page skips it too)
  2. make_image(): podgo/podgo_model.py (Entries 0, 3, 4: the model, its knobs, name and DSP cost),
     optional boot screens (podgo/splash.py, Entry 8), podgo/podgo_e2.py (Entry 2: kernel and hook)
  3. tools/l6ia_verify.py, tools/hxf.py pack
The default build (Elektrik, no boot screens) is BUILT_MD5: web/pod-go/firmware-worker.js compares its result
with it, and tests/test_podgo_build.py keeps the two equal.
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'sharc'))

STOCK_MD5S = {'e0ea3e1ed32f0f353b79f6ad39631838'}           # POD_Go_v2.50.0_0x6e984472.hxf
BUILT_MD5 = '61920a6cdb5342cecffcd968e1ae6ad1'              # the default build's .hxf (Elektrik, no splash)
KERNEL_ARGS = ['--mid-sweep', '--podgo', '--plexi', '--static-sdram', '--block32']
OUT_NAME = 'POD_Go_v2.50.0_NAM_A2_Lite.hxf'
OUT_NAME_EDITION = 'POD_Go_v2.50.0_NAM_A2_Lite_ToneShift_Edition.hxf'
BUILT_MD5_EDITION = '70cfd341bb4bf00422f7ea19c5b49e95'                                    # the --edition build's .hxf
# --model-names (experimental, podgo/model_names.py): the same builds with the Model knob's names
BUILT_MD5_NAMES = '2cb121444bfe5e4a9259903b7ea2dc83'
BUILT_MD5_EDITION_NAMES = '0b27b025a84fc4a6d7af77f72f85d5ea'
EDITION = {'Splash': ('overlay', os.path.join(ROOT, 'art', 'nam-a2-edition', 'wired.png')),
           'Splash_Wireless': ('overlay', os.path.join(ROOT, 'art', 'nam-a2-edition', 'wireless.png'))}


def pinned_md5(edition, names):
    return {(False, False): BUILT_MD5, (True, False): BUILT_MD5_EDITION,
            (False, True): BUILT_MD5_NAMES, (True, True): BUILT_MD5_EDITION_NAMES}[edition, names]


def out_name(edition, names):
    base = OUT_NAME_EDITION if edition else OUT_NAME
    return base.replace('.hxf', '_Names.hxf') if names else base


def run(*args):
    print('$ ' + ' '.join(args[1:] if args[0] == sys.executable else args), flush=True)
    r = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(f'build_podgo.py: step failed ({args[1]})')
    return r.stdout


def make_image(data, asm_src, asm_name='nam_lite_podgo_b32.asm', donor=None, splashes=None, log=print,
               model_names=False):
    """The L6IA image with NAM A2 Lite: `data` the stock L6IA, `asm_src` the kernel (nam_multi.py's output).
    splashes: {'Splash' | 'Splash_Wireless': image path, or ('overlay', PNG) drawn over the stock screen}."""
    import kit_patch_amp as kp
    import l6ia
    import podgo_e2
    import podgo_model
    podgo_model.use_donor(donor or podgo_model.DEFAULT_DONOR)
    podgo_model.MODEL_NAMES = bool(model_names)
    log(f'[+] NAM replaces {podgo_model.DONOR_SHOWN}')
    new = podgo_model.build(data, log=log)
    for name, path in (splashes or {}).items():          # a boot screen (podgo/splash.py): Entry 8 in place
        import splash
        e7 = kp.get_entry_swapped(data, 7)
        e8 = new.get(8) or kp.get_entry_swapped(data, 8)
        overlay = isinstance(path, tuple)
        new[8] = splash.replace(e7, e8, name, path[1] if overlay else path, overlay=overlay)
        log(f'[+] Entry 8: {name} ' + (f'with {os.path.basename(path[1])} drawn over it' if overlay else f'replaced by {path}'))
    e = l6ia.parse(data)[2]
    e2 = podgo_e2.patch_e2(data[e['payload_off']: e['payload_off'] + e['payload_len']], asm_src, asm_name, log=log)
    new[2] = l6ia.swap32(e2)
    image, _, _ = l6ia.rebuild_archive(data, new)
    return image


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        sys.exit(__doc__)
    stock = os.path.abspath(a[0])
    md5 = hashlib.md5(open(stock, 'rb').read()).hexdigest()
    if md5 not in STOCK_MD5S:
        sys.exit(f'{stock}: MD5 {md5}, not POD_Go_v2.50.0_0x6e984472.hxf')
    build = os.path.join(ROOT, 'build')
    os.makedirs(build, exist_ok=True)
    out = os.path.abspath(a[a.index('-o') + 1]) if '-o' in a else \
        os.path.join(build, out_name('--edition' in a, '--model-names' in a))
    asm = os.path.join(build, 'nam_lite_podgo_b32.asm')
    meter = a[a.index('--meter') + 1] if '--meter' in a else None     # a test image (no check: it plays the meter)
    if meter:
        asm = asm.replace('.asm', f'_meter{meter}.asm')
    run(sys.executable, 'tools/sharc/nam_multi.py', *KERNEL_ARGS, '-o', asm,
        *(['--meter', meter] if meter else []), *([] if '--no-check' in a or meter else ['--check']))

    import patch_amp
    data, _ = patch_amp.load_l6ia_from_any(stock)
    splashes = dict(EDITION) if '--edition' in a else {}
    splashes.update({name: os.path.abspath(a[a.index(opt) + 1])
                     for opt, name in (('--splash', 'Splash'), ('--splash-wireless', 'Splash_Wireless')) if opt in a})
    image = make_image(data, open(asm).read(), os.path.basename(asm),
                       donor=a[a.index('--donor') + 1] if '--donor' in a else None, splashes=splashes,
                       model_names='--model-names' in a)
    img_path = os.path.join(build, 'POD_Go_v2.50.0_NAM_A2_Lite.l6ia')
    open(img_path, 'wb').write(image)
    report = run(sys.executable, 'tools/l6ia_verify.py', img_path)
    if 'ALL OK' not in report:
        sys.exit('build_podgo.py: the image failed its checksum check')
    run(sys.executable, 'tools/hxf.py', 'pack', img_path, out, '--donor', stock)
    got = hashlib.md5(open(out, 'rb').read()).hexdigest()
    pinned = None if meter or '--donor' in a or (splashes and splashes != EDITION) else \
        pinned_md5(bool(splashes), '--model-names' in a)
    tested = ', the project build (Model names: experimental)' if '--model-names' in a else ', the tested build'
    print(f'\nDone: {out} (MD5 {got}' + (tested if got == pinned else
                                         ', NOT the tested build: please report' if pinned else '') + ')')
    print(f'Try it from RAM first: python3 tools/hxf_ram.py run {os.path.relpath(out, ROOT)} --stock {a[0]}')


if __name__ == '__main__':
    main()
