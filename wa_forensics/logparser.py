"""Parser for whatsapp.log / whatsapp-<date>.log (formats from Figs 1, 2, 13, 14, 15 of the paper).

A log record starts with `YYYY-MM-DD HH:MM:SS.mmm L: [thread] text`; the thread tag is optional.
Wrapped continuation lines are indented and belong to the previous record. `[...]` marks an
elision in the paper's figures and is ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .timeutil import parse_log_ts

JID = r"[\w.+\-]+@(?:s\.whatsapp\.net|g\.us)"
GID = r"[\w.+\-]+@g\.us"

_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) ([A-Z]): (?:\[(\d+)\] )?(.*)$")


@dataclass
class Event:
    ts: datetime
    level: str
    thread: str | None
    text: str          # continuation lines already joined with single spaces
    source: str = ""
    kind: str = "other"
    fields: dict = field(default_factory=dict)


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


_RULES: list[tuple[str, re.Pattern]] = [
    ("contact_lookup", re.compile(rf"^found 0 similar contacts to row_id=(?P<row_id>\d+) jid=(?P<jid>{JID})")),
    ("contact_photo_updated", re.compile(
        rf"^updated photo id for contact jid=(?P<jid>{JID}) photo_id_timestamp=(?P<photo_id_timestamp>\d+) "
        r"thumb_ts=(?P<thumb_ts>\d+)")),
    ("block_add", re.compile(rf"^xmpp/reader/read/blocklist/add (?P<jid>{JID})")),
    ("unblock", re.compile(r"^xmpp/writer/write/blocklist(?: |$)")),
    ("msg_delete", re.compile(r"^msgstore/delete (?P<key_id>\S+)$")),
    ("msg_send", re.compile(rf"^msgstore/add/send (?P<jid>{JID}) (?P<key_id>\S+) (?P<flag>\d+)$")),
    # ASSUMPTION: the paper never shows the receive-side event; see docs/deviations.md D-07.
    ("msg_receive", re.compile(rf"^msgstore/add/receive (?P<jid>{JID}) (?P<key_id>\S+) (?P<flag>\d+)$")),
    ("receipt_server", re.compile(rf"^xmpp/reader/read/message/receipt/server (?P<jid>{JID}) (?P<key_id>\S+)$")),
    ("receipt_device", re.compile(rf"^xmpp/reader/read/message/receipt/device (?P<jid>{JID}) (?P<key_id>\S+)$")),
    ("group_create_request", re.compile(r"^newgroup/go create group: (?P<creator>[\w.+]+)-(?P<name>.+)@temp$")),
    ("group_created", re.compile(
        rf"^groupmgr/onGroupCreated/gid: (?P<gid>{GID})/(?P<name>.*)/(?P<created_ms>\d+)$")),
    ("group_add_request", re.compile(
        rf"^xmpp/writer/write/req-add-participants (?P<gid>{GID}) \| \[(?P<jids>[^\]]*)\]$")),
    ("group_add", re.compile(rf"^groupmgr/onGroupAddUser/jid: (?P<jid>{JID})/gid:(?P<gid>{GID})$")),
    ("group_remove", re.compile(
        rf"^groupmgr/onGroupRemoveUser/jid: (?P<jid>{JID})/gid:(?P<gid>{GID})/ ?removed_by:(?P<removed_by>\S+)$")),
]


def classify(ev: Event) -> Event:
    for kind, pat in _RULES:
        m = pat.search(ev.text)
        if m:
            ev.kind = kind
            ev.fields = m.groupdict()
            break
    return ev


def parse_text(text: str, source: str = "") -> list[Event]:
    events: list[Event] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = _LINE.match(raw.lstrip("\ufeff"))
        if m:
            events.append(Event(parse_log_ts(m.group(1)), m.group(2), m.group(3), m.group(4), source))
        elif raw.strip() == "[...]":
            continue
        elif events:
            events[-1].text += " " + raw.strip()
    for e in events:
        e.text = _norm(e.text)
        classify(e)
    return events


def parse_file(path: str | Path) -> list[Event]:
    p = Path(path)
    return parse_text(p.read_text(encoding="utf-8", errors="replace"), p.name)


def load_logs(log_dir: str | Path) -> list[Event]:
    """All whatsapp*.log files in a directory, merged chronologically (stable)."""
    d = Path(log_dir)
    events: list[Event] = []
    if d.is_dir():
        for f in sorted(d.glob("whatsapp*.log")):
            events.extend(parse_file(f))
    events.sort(key=lambda e: e.ts)
    return events
