"""Sec. 4.3: settings and preferences (`me`, `me.jpg`)."""

from __future__ import annotations

import hashlib
import re

from .case import Case


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def registered_identity(case: Case, sim_number: str | None = None) -> dict:
    """`me` holds (ASCII) the number WhatsApp was registered with. Comparing it with the SIM currently in the
    phone shows whether the account is used with a different SIM (possible impersonation)."""
    me = case.me_file
    number = digits(me.read_text(encoding="ascii", errors="ignore")) if me else None
    out = {"registered_number": number, "owner_jid": f"{number}@s.whatsapp.net" if number else None,
           "me_jpg_sha256": None, "sim_number": digits(sim_number) if sim_number else None, "sim_mismatch": None}
    jpg = case.me_jpg
    if jpg:
        out["me_jpg_sha256"] = hashlib.sha256(jpg.read_bytes()).hexdigest()
    if sim_number and number:
        out["sim_mismatch"] = digits(sim_number) != number
    return out
