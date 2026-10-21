"""Sec. 4.2.6: deleted messages reconstructed from the log files (content itself is not in the logs)."""

from __future__ import annotations

from .chat import Message
from .logparser import Event
from .timeutil import iso


def deleted_from_logs(events: list[Event], live: list[Message]) -> list[dict]:
    """For every `msgstore/delete <key_id>` event, collect the log events carrying the same key_id
    (send/receive and the two acknowledgements) to recover who, when and the delivery state."""
    live_ids = {m.key_id for m in live}
    by_key: dict[str, list[Event]] = {}
    for e in events:
        if e.kind in ("msg_send", "msg_receive", "receipt_server", "receipt_device"):
            by_key.setdefault(e.fields["key_id"], []).append(e)
    out = []
    for d in (e for e in events if e.kind == "msg_delete"):
        kid = d.fields["key_id"]
        related = by_key.get(kid, [])
        send = next((e for e in related if e.kind == "msg_send"), None)
        recv = next((e for e in related if e.kind == "msg_receive"), None)
        srv = next((e for e in related if e.kind == "receipt_server"), None)
        dev = next((e for e in related if e.kind == "receipt_device"), None)
        origin = send or recv
        state = None
        if send:
            state = "DELIVERED" if dev else ("ON_SERVER_NOT_DELIVERED" if srv else "NOT_YET_SENT_TO_SERVER")
        elif recv:
            state = "RECEIVED"
        out.append({
            "key_id": kid, "deleted_at": iso(d.ts), "direction": "out" if send else ("in" if recv else None),
            "partner": origin.fields["jid"] if origin else None,
            "exchanged_at": iso(origin.ts) if origin else None,
            "server_ack_at": iso(srv.ts) if srv else None, "delivered_at": iso(dev.ts) if dev else None,
            "state": state, "still_in_live_db": kid in live_ids,
            "content_recoverable_from_logs": False,
        })
    return out
