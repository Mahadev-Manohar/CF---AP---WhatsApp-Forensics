"""Sec. 4.2.1: encrypted msgstore backups (.crypt) and what they reveal about deleted messages."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import aes
from .case import Case
from .chat import Message, load_messages

# AES-192 key published in the paper (Sec. 4.2.1), common to all devices of that WhatsApp generation.
PAPER_KEY = bytes.fromhex("346a23652a46392b4d73257c67317e352e3372482177652c")
SQLITE_MAGIC = b"SQLite format 3\x00"


def decrypt_backup(path: str | Path, key: bytes = PAPER_KEY) -> bytes:
    plain = aes.ecb_decrypt(key, Path(path).read_bytes())
    if not plain.startswith(SQLITE_MAGIC):
        raise ValueError(f"{Path(path).name}: decrypted data is not an SQLite 3 database")
    return plain


def encrypt_backup(plain: bytes, key: bytes = PAPER_KEY) -> bytes:
    return aes.ecb_encrypt(key, plain)


def messages_from_backup(path: str | Path, key: bytes = PAPER_KEY) -> list[Message]:
    plain = decrypt_backup(path, key)
    con = sqlite3.connect(":memory:")
    try:
        con.deserialize(plain)
        return load_messages(con, source=Path(path).name)
    finally:
        con.close()


def list_backups(case: Case) -> list[Path]:
    d = case.backups_dir
    return sorted(p for p in d.iterdir() if ".crypt" in p.name or p.suffix == ".crypt") if d else []


def _ident(m: Message) -> tuple[str, str, bool]:
    return (m.remote_jid, m.key_id, m.from_me)


def deleted_vs_backups(live: list[Message], backups: dict[str, list[Message]]) -> list[dict]:
    """Messages present in some backup but missing from the live database (backups are not kept in sync
    with it, so they may hold messages the user deleted)."""
    live_ids = {_ident(m) for m in live}
    found: dict[tuple, dict] = {}
    for name, msgs in backups.items():
        for m in msgs:
            if _ident(m) in live_ids or m.status == 6:
                continue
            rec = found.setdefault(_ident(m), {
                "key_id": m.key_id, "remote_jid": m.remote_jid, "direction": "out" if m.from_me else "in",
                "type": m.type_name, "content": m.data, "backups": []})
            rec["backups"].append(name)
    return sorted(found.values(), key=lambda r: r["key_id"])
