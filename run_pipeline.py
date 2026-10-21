"""End-to-end demo on SYNTHETIC data:  generate -> image -> acquire (verify, read-only) -> analyse -> JSON + summary.

    python run_pipeline.py [output_dir]      (default: ./output ; refuses to overwrite)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from wa_forensics import acquisition
from wa_forensics.analyze import analyze, to_json
from wa_synth.generate import build_corpus


def main(out: Path) -> int:
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        print(f"{out} is not empty; refusing to overwrite", file=sys.stderr)
        return 1
    corpus = build_corpus(out / "corpus")
    for dev, c in corpus.items():
        desc = acquisition.create_image(c["fs"], out / "images" / f"{dev}.img")
        custody = acquisition.acquire(Path(desc["image"]), out / "acquired" / dev, desc["image_sha256"], desc["manifest"])
        sim = c["truth"].get("identity", {}).get("sim_number")
        result = analyze(out / "acquired" / dev, sim)
        (out / f"report_{dev}.json").write_text(to_json(result), encoding="utf-8")
        print(f"[{dev}] image sha256={custody['image_sha256'][:16]}...  files={len(custody['files'])}  "
              f"messages={result['counts']['live_messages']}  log_events={result['counts']['log_events']}  "
              f"backups={result['counts']['backups']}")
    a = json.loads((out / "report_alice.json").read_text(encoding="utf-8"))
    print("\nalice: deleted contacts (from logs):", a["deleted_contacts_from_logs"])
    print("alice: blocks:", {j[:11]: v["status"] for j, v in a["blocks"].items()})
    print("alice: deleted messages found in logs:", [d["key_id"] for d in a["deleted_messages_from_logs"]])
    print("alice: ... of which recovered from backups:", [d["key_id"] for d in a["deleted_messages_from_backups"]])
    print(f"\nreports written to {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "output")))
