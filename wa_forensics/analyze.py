"""End-to-end analysis of one extracted device tree; returns a JSON-serialisable dict."""

from __future__ import annotations

import json
from datetime import datetime

from . import backups, chat, contacts, deleted, groups, logparser, media, settings
from .case import Case
from .timeutil import iso


def _jsonable(o):
    if isinstance(o, datetime):
        return iso(o)
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (bytes, bytearray)):
        return f"<{len(o)} bytes>"
    return o


def analyze(root, sim_number: str | None = None) -> dict:
    case = Case(root)
    ident = settings.registered_identity(case, sim_number)
    events = logparser.load_logs(case.logs_dir) if case.logs_dir else []
    db_contacts = contacts.read_contacts(case)
    live = chat.load_messages_from_file(case.msgstore_db) if case.msgstore_db else []

    bk = {}
    bk_errors = {}
    for p in backups.list_backups(case):
        try:
            bk[p.name] = backups.messages_from_backup(p)
        except ValueError as e:
            bk_errors[p.name] = str(e)

    ctrl = groups.group_control_events(live)
    conv = chat.conversations(live)
    idx = media.index_media_files(case)

    result = {
        "identity": ident,
        "contacts": db_contacts,
        "contact_added": {j: {"added_at": v["added_at"], "avatar_done_at": v["avatar_done_at"]}
                          for j, v in contacts.contact_added_times(events).items()},
        "deleted_contacts_from_logs": contacts.deleted_contacts(db_contacts, events),
        "orphan_avatars": contacts.orphan_avatars(case, db_contacts),
        "blocks": {j: {"status": s["status"], "blocked_at": s["blocked_at"], "unblock_event_at": s["unblock_event_at"]}
                   for j, s in contacts.block_history(events).items()},
        "conversations": {j: [{"key_id": m.key_id, "dir": "out" if m.from_me else "in", "time": iso(m.time),
                               "type": m.type_name, "text": m.data if m.media_wa_type == 0 else None,
                               **m.state_timeline()} for m in ms] for j, ms in conv.items()},
        "chat_list": chat.load_chat_list(case.msgstore_db) if case.msgstore_db else [],
        "media": media.resolve_media(live, idx),
        "contact_cards": media.contact_cards(live),
        "locations": media.locations(live),
        "broadcasts_sent": groups.broadcasts_sent(live),
        "broadcasts_received": groups.broadcasts_received(live),
        "group_timelines": {g: groups.group_timeline(e) for g, e in ctrl.items()},
        "group_info": {g: groups.parse_group_id(g) for g in ctrl},
        "group_messages": groups.group_messages(live, ident["owner_jid"]),
        "group_events_from_logs": groups.group_events_from_logs(events),
        "deleted_messages_from_logs": deleted.deleted_from_logs(events, live),
        "deleted_messages_from_backups": backups.deleted_vs_backups(live, bk),
        "backup_errors": bk_errors,
        "counts": {"live_messages": len(live), "log_events": len(events), "backups": len(bk)},
    }
    return _jsonable(result)


def to_json(result: dict) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)
