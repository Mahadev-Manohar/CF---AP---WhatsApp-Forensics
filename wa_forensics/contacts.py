"""Sec. 4.1: contacts, contact-add times, blocked and deleted contacts."""

from __future__ import annotations

import sqlite3

from .case import Case
from .logparser import Event
from .timeutil import from_ms, from_s, iso


def phone_of(jid: str) -> str:
    return jid.split("@", 1)[0]


def read_contacts(case: Case) -> list[dict]:
    """Sec. 4.1.1: records of wa_contacts (WhatsApp-sourced fields only, per Table 2)."""
    db = case.wa_db
    if db is None:
        return []
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM wa_contacts ORDER BY _id").fetchall()
    finally:
        con.close()
    avatars = {p.name for p in case.avatars_dir.iterdir()} if case.avatars_dir else set()
    out = []
    for r in rows:
        jid = r["jid"]
        out.append({
            "jid": jid,
            "phone": phone_of(jid),
            "is_whatsapp_user": bool(r["is_whatsapp_user"]),
            "wa_name": r["wa_name"],
            "status": r["status"],
            "unseen_msg_count": r["unseen_msg_count"],
            "avatar_set_at": iso(from_s(r["thumb_ts"]), ms=False),          # thumb_ts: 10-digit seconds
            "avatar_downloaded_at": iso(from_ms(r["photo_id_timestamp"])),  # 13-digit ms
            "has_avatar_file": f"{jid}.j" in avatars,
        })
    return out


def contact_added_times(events: list[Event]) -> dict[str, dict]:
    """Sec. 4.1.2: time a contact was added = first 'found 0 similar contacts' event for the jid;
    avatar-download completion is recorded as corroboration."""
    added: dict[str, dict] = {}
    for e in events:
        if e.kind == "contact_lookup":
            added.setdefault(e.fields["jid"], {"added_at": e.ts, "avatar_done_at": None})
    for e in events:
        if e.kind == "contact_photo_updated":
            rec = added.get(e.fields["jid"])
            if rec and rec["avatar_done_at"] is None and e.ts >= rec["added_at"]:
                rec["avatar_done_at"] = e.ts
    return added


def deleted_contacts(db_contacts: list[dict], events: list[Event]) -> list[str]:
    """Sec. 4.1.4: contacts ever added (per logs) that are no longer in wa_contacts.
    Deletion TIME cannot be determined (deletion events carry no jid)."""
    present = {c["jid"] for c in db_contacts}
    return sorted(j for j in contact_added_times(events) if j not in present)


def orphan_avatars(case: Case, db_contacts: list[dict]) -> list[str]:
    """Sec. 4.3: avatar files of contacts that are no longer in wa_contacts (deleting a contact
    record does not delete the avatar), so they still evidence contact."""
    present = {c["jid"] for c in db_contacts}
    found = set()
    for d in (case.avatars_dir, case.profile_pictures_dir):
        if d:
            for p in d.iterdir():
                if p.name.endswith(".j") and p.name[:-2] not in present:
                    found.add(p.name[:-2])
    return sorted(found)


# ---- Sec. 4.1.3 blocked contacts --------------------------------------------------------------

BLOCKED, UNBLOCKED, INDETERMINATE = "BLOCKED", "UNBLOCKED", "INDETERMINATE"


def block_history(events: list[Event], until=None) -> dict[str, dict]:
    """Replay block/unblock log events.

    A block event names the contact; an unblock event does NOT and may be cumulative. So:
    * blocked, no later unblock event                         -> BLOCKED
    * unblock event while exactly one contact could be blocked -> that contact is UNBLOCKED
    * unblock event while several could be blocked             -> INDETERMINATE for those
    """
    state: dict[str, dict] = {}
    for e in sorted(events, key=lambda x: x.ts):
        if until is not None and e.ts > until:
            break
        if e.kind == "block_add":
            state[e.fields["jid"]] = {"status": BLOCKED, "blocked_at": e.ts, "unblock_event_at": None}
        elif e.kind == "unblock":
            cands = [j for j, s in state.items() if s["status"] in (BLOCKED, INDETERMINATE)]
            if len(cands) == 1:
                state[cands[0]].update(status=UNBLOCKED, unblock_event_at=e.ts)
            else:
                for j in cands:
                    state[j].update(status=INDETERMINATE, unblock_event_at=e.ts)
    return state


def blocked_status_at(events: list[Event], jid: str, at) -> str | None:
    """Status of `jid` as of time `at`; None if the logs never show it being blocked by then."""
    s = block_history(events, until=at).get(jid)
    return s["status"] if s else None
