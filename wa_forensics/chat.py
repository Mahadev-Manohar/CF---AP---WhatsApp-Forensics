"""Sec. 4.2.1-4.2.4: chat database, chat history, message content and message state."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .timeutil import from_ms, iso

MEDIA_TYPES = {0: "text", 1: "image", 2: "audio", 3: "video", 4: "contact card", 5: "geo position"}
BROADCAST_JID = "broadcast"


@dataclass
class Message:
    row_id: int
    remote_jid: str
    from_me: bool
    key_id: str
    status: int
    timestamp: int
    received_timestamp: int
    receipt_server_timestamp: int
    receipt_device_timestamp: int
    needs_push: int
    recipient_count: int | None
    remote_resource: str | None
    media_wa_type: int
    data: str | None
    media_url: str | None = None
    media_mime_type: str | None = None
    media_size: int | None = None
    media_name: str | None = None
    media_hash: str | None = None
    media_duration: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw_data: bytes | None = field(default=None, repr=False)
    source: str = "live"

    # --- derived -----------------------------------------------------------------------------
    @property
    def type_name(self) -> str:
        if self.status == 6:
            return "control"
        return MEDIA_TYPES.get(self.media_wa_type, f"unknown({self.media_wa_type})")

    @property
    def norm_key_id(self) -> str:
        """Broadcast recipients store '%~<id>' (Sec. 4.2.5); the sender's id is the part after it."""
        return re.sub(r"^%+~?", "", self.key_id)

    @property
    def is_broadcast_copy(self) -> bool:
        return self.key_id.startswith("%")

    @property
    def is_group(self) -> bool:
        return self.remote_jid.endswith("@g.us")

    @property
    def time(self):
        """When the message was sent (outgoing) / received (incoming)."""
        if self.from_me:
            return from_ms(self.timestamp)
        return from_ms(self.received_timestamp) or from_ms(self.timestamp)

    @property
    def state(self) -> str:
        """Sec. 4.2.4. Meaning of `status` for OUTGOING messages (key_from_me=1)."""
        if self.status == 6:
            return "CONTROL"
        if not self.from_me:
            return "RECEIVED"
        return {0: "NOT_YET_SENT_TO_SERVER", 4: "ON_SERVER_NOT_DELIVERED", 5: "DELIVERED"}.get(
            self.status, f"UNKNOWN({self.status})")

    def state_timeline(self) -> dict:
        t = {
            "created_at": iso(from_ms(self.timestamp)),
            "stored_at": iso(from_ms(self.received_timestamp)),
            "server_ack_at": iso(from_ms(self.receipt_server_timestamp)),
            "delivered_at": iso(from_ms(self.receipt_device_timestamp)),
        }
        out = {"state": self.state, **t}
        if self.from_me and self.receipt_server_timestamp > 0:
            out["waited_for_server_s"] = round((self.receipt_server_timestamp - self.timestamp) / 1000, 3)
        if self.from_me and self.receipt_device_timestamp > 0 and self.receipt_server_timestamp > 0:
            out["server_to_recipient_s"] = round(
                (self.receipt_device_timestamp - self.receipt_server_timestamp) / 1000, 3)
        return out


def _msg_from_row(r: sqlite3.Row, source: str) -> Message:
    return Message(
        row_id=r["_id"], remote_jid=r["key_remote_jid"], from_me=bool(r["key_from_me"]), key_id=r["key_id"],
        status=r["status"], timestamp=r["timestamp"], received_timestamp=r["received_timestamp"],
        receipt_server_timestamp=r["receipt_server_timestamp"], receipt_device_timestamp=r["receipt_device_timestamp"],
        needs_push=r["needs_push"], recipient_count=r["recipient_count"], remote_resource=r["remote_resource"],
        media_wa_type=r["media_wa_type"], data=r["data"], media_url=r["media_url"],
        media_mime_type=r["media_mime_type"], media_size=r["media_size"], media_name=r["media_name"],
        media_hash=r["media_hash"], media_duration=r["media_duration"], latitude=r["latitude"],
        longitude=r["longitude"], raw_data=r["raw_data"], source=source)


def load_messages(con: sqlite3.Connection, source: str = "live") -> list[Message]:
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM messages ORDER BY _id").fetchall()
    return [_msg_from_row(r, source) for r in rows]


def load_messages_from_file(path, source: str = "live") -> list[Message]:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return load_messages(con, source)
    finally:
        con.close()


def load_chat_list(path) -> list[dict]:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT * FROM chat_list ORDER BY _id")]
    finally:
        con.close()


def conversations(messages: list[Message]) -> dict[str, list[Message]]:
    """Sec. 4.2.2: messages grouped per partner (jid), each in chronological order."""
    conv: dict[str, list[Message]] = {}
    for m in messages:
        if m.status == 6:
            continue
        conv.setdefault(m.remote_jid, []).append(m)
    for v in conv.values():
        v.sort(key=lambda m: (m.time, m.row_id))
    return conv


def correlate(sender_msgs: list[Message], recipient_msgs: list[Message]) -> list[tuple[Message, Message]]:
    """Sec. 4.2.2: pair a sender's outgoing record with the recipient's incoming record through the
    shared key_id (set by the sender, reused by the recipient)."""
    inc: dict[str, Message] = {}
    for m in recipient_msgs:
        if not m.from_me and m.status != 6:
            inc.setdefault(m.norm_key_id, m)
    return [(m, inc[m.norm_key_id]) for m in sender_msgs
            if m.from_me and m.status != 6 and m.remote_jid != BROADCAST_JID and m.norm_key_id in inc]


def key_id_parts(key_id: str) -> tuple[int, int]:
    """key_id = <last WhatsApp start time (s)>-<progressive number>. Returns (epoch_s, counter)."""
    m = re.match(r"^%*~?(\d+)-(\d+)$", key_id)
    if not m:
        raise ValueError(f"unrecognised key_id {key_id!r}")
    return int(m.group(1)), int(m.group(2))
