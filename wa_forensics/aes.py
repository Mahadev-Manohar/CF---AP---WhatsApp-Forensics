"""Pure-Python AES (128/192/256) in ECB mode with PKCS#7 padding.

Written so the project needs no third-party crypto package. The paper reports that
WhatsApp's .crypt backups use AES-192; ECB is what the format used. It is NOT meant
for any security purpose and is verified against the FIPS-197 test vectors in tests.
"""

from __future__ import annotations


def _build_sbox() -> list[int]:
    sbox = [0] * 256
    p = q = 1
    while True:
        p = (p ^ (p << 1) ^ (0x1B if p & 0x80 else 0)) & 0xFF  # p *= 3
        q ^= (q << 1) & 0xFF                                     # q /= 3
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        if q & 0x80:
            q ^= 0x09
        rot = lambda x, n: ((x << n) | (x >> (8 - n))) & 0xFF
        sbox[p] = q ^ rot(q, 1) ^ rot(q, 2) ^ rot(q, 3) ^ rot(q, 4) ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


SBOX = _build_sbox()
INV_SBOX = [0] * 256
for _i, _v in enumerate(SBOX):
    INV_SBOX[_v] = _i


def _xtime(a: int) -> int:
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _gmul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


class AES:
    def __init__(self, key: bytes):
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16, 24 or 32 bytes")
        self.nk = len(key) // 4
        self.nr = self.nk + 6
        self._round_keys = self._expand(key)

    def _expand(self, key: bytes) -> list[list[int]]:
        words = [list(key[4 * i:4 * i + 4]) for i in range(self.nk)]
        rcon = 1
        for i in range(self.nk, 4 * (self.nr + 1)):
            t = list(words[i - 1])
            if i % self.nk == 0:
                t = [SBOX[b] for b in t[1:] + t[:1]]
                t[0] ^= rcon
                rcon = _xtime(rcon)
            elif self.nk > 6 and i % self.nk == 4:
                t = [SBOX[b] for b in t]
            words.append([a ^ b for a, b in zip(words[i - self.nk], t)])
        return [sum(words[4 * r:4 * r + 4], []) for r in range(self.nr + 1)]

    @staticmethod
    def _add(s: list[int], k: list[int]) -> None:
        for i in range(16):
            s[i] ^= k[i]

    def encrypt_block(self, block: bytes) -> bytes:
        s = list(block)
        self._add(s, self._round_keys[0])
        for rnd in range(1, self.nr + 1):
            s = [SBOX[b] for b in s]
            s = [s[(r + 4 * ((c + r) % 4))] for c in range(4) for r in range(4)]
            if rnd != self.nr:
                n = []
                for c in range(4):
                    a = s[4 * c:4 * c + 4]
                    n += [_gmul(a[0], 2) ^ _gmul(a[1], 3) ^ a[2] ^ a[3],
                          a[0] ^ _gmul(a[1], 2) ^ _gmul(a[2], 3) ^ a[3],
                          a[0] ^ a[1] ^ _gmul(a[2], 2) ^ _gmul(a[3], 3),
                          _gmul(a[0], 3) ^ a[1] ^ a[2] ^ _gmul(a[3], 2)]
                s = n
            self._add(s, self._round_keys[rnd])
        return bytes(s)

    def decrypt_block(self, block: bytes) -> bytes:
        s = list(block)
        self._add(s, self._round_keys[self.nr])
        for rnd in range(self.nr - 1, -1, -1):
            n = [0] * 16
            for c in range(4):
                for r in range(4):
                    n[r + 4 * ((c + r) % 4)] = s[r + 4 * c]
            s = [INV_SBOX[b] for b in n]
            self._add(s, self._round_keys[rnd])
            if rnd != 0:
                n = []
                for c in range(4):
                    a = s[4 * c:4 * c + 4]
                    n += [_gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9),
                          _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13),
                          _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11),
                          _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)]
                s = n
        return bytes(s)


def pkcs7_pad(data: bytes, block: int = 16) -> bytes:
    n = block - len(data) % block
    return data + bytes([n]) * n


def pkcs7_unpad(data: bytes, block: int = 16) -> bytes:
    if not data or len(data) % block:
        raise ValueError("ciphertext is not a multiple of the block size")
    n = data[-1]
    if not 1 <= n <= block or data[-n:] != bytes([n]) * n:
        raise ValueError("bad PKCS#7 padding (wrong key or corrupt file)")
    return data[:-n]


def ecb_encrypt(key: bytes, plaintext: bytes) -> bytes:
    a = AES(key)
    d = pkcs7_pad(plaintext)
    return b"".join(a.encrypt_block(d[i:i + 16]) for i in range(0, len(d), 16))


def ecb_decrypt(key: bytes, ciphertext: bytes) -> bytes:
    if len(ciphertext) % 16:
        raise ValueError("ciphertext is not a multiple of the block size")
    a = AES(key)
    d = b"".join(a.decrypt_block(ciphertext[i:i + 16]) for i in range(0, len(ciphertext), 16))
    return pkcs7_unpad(d)
