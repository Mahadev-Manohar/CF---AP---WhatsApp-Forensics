"""Sec. 4.2.3: multimedia files, contact cards and geolocation messages."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from .case import Case
from .chat import Message


def media_hash_b64(data: bytes) -> str:
    """The media_hash field: base64 of the SHA-256 digest of the file."""
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


def server_filename(url: str | None) -> str | None:
    """Last path component of media_url = name given by the WhatsApp server (same on both sides)."""
    return url.rstrip("/").rsplit("/", 1)[-1] if url else None


def index_media_files(case: Case) -> dict[str, list[dict]]:
    """base64-SHA256 -> files, from the received (Media) and sent (Media/Sent) folders."""
    idx: dict[str, list[dict]] = {}
    sent = case.media_sent_dir
    for folder, where in ((case.media_dir, "received"), (sent, "sent")):
        if folder is None:
            continue
        for p in sorted(folder.iterdir()):
            if p.is_file():
                if where == "received" and sent and p.parent == sent:
                    continue
                idx.setdefault(media_hash_b64(p.read_bytes()), []).append({"path": p, "where": where, "name": p.name})
    return idx


def resolve_media(messages: list[Message], index: dict[str, list[dict]]) -> list[dict]:
    """For each image/audio/video message: stored metadata and the file found by SHA-256 match."""
    out = []
    for m in messages:
        if m.media_wa_type not in (1, 2, 3) or m.status == 6:
            continue
        files = index.get(m.media_hash or "", [])
        mine = [f for f in files if f["where"] == ("sent" if m.from_me else "received")]
        out.append({
            "key_id": m.key_id, "direction": "out" if m.from_me else "in", "type": m.type_name,
            "mime": m.media_mime_type, "declared_size": m.media_size, "media_name": m.media_name,
            "server_filename": server_filename(m.media_url), "media_hash": m.media_hash,
            "matched_file": mine[0]["name"] if mine else None,
            "matched_by": "media_name" if m.media_name and mine and mine[0]["name"] == m.media_name else
                          ("sha256" if mine else None),
            "size_matches": bool(mine) and mine[0]["path"].stat().st_size == m.media_size,
        })
    return out


def parse_vcard(text: str) -> dict:
    fields: dict[str, list[str]] = {}
    for line in (text or "").splitlines():
        if ":" in line and not line.startswith("BEGIN") and not line.startswith("END"):
            k, v = line.split(":", 1)
            fields.setdefault(k.split(";")[0].upper(), []).append(v.strip())
    return {"full_name": (fields.get("FN") or [None])[0], "phones": fields.get("TEL", []),
            "version": (fields.get("VERSION") or [None])[0]}


def contact_cards(messages: list[Message]) -> list[dict]:
    return [{"key_id": m.key_id, "direction": "out" if m.from_me else "in", "name_given_by_sender": m.media_name,
             **parse_vcard(m.data or "")} for m in messages if m.media_wa_type == 4 and m.status != 6]


def locations(messages: list[Message]) -> list[dict]:
    return [{"key_id": m.key_id, "direction": "out" if m.from_me else "in", "latitude": m.latitude,
             "longitude": m.longitude, "has_map_thumbnail": bool(m.raw_data)}
            for m in messages if m.media_wa_type == 5 and m.status != 6]


def correlate_media(sent: Message, received: Message) -> dict:
    """Sender- and recipient-side records of one file correlate by server filename and by hash."""
    return {"same_server_filename": server_filename(sent.media_url) == server_filename(received.media_url),
            "same_hash": sent.media_hash == received.media_hash,
            "same_size": sent.media_size == received.media_size,
            "urls_differ_in_host_path": sent.media_url != received.media_url}
