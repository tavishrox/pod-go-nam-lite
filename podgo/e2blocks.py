"""Shared helper: the POD Go's SHARC LDR stream (Entry 2) as a list of blocks with their payload words."""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import l6ia  # noqa: E402

NW = {5: lambda c: ((c + 1) & ~1) * 3 // 2, 4: lambda c: c, 3: lambda c: (c + 1) // 2,
      6: lambda c: c * 2, 0: lambda c: 384, 10: lambda c: c, 9: lambda c: c, 1: lambda c: 0, 2: lambda c: 0}


def load_l6ia(path):
    d = open(path, 'rb').read()
    if d[:4] == b'FORM':
        import zlib, hxf
        d = zlib.decompress([b for c, p, s, b in hxf._chunks(d) if c == b'data'][0])
    return d


def e2_words(path):
    d = load_l6ia(path)
    e = l6ia.parse(d)[2]
    e2 = d[e['payload_off']: e['payload_off'] + e['payload_len']]
    return list(struct.unpack('<%dI' % (len(e2) // 4), e2))


def blocks(w):
    i, out = 384, []
    while i + 3 <= len(w):
        tag, cnt, addr = w[i:i + 3]
        n = NW[tag](cnt)
        out.append(dict(w=i, tag=tag, cnt=cnt, addr=addr, data=w[i + 3:i + 3 + n]))
        if tag == 0:
            break
        i += 3 + n
    return out
