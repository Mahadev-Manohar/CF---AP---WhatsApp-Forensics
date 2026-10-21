"""Acquisition stage (stand-in for the paper's "open the VDI in FTK Imager and export the files").

DEVIATION (docs/deviations.md D-02): the evidence container here is a plain tar archive, not a VirtualBox VDI,
and extraction is done by this module, not FTK Imager. What is preserved is the forensic discipline: hash the
container before and after, never write to it, extract read-only, verify every extracted file against a
manifest and keep a chain-of-custody log.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_manifest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}


def create_image(src_root: Path, image_path: Path) -> dict:
    """Pack a file tree into an 'evidence image' and return its descriptor (hash + manifest)."""
    src_root, image_path = Path(src_root), Path(image_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(image_path, "w") as tf:
        for p in sorted(src_root.rglob("*")):
            ti = tf.gettarinfo(str(p), p.relative_to(src_root).as_posix())
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            if p.is_file():
                with open(p, "rb") as f:
                    tf.addfile(ti, f)
            else:
                tf.addfile(ti)
    return {"image": str(image_path), "image_sha256": sha256_file(image_path), "manifest": tree_manifest(src_root)}


class AcquisitionError(RuntimeError):
    pass


def acquire(image_path: Path, dest: Path, expected_image_sha256: str, expected_manifest: dict[str, str] | None = None,
            examiner: str = "automated-test") -> dict:
    """Verify -> extract read-only -> verify again. Raises AcquisitionError on any mismatch."""
    image_path, dest = Path(image_path), Path(dest)
    log: list[dict] = []

    def note(action: str, **kw):
        log.append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "action": action, **kw})

    before = sha256_file(image_path)
    note("hash_image_before", sha256=before, examiner=examiner)
    if before != expected_image_sha256:
        raise AcquisitionError("image hash does not match the expected value; refusing to extract")
    if dest.exists() and any(dest.iterdir()):
        raise AcquisitionError("destination is not empty")
    dest.mkdir(parents=True, exist_ok=True)

    with tarfile.open(image_path, "r:") as tf:          # read-only open
        members = tf.getmembers()
        for m in members:                                # no path traversal, no links/devices
            if not (m.isfile() or m.isdir()) or m.name.startswith(("/", "\\")) or ".." in Path(m.name).parts:
                raise AcquisitionError(f"unsafe member in image: {m.name!r}")
        tf.extractall(dest, filter="data")
    note("extract", files=sum(m.isfile() for m in members))

    got = tree_manifest(dest)
    if expected_manifest is not None and got != expected_manifest:
        diff = sorted(set(got) ^ set(expected_manifest) | {k for k in got if k in expected_manifest and got[k] != expected_manifest[k]})
        raise AcquisitionError(f"extracted tree differs from manifest: {diff[:5]}")
    note("verify_manifest", files=len(got), ok=True)

    for p in dest.rglob("*"):                            # mark evidence read-only
        if p.is_file():
            os.chmod(p, stat.S_IREAD)
    after = sha256_file(image_path)
    note("hash_image_after", sha256=after)
    if after != before:
        raise AcquisitionError("image changed during acquisition")
    custody = {"image": image_path.name, "image_sha256": before, "files": got, "log": log}
    (dest.parent / (dest.name + ".custody.json")).write_text(json.dumps(custody, indent=2), encoding="utf-8")
    return custody
