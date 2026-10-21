"""CLI:  python -m wa_forensics acquire|analyze ..."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import acquisition
from .analyze import analyze, to_json


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wa_forensics")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyse an extracted device tree")
    a.add_argument("root")
    a.add_argument("--sim", help="phone number of the SIM currently in the device")
    a.add_argument("--out", help="write JSON here (default: stdout)")
    q = sub.add_parser("acquire", help="verify and extract an evidence image")
    q.add_argument("image")
    q.add_argument("dest")
    q.add_argument("--sha256", required=True, help="expected SHA-256 of the image")
    args = ap.parse_args(argv)
    if args.cmd == "analyze":
        text = to_json(analyze(args.root, args.sim))
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text + "\n")
    else:
        c = acquisition.acquire(Path(args.image), Path(args.dest), args.sha256)
        print(json.dumps({"image_sha256": c["image_sha256"], "files": len(c["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
