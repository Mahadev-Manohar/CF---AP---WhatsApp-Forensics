import unittest

from tests import support  # noqa: F401
from wa_forensics import aes
from wa_forensics.backups import PAPER_KEY, decrypt_backup, encrypt_backup

PT = bytes.fromhex("00112233445566778899aabbccddeeff")


class AesVectors(unittest.TestCase):
    """FIPS-197 appendix C known-answer tests."""

    def test_fips197(self):
        for n, ct in ((16, "69c4e0d86a7b0430d8cdb78070b4c55a"), (24, "dda97ca4864cdfe06eaf70a0ec0d7191"),
                      (32, "8ea2b7ca516745bfeafc49904b496089")):
            with self.subTest(bits=n * 8):
                a = aes.AES(bytes(range(n)))
                self.assertEqual(a.encrypt_block(PT).hex(), ct)
                self.assertEqual(a.decrypt_block(bytes.fromhex(ct)), PT)

    def test_paper_key_is_aes192(self):
        self.assertEqual(len(PAPER_KEY), 24)
        self.assertEqual(PAPER_KEY.hex(), "346a23652a46392b4d73257c67317e352e3372482177652c")

    def test_roundtrip_and_padding(self):
        for n in (0, 1, 15, 16, 17, 1000):
            data = bytes(range(256)) * 4
            data = data[:n]
            self.assertEqual(aes.ecb_decrypt(PAPER_KEY, aes.ecb_encrypt(PAPER_KEY, data)), data)

    def test_wrong_key_rejected(self):
        blob = encrypt_backup(b"SQLite format 3\x00" + b"x" * 100)
        with self.assertRaises(ValueError):
            aes.ecb_decrypt(bytes(24), blob)

    def test_bad_key_length(self):
        with self.assertRaises(ValueError):
            aes.AES(b"short")


class BackupDecrypt(unittest.TestCase):
    def test_non_sqlite_plaintext_rejected(self):
        d = support.workdir("aes_")
        p = d / "x.crypt"
        p.write_bytes(encrypt_backup(b"this is not a database"))
        with self.assertRaises(ValueError):
            decrypt_backup(p)


if __name__ == "__main__":
    unittest.main()
