"""Sec. 4.2.5: partners of a message: broadcast lists, group chats, group membership over time."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .chat import BROADCAST_JID, Message
from .logparser import Event
from .timeutil import from_ms, from_s, iso

CONTROL_OPS = {1: "create", 4: "join", 5: "leave"}   # media_size of status=6 records


def broadcasts_sent(messages: list[Message]) -> list[dict]:
    """Sender side: one record per recipient plus one with key_remote_jid='broadcast', all with the same
    key_id and needs_push=2."""
    groups: dict[str, list[Message]] = {}
    for m in messages:
        if m.from_me and m.needs_push == 2:
            groups.setdefault(m.key_id, []).append(m)
    out = []
    for key_id, ms in groups.items():
        recips = sorted(m.remote_jid for m in ms if m.remote_jid != BROADCAST_JID)
        declared = {m.recipient_count for m in ms}
        listed = set()
        for m in ms:
            listed.update(x for x in (m.remote_resource or "").split(",") if x)
        out.append({"key_id": key_id, "recipients": recips, "has_self_record": any(
                        m.remote_jid == BROADCAST_JID for m in ms),
                    "recipient_count": declared.pop() if len(declared) == 1 else sorted(declared),
                    "remote_resource_list": sorted(listed), "text": ms[0].data,
                    "sent_at": iso(ms[0].time)})
    return out


def broadcasts_received(messages: list[Message]) -> list[dict]:
    """Recipient side: a single record whose key_id is '%' + the sender's id."""
    return [{"key_id": m.key_id, "sender_key_id": m.norm_key_id, "from": m.remote_jid, "text": m.data,
             "received_at": iso(m.time)} for m in messages if not m.from_me and m.is_broadcast_copy]


def parse_group_id(gid: str) -> dict:
    """<creator phone>-<creation epoch>@g.us"""
    m = re.match(r"^(?P<creator>[^-@]+)-(?P<epoch>\d+)@g\.us$", gid)
    if not m:
        raise ValueError(f"not a group id: {gid!r}")
    return {"creator": m.group("creator"), "created_at": from_s(int(m.group("epoch")))}


@dataclass
class ControlEvent:
    group: str
    op: str
    user: str | None
    time: object
    name: str | None = None


def group_control_events(messages: list[Message]) -> dict[str, list[ControlEvent]]:
    """Control messages: status=6, media_size 1=create 4=join 5=leave (user in remote_resource)."""
    out: dict[str, list[ControlEvent]] = {}
    for m in messages:
        if m.status == 6 and m.is_group and m.media_size in CONTROL_OPS:
            out.setdefault(m.remote_jid, []).append(
                ControlEvent(m.remote_jid, CONTROL_OPS[m.media_size], m.remote_resource, from_ms(m.timestamp),
                             m.data if m.media_size == 1 else None))
    for v in out.values():
        v.sort(key=lambda e: e.time)
    return out


def members_at(events: list[ControlEvent], at) -> set[str]:
    """Group composition at time `at`, from the control-message timeline (Fig 12)."""
    members: set[str] = set()
    for e in events:
        if e.time > at:
            break
        if e.op in ("create", "join") and e.user:
            members.add(e.user)
        elif e.op == "leave":
            members.discard(e.user)
    return members


def group_timeline(events: list[ControlEvent]) -> list[dict]:
    return [{"time": iso(e.time), "op": e.op, "user": e.user, "name": e.name} for e in events]


def group_messages(messages: list[Message], owner_jid: str | None = None) -> list[dict]:
    """Ordinary group messages. Outgoing ones: key_from_me=1, status=4 (or 5), remote_resource NULL.
    Group membership at send time gives the possible recipients."""
    ctrl = group_control_events(messages)
    out = []
    for m in messages:
        if not m.is_group or m.status == 6:
            continue
        sender = owner_jid if m.from_me else m.remote_resource
        when = from_ms(m.timestamp)
        members = members_at(ctrl.get(m.remote_jid, []), when)
        out.append({"group": m.remote_jid, "key_id": m.key_id, "sender": sender or "(device owner)",
                    "text": m.data, "time": iso(when), "members_at_time": sorted(members),
                    "sender_was_member": (sender in members) if sender else None})
    return sorted(out, key=lambda x: x["time"])


def group_events_from_logs(events: list[Event]) -> list[dict]:
    """Sec. 4.2.6: group evolution reconstructed from log events (survives deletion of messages)."""
    out = []
    for e in events:
        f = e.fields
        if e.kind == "group_created":
            out.append({"time": e.ts, "op": "create", "group": f["gid"], "name": f["name"],
                        "created_at": from_ms(int(f["created_ms"]))})
        elif e.kind == "group_add":
            out.append({"time": e.ts, "op": "join", "group": f["gid"], "user": f["jid"]})
        elif e.kind == "group_remove":
            out.append({"time": e.ts, "op": "leave", "group": f["gid"], "user": f["jid"],
                        "removed_by": None if f["removed_by"] == "null" else f["removed_by"]})
    return out
