"""Poor-man's mutation test: inject one plausible bug at a time and confirm the suite fails.

Run from the project root:  python tools/mutation_check.py
The baseline must be green first; the original source is always restored.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MUTANTS = [
    ("wa_forensics/contacts.py", "if len(cands) == 1:", "if len(cands) >= 1:", "unblock ambiguity resolved eagerly"),
    ("wa_forensics/groups.py", "if e.time > at:", "if e.time >= at:", "membership boundary off-by-one"),
    ("wa_forensics/chat.py", '{0: "NOT_YET_SENT_TO_SERVER", 4: "ON_SERVER_NOT_DELIVERED", 5: "DELIVERED"}',
     '{0: "NOT_YET_SENT_TO_SERVER", 4: "DELIVERED", 5: "ON_SERVER_NOT_DELIVERED"}', "status 4/5 swapped"),
    ("wa_forensics/timeutil.py", "ms / 1000", "ms / 1001", "ms timestamp unit slip"),
    ("wa_forensics/timeutil.py", "datetime.fromtimestamp(s, tz=UTC)", "datetime.fromtimestamp(s * 1000, tz=UTC)", "s timestamp unit slip"),
    ("wa_forensics/media.py", "hashlib.sha256(data).digest()).decode", "hashlib.sha1(data).digest()).decode", "wrong media hash algorithm"),
    ("wa_forensics/backups.py", 'bytes.fromhex("346a', 'bytes.fromhex("356a', "wrong AES key"),
    ("wa_forensics/contacts.py", '"has_avatar_file": f"{jid}.j" in avatars', '"has_avatar_file": False', "avatar flag broken"),
    ("wa_forensics/contacts.py", 'p.name.endswith(".j") and p.name[:-2] not in present', "False", "orphan avatars never found"),
    ("wa_forensics/deleted.py", '"deleted_at": iso(d.ts)', '"deleted_at": iso(origin.ts if origin else d.ts)', "deletion time wrong"),
    ("wa_forensics/logparser.py", "msgstore/add/receive", "msgstore/add/recv", "receive event regex broken"),
    ("wa_forensics/chat.py", 're.sub(r"^%+~?", "", self.key_id)', "self.key_id", "broadcast prefix not stripped"),
    ("wa_forensics/backups.py", "if _ident(m) in live_ids or m.status == 6:", "if m.status == 6:", "backup diff ignores live db"),
    ("wa_forensics/contacts.py", 'setdefault(e.fields["jid"]', 'setdefault(e.fields["jid"] + "x"', "contact-add key corrupted"),
    ("wa_forensics/groups.py", "e.op in (\"create\", \"join\")", "e.op in (\"join\",)", "group creator not a member"),
    ("wa_forensics/acquisition.py", "if after != before:", "if False:", "image-modified check removed"),
    ("wa_forensics/acquisition.py", 'if before != expected_image_sha256:', "if False:", "image hash check removed"),
]


def suite_ok() -> bool:
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    if not suite_ok():
        print("baseline suite is NOT green; aborting")
        return 2
    survived = 0
    for rel, old, new, name in MUTANTS:
        path = ROOT / rel
        src = path.read_text(encoding="utf-8")
        if old not in src:
            print(f"N/A       {name}  (pattern not found: update the mutant)")
            survived += 1
            continue
        path.write_text(src.replace(old, new, 1), encoding="utf-8")
        try:
            ok = suite_ok()
        finally:
            path.write_text(src, encoding="utf-8")
        print(("SURVIVED " if ok else "killed   ") + name)
        survived += ok
    print(f"\n{len(MUTANTS) - survived}/{len(MUTANTS)} mutants killed")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
