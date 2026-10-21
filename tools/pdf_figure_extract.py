import re, zlib, struct, sys, os

d = open(sys.argv[1], 'rb').read()
outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)


def png(path, w, h, ch, raw):
    ct = {1: 0, 3: 2, 4: 6}[ch]
    rows = b''.join(b'\x00' + raw[y * w * ch:(y + 1) * w * ch] for y in range(h))

    def chunk(t, b):
        c = struct.pack('>I', len(b)) + t + b
        return c + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, ct, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


n = 0
for m in re.finditer(rb'(\d+) 0 obj\s*<<(.*?)>>\s*stream\r?\n', d, re.S):
    hdr = m.group(2)
    if b'/Subtype' not in hdr or b'/Image' not in hdr:
        continue
    e = d.find(b'endstream', m.end())
    data = d[m.end():e]
    w = int(re.search(rb'/Width\s+(\d+)', hdr).group(1))
    h = int(re.search(rb'/Height\s+(\d+)', hdr).group(1))
    n += 1
    name = f'{outdir}/img{n:02d}_obj{m.group(1).decode()}_{w}x{h}'
    if b'DCTDecode' in hdr:
        open(name + '.jpg', 'wb').write(data.rstrip(b'\r\n'))
    elif b'FlateDecode' in hdr and b'/DeviceRGB' in hdr and b'/Predictor' not in hdr:
        try:
            raw = zlib.decompress(data)
            if len(raw) == w * h * 3:
                png(name + '.png', w, h, 3, raw)
            else:
                print('skip size', name, len(raw), w * h * 3)
        except Exception as ex:
            print('err', name, ex)
    else:
        print('unhandled', name, hdr[:150])
print(n, 'images')
