#!/usr/bin/env python3
"""Build POD Go 2.50 firmware with NAM A2 Lite in the amp slot, on Brit Plexi Brt's identity.

    python3 podgo/build_podgo.py POD_Go_v2.50.0_0x6e984472.hxf [-o OUT.hxf] [--no-check] [--donor elektrik|plexi] [--splash IMG] [--splash-wireless IMG]

Unofficial and experimental: try it from RAM first (tools/hxf_ram.py run OUT --stock STOCK).
Steps (docs/PODGO_PORT_MAP.md):
  1. tools/sharc/nam_multi.py --mid-sweep --podgo --plexi --static-sdram --block32: the kernel, checked in the simulator
  2. podgo/podgo_model.py: Entry 4 (NAM host graph) and Entry 3 (model 74's knobs, Plexi layout)
  3. podgo/podgo_e2.py: Entry 2 (Blob 0 buffer, region A moved, kernel, primitive 0x9c75)
  4. tools/l6ia_verify.py, tools/hxf.py pack
Entry 0 (the application) is not changed yet: the unit lists the block as Brit Plexi Brt.
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



def run(*args):
    print('$ ' + ' '.join(args[1:] if args[0] == sys.executable else args), flush=True)
    r = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        sys.exit(f'build_podgo.py: step failed ({args[1]})')
    return r.stdout


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
    out = os.path.abspath(a[a.index('-o') + 1]) if '-o' in a else os.path.join(build, 'POD_Go_v2.50.0_NAM_A2_Lite.hxf')
    asm = os.path.join(build, 'nam_lite_podgo_b32.asm')
    meter = a[a.index('--meter') + 1] if '--meter' in a else None     # a test image (no check: it plays the meter)
    if meter:
        asm = asm.replace('.asm', f'_meter{meter}.asm')
    run(sys.executable, 'tools/sharc/nam_multi.py', '--mid-sweep', '--podgo', '--plexi', '--static-sdram', '--block32', '-o', asm,
        *(['--meter', meter] if meter else []), *([] if '--no-check' in a or meter else ['--check']))

    import l6ia
    import patch_amp
    import podgo_e2
    import podgo_model
    podgo_model.use_donor(a[a.index('--donor') + 1] if '--donor' in a else podgo_model.DEFAULT_DONOR)
    print(f'[+] NAM replaces {podgo_model.DONOR_SHOWN}')
    data, _ = patch_amp.load_l6ia_from_any(stock)
    new = podgo_model.build(data)
    for opt_, name in (('--splash', 'Splash'), ('--splash-wireless', 'Splash_Wireless')):
        if opt_ in a:                                   # a boot screen (podgo/splash.py): Entry 8 in place
            import splash
            kp = __import__('kit_patch_amp')
            e7 = kp.get_entry_swapped(data, 7)
            e8 = new.get(8) or kp.get_entry_swapped(data, 8)
            new[8] = splash.replace(e7, e8, name, os.path.abspath(a[a.index(opt_) + 1]))
            print(f'[+] Entry 8: {name} replaced by {a[a.index(opt_) + 1]}')
    e = l6ia.parse(data)[2]
    e2 = podgo_e2.patch_e2(data[e['payload_off']: e['payload_off'] + e['payload_len']],
                           open(asm).read(), os.path.basename(asm))
    new[2] = l6ia.swap32(e2)
    image, _, _ = l6ia.rebuild_archive(data, new)
    img_path = os.path.join(build, 'POD_Go_v2.50.0_NAM_A2_Lite.l6ia')
    open(img_path, 'wb').write(image)
    report = run(sys.executable, 'tools/l6ia_verify.py', img_path)
    if 'ALL OK' not in report:
        sys.exit('build_podgo.py: the image failed its checksum check')
    run(sys.executable, 'tools/hxf.py', 'pack', img_path, out, '--donor', stock)
    print(f'\nDone: {out}\nTry it from RAM first: python3 tools/hxf_ram.py run {os.path.relpath(out, ROOT)} '
          f'--stock {a[0]}')


STOCK_MD5S = {'e0ea3e1ed32f0f353b79f6ad39631838'}           # POD_Go_v2.50.0_0x6e984472.hxf

if __name__ == '__main__':
    main()
