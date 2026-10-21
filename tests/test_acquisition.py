import json
import tarfile
import unittest
from pathlib import Path

from tests import support
from wa_forensics import acquisition
from wa_forensics.analyze import analyze

C = support.corpus()


class Acquisition(unittest.TestCase):
    def setUp(self):
        self.w = support.workdir("acq_")
        self.desc = acquisition.create_image(C["alice"]["fs"], self.w / "alice.img")

    def test_roundtrip_and_analysis_equivalence(self):
        dest = self.w / "extracted"
        custody = acquisition.acquire(self.w / "alice.img", dest, self.desc["image_sha256"], self.desc["manifest"])
        self.assertEqual(custody["files"], self.desc["manifest"])
        self.assertEqual([x["action"] for x in custody["log"]],
                         ["hash_image_before", "extract", "verify_manifest", "hash_image_after"])
        self.assertEqual(custody["log"][0]["sha256"], custody["log"][-1]["sha256"])
        self.assertTrue((self.w / "extracted.custody.json").exists())
        sim = C["alice"]["truth"]["identity"]["sim_number"]
        self.assertEqual(json.dumps(analyze(dest, sim), sort_keys=True),
                         json.dumps(analyze(C["alice"]["fs"], sim), sort_keys=True))

    def test_image_is_not_modified(self):
        before = acquisition.sha256_file(self.w / "alice.img")
        acquisition.acquire(self.w / "alice.img", self.w / "x", self.desc["image_sha256"])
        self.assertEqual(acquisition.sha256_file(self.w / "alice.img"), before)

    def test_image_changed_during_acquisition_is_detected(self):
        from unittest import mock
        img = self.w / "alice.img"
        real, seen = acquisition.sha256_file, []

        def flaky(p):
            h = real(p)
            if Path(p) == img:
                seen.append(h)
                if len(seen) == 2:                 # the "after" hash: pretend the image changed underneath us
                    return "f" * 64
            return h
        with mock.patch.object(acquisition, "sha256_file", flaky):
            with self.assertRaises(acquisition.AcquisitionError):
                acquisition.acquire(img, self.w / "x", self.desc["image_sha256"])

    def test_extracted_files_are_read_only(self):
        acquisition.acquire(self.w / "alice.img", self.w / "x", self.desc["image_sha256"])
        p = next((self.w / "x").rglob("wa.db"))
        with self.assertRaises(PermissionError):
            open(p, "ab")

    def test_tampered_image_refused(self):
        img = self.w / "alice.img"
        raw = bytearray(img.read_bytes())
        raw[2000] ^= 0xFF
        img.write_bytes(bytes(raw))
        with self.assertRaises(acquisition.AcquisitionError):
            acquisition.acquire(img, self.w / "x", self.desc["image_sha256"])
        self.assertFalse((self.w / "x").exists())            # nothing extracted

    def test_manifest_mismatch_detected(self):
        bad = dict(self.desc["manifest"])
        k = sorted(bad)[0]
        bad[k] = "0" * 64
        with self.assertRaises(acquisition.AcquisitionError):
            acquisition.acquire(self.w / "alice.img", self.w / "x", self.desc["image_sha256"], bad)

    def test_path_traversal_member_refused(self):
        evil = self.w / "evil.img"
        with tarfile.open(evil, "w") as tf:
            ti = tarfile.TarInfo("../escape.txt")
            ti.size = 1
            import io
            tf.addfile(ti, io.BytesIO(b"x"))
        with self.assertRaises(acquisition.AcquisitionError):
            acquisition.acquire(evil, self.w / "y", acquisition.sha256_file(evil))
        self.assertFalse((self.w / "escape.txt").exists())

    def test_nonempty_destination_refused(self):
        (self.w / "z").mkdir()
        (self.w / "z" / "f").write_text("x")
        with self.assertRaises(acquisition.AcquisitionError):
            acquisition.acquire(self.w / "alice.img", self.w / "z", self.desc["image_sha256"])


class Generator(unittest.TestCase):
    def test_all_numbers_are_fictional(self):
        import re
        blob = (C["alice"]["fs"].parent / "ground_truth.json").read_text()
        for n in set(re.findall(r"\b1\d{10}\b", blob)):
            self.assertTrue(n.startswith("120255501"), n)    # 202-555-01xx fictional range

    def test_generator_is_deterministic(self):
        w = support.workdir("det_")
        from wa_synth.generate import build_corpus
        c2 = build_corpus(w / "c")
        m1 = acquisition.tree_manifest(C["alice"]["fs"])
        m2 = acquisition.tree_manifest(c2["alice"]["fs"])
        self.assertEqual(m1, m2)

    def test_generator_refuses_overwrite(self):
        from wa_synth.generate import build_corpus
        with self.assertRaises(FileExistsError):
            build_corpus(C["alice"]["fs"].parent.parent)


if __name__ == "__main__":
    unittest.main()
