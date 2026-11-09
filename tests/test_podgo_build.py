"""The POD Go web builder (web/pod-go/firmware-worker.js) and the desktop build (podgo/build_podgo.py) agree:
the stock and built MD5s, the kernel's options, the output name, and every source the build imports."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'podgo'))
import build_podgo  # noqa: E402

JS = open(os.path.join(ROOT, 'web', 'pod-go', 'firmware-worker.js')).read()


def js_value(name):
    m = re.search(r'var %s = (.+?);\n' % name, JS, re.S)
    assert m, name
    return eval(m.group(1).replace('\n', ''))


def test_md5s_and_options_match():
    assert {js_value('STOCK_MD5')} == build_podgo.STOCK_MD5S
    assert js_value('BUILT_MD5') == build_podgo.BUILT_MD5
    assert js_value('KERNEL_ARGS') == build_podgo.KERNEL_ARGS
    assert js_value('OUT_NAME') == build_podgo.OUT_NAME
    assert js_value('BUILT_MD5_EDITION') == build_podgo.BUILT_MD5_EDITION
    assert js_value('OUT_NAME_EDITION') == build_podgo.OUT_NAME_EDITION
    assert js_value('BUILT_MD5_NAMES') == build_podgo.BUILT_MD5_NAMES
    assert js_value('BUILT_MD5_EDITION_NAMES') == build_podgo.BUILT_MD5_EDITION_NAMES
    assert build_podgo.out_name(True, True) == 'POD_Go_v2.50.0_NAM_A2_Lite_ToneShift_Edition_Names.hxf'
    for path in js_value('EDITION_SOURCES'):
        assert os.path.exists(os.path.join(ROOT, path)), path
    assert {os.path.relpath(v[1], ROOT) for v in build_podgo.EDITION.values()} <= set(js_value('EDITION_SOURCES'))


def test_sources_exist_and_cover_the_imports():
    sources = js_value('SOURCES')
    for path in sources:
        assert os.path.exists(os.path.join(ROOT, path)), path
    names = {os.path.splitext(os.path.basename(p))[0] for p in sources}
    for mod in ('build_podgo', 'podgo_model', 'podgo_e2', 'kit_patch_amp', 'patch_amp', 'effects', 'l6ia',
                'hxf', 'sasm', 'ssim', 'entry4_blob', 'nam_multi', 'nam_lite', 'nam_pack', 'l6ia_verify'):
        assert mod in names, mod
