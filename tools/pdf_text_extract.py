import re, zlib, sys

d = open(sys.argv[1], 'rb').read()
pages = []
for m in re.finditer(rb'stream\r?\n', d):
    e = d.find(b'endstream', m.end())
    try:
        s = zlib.decompress(d[m.end():e])
    except Exception:
        continue
    if not s.startswith(b'q\n1 0 0 1') or b'BT' not in s:
        continue
    out = []
    tok = re.compile(rb'\[((?:\\.|[^\]\\])*)\]\s*TJ|(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+Td|(ET)', re.S)
    for tm in tok.finditer(s):
        if tm.group(1) is not None:
            t = ''
            for a, n in re.findall(rb'\(((?:\\.|[^\\)])*)\)|(-?\d+\.?\d*)', tm.group(1)):
                if a:
                    t += a.decode('latin1')
                elif n and float(n) < -200:
                    t += ' '
            out.append(t)
        elif tm.group(3) is not None:
            if abs(float(tm.group(3))) > 1:
                out.append('\n')
        elif tm.group(4):
            out.append('\n')
    t = ''.join(out)
    t = re.sub(r'\\([()\\])', r'\1', t)
    t = re.sub(r'\\(\d{3})', lambda x: chr(int(x.group(1), 8)), t)
    for a, b in (('\x0c', 'fi'), ('\x0d', 'fl'), ('\x0b', 'ff'), ('\x0e', 'ffi'), ('\x0f', 'ffl')):
        t = t.replace(a, b)
    pages.append(re.sub(r'\n{2,}', '\n', t))
open(sys.argv[2], 'w', encoding='utf-8').write('\n\n=====PAGE=====\n'.join(pages))
print(len(pages), 'pages')
