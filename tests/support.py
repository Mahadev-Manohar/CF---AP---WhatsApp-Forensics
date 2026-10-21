"""Shared fixtures: one synthetic corpus per test process, built under ./build (never in system temp dirs)."""

from __future__ import annotations

import atexit
import functools
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wa_synth.generate import build_corpus  # noqa: E402
from wa_forensics.analyze import analyze     # noqa: E402

BUILD = ROOT / "build"


def _rmtree(p: Path):
    def onerr(func, path, exc):           # evidence trees are read-only
        Path(path).chmod(stat.S_IWRITE)
        func(path)
    shutil.rmtree(p, onexc=onerr) if sys.version_info >= (3, 12) else shutil.rmtree(p, onerror=onerr)


def workdir(prefix: str) -> Path:
    BUILD.mkdir(exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix=prefix, dir=BUILD))
    atexit.register(_rmtree, d)
    return d


@functools.lru_cache(maxsize=1)
def corpus() -> dict:
    return build_corpus(workdir("corpus_") / "c")


@functools.lru_cache(maxsize=1)
def alice() -> dict:
    c = corpus()["alice"]
    return analyze(c["fs"], sim_number=c["truth"]["identity"]["sim_number"])


@functools.lru_cache(maxsize=1)
def bob() -> dict:
    return analyze(corpus()["bob"]["fs"])
