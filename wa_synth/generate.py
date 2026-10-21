"""Synthetic WhatsApp-2.11-on-Android artifact generator.

Builds two fictitious devices ("alice" = device under analysis, "bob" = a communication partner) as extracted
file trees laid out like Table 1 of the paper, plus a ground-truth manifest for each. EVERYTHING IS SYNTHETIC:
phone numbers are in the fictional NANP 202-555-01xx range and all content is invented.

Independence rule: ground truth is computed from the scenario variables in this file, never by calling the
parsers in `wa_forensics`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from wa_forensics.backups import PAPER_KEY, encrypt_backup


# ---------------------------------------------------------------------------------------------------------
# helpers
def T(s: str) -> int:
    """'YYYY-MM-DD HH:MM:SS[.mmm]' (UTC) -> epoch ms."""
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in s else "%Y-%m-%d %H:%M:%S"
    return round(datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp() * 1000)


def fmt(ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ms // 1000)) + f".{ms % 1000:03d} UTC"


def num(i: int) -> str:
    return f"120255501{i:02d}"      # 1-202-555-01xx: reserved for fiction


def jid(n: str) -> str:
    return f"{n}@s.whatsapp.net"


ALICE, BOB, CAROL, DAVE, ERIN, FRANK, GRACE, HEIDI, EVE = (num(i) for i in range(1, 10))
SIM_OTHER = num(99)

DATA = "data/data/com.whatsapp"
SD = "mnt/sdcard/WhatsApp"

WA_CONTACTS = """CREATE TABLE wa_contacts (_id INTEGER PRIMARY KEY AUTOINCREMENT, jid TEXT, is_whatsapp_user INTEGER,
 unseen_msg_count INTEGER, photo_ts INTEGER, thumb_ts INTEGER, photo_id_timestamp INTEGER, wa_name TEXT, status TEXT,
 sort_name TEXT, number TEXT, raw_contact_id INTEGER, display_name TEXT, phone_type INTEGER, phone_label TEXT,
 given_name TEXT, family_name TEXT)"""
MESSAGES = """CREATE TABLE messages (_id INTEGER PRIMARY KEY AUTOINCREMENT, key_remote_jid TEXT NOT NULL,
 key_from_me INTEGER, key_id TEXT NOT NULL, status INTEGER, needs_push INTEGER, data TEXT, timestamp INTEGER,
 media_url TEXT, media_mime_type TEXT, media_wa_type INTEGER DEFAULT 0, media_size INTEGER, media_name TEXT,
 latitude REAL, longitude REAL, thumb_image TEXT, remote_resource TEXT, received_timestamp INTEGER,
 send_timestamp INTEGER, receipt_server_timestamp INTEGER, receipt_device_timestamp INTEGER, raw_data BLOB,
 media_hash TEXT, recipient_count INTEGER, media_duration INTEGER)"""
CHAT_LIST = "CREATE TABLE chat_list (_id INTEGER PRIMARY KEY AUTOINCREMENT, key_remote_jid TEXT UNIQUE, message_table_id INTEGER)"


def fake_bytes(seed: str, n: int, head: bytes = b"", tail: bytes = b"") -> bytes:
    rng = random.Random(seed)
    body = bytes(rng.getrandbits(8) for _ in range(n - len(head) - len(tail)))
    return head + body + tail


def b64sha(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def server_name(data: bytes, ext: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=") + ext


class Log:
    def __init__(self):
        self.ev: list[tuple[int, str, str | None, list[str]]] = []

    def add(self, ts: int, *lines: str, level: str = "I", thread: str | None = None):
        self.ev.append((ts, level, thread, list(lines)))

    def write(self, logdir: Path, purged_dates: set[str] = frozenset()) -> list[str]:
        logdir.mkdir(parents=True, exist_ok=True)
        by_date: dict[str, list] = defaultdict(list)
        for e in sorted(self.ev, key=lambda e: e[0]):
            by_date[time.strftime("%Y-%m-%d", time.gmtime(e[0] // 1000))].append(e)
        dates = sorted(by_date)
        written = []
        for d in dates:
            if d in purged_dates:
                continue
            name = "whatsapp.log" if d == dates[-1] else f"whatsapp-{d}.log"
            out = []
            for ts, lvl, thr, lines in by_date[d]:
                stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts // 1000)) + f".{ts % 1000:03d}"
                out.append(f"{stamp} {lvl}: " + (f"[{thr}] " if thr else "") + lines[0])
                out += [" " * 33 + ln for ln in lines[1:]]
            (logdir / name).write_text("\n".join(out) + "\n", encoding="utf-8")
            written.append(name)
        return written

    # -- event templates (formats from Figs 1, 2, 13, 14, 15) -----------------------------------------
    def contact_add(self, ts: int, n: str, row_id: int, thumb_ts_s: int):
        j = jid(n)
        self.add(ts, "contactpicker/create", thread="1")
        self.add(ts + 1, "1 contacts selected for picker", "(is_broadcast=false) | time: 1", thread="1")
        self.add(ts + 40, f"found 0 similar contacts to row_id={row_id}", f"jid={j}",
                 f"key=1-{n[1:]} phone=2 iswa=true | time: 0", thread="89")
        self.add(ts + 41, "app/sendGetProfilePhoto photo_id:0 type:2", f"jid:{j}", thread="89")
        self.add(ts + 182, "xmpp/reader/read/profilephotoreceived", f"{j} id:{thumb_ts_s}",
                 "type:preview has_data:true", thread="82")
        self.add(ts + 183, "contact fetched by jid=" + j, f"result=row_id={row_id} jid={j}",
                 f"key=1-{n[1:]} phone=2 iswa=true count=1 | time: 1", thread="1")
        self.add(ts + 203, "updated photo id for contact", f"jid={j}",
                 f"photo_id_timestamp={ts + 203} thumb_ts={thumb_ts_s}", "photo_ts=0 | time: 20", thread="67")
        return ts + 203   # photo_id_timestamp value

    def block(self, ts: int, n: str):
        self.add(ts, "xmpp/reader/read/blocklist/add", jid(n), thread="90")

    def unblock(self, ts: int):
        self.add(ts, "xmpp/writer/write/blocklist", thread="87")
        self.add(ts + 262, "general_request_success/3", thread="90")

    def send(self, ts: int, to: str, key: str, server: int | None, device: int | None):
        self.add(ts, f"msgstore/add/send {jid(to)}", f"{key} 0")
        self.add(ts + 27, f"xmpp/writer/write/message {jid(to)}", f"{key} | time: 1")
        if server:
            self.add(server, "xmpp/reader/read/message/receipt/server", f"{jid(to)} {key}")
        if device:
            self.add(device, "xmpp/reader/read/message/receipt/device", f"{jid(to)} {key}")

    def receive(self, ts: int, frm: str, key: str):
        self.add(ts, f"msgstore/add/receive {jid(frm)}", f"{key} 0")

    def delete(self, ts: int, key: str):
        self.add(ts, f"msgstore/delete {key}")


class MsgDb:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(MESSAGES)
        self.con.execute(CHAT_LIST)

    def add(self, remote: str, from_me: bool, key: str, ts: int, data=None, status=None, recv=None, server=-1,
            device=-1, wa_type=0, needs_push=0, recipient_count=None, resource=None, **media) -> int:
        if status is None:
            status = 0
        if recv is None:
            recv = ts + 20 if from_me else ts + 2000
        cur = self.con.execute(
            """INSERT INTO messages (key_remote_jid,key_from_me,key_id,status,needs_push,data,timestamp,media_url,
            media_mime_type,media_wa_type,media_size,media_name,latitude,longitude,remote_resource,received_timestamp,
            send_timestamp,receipt_server_timestamp,receipt_device_timestamp,raw_data,media_hash,recipient_count,
            media_duration) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (remote, int(from_me), key, status, needs_push, data, ts, media.get("url"), media.get("mime"), wa_type,
             media.get("size"), media.get("name"), media.get("lat"), media.get("lon"), resource, recv, -1,
             server if from_me else -1, device if from_me else -1, media.get("raw"), media.get("hash"),
             recipient_count, media.get("duration")))
        return cur.lastrowid

    def delete_key(self, key: str):
        self.con.execute("DELETE FROM messages WHERE key_id=?", (key,))

    def delete_conversation(self, remote: str):
        self.con.execute("DELETE FROM messages WHERE key_remote_jid=?", (remote,))

    def rebuild_chat_list(self):
        self.con.execute("DELETE FROM chat_list")
        self.con.execute("INSERT INTO chat_list (key_remote_jid,message_table_id) SELECT key_remote_jid, MAX(_id) "
                         "FROM messages WHERE key_remote_jid<>'broadcast' GROUP BY key_remote_jid ORDER BY MAX(_id)")
        self.con.commit()

    def snapshot(self) -> bytes:
        self.rebuild_chat_list()
        self.con.commit()
        self.con.execute("VACUUM")
        return self.con.serialize()


def write_wa_db(path: Path, contacts: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(":memory:")
    con.execute(WA_CONTACTS)
    con.execute("CREATE TABLE android_metadata (locale TEXT)")
    con.execute("INSERT INTO android_metadata VALUES ('en_US')")
    for c in contacts:
        con.execute("INSERT INTO wa_contacts (jid,is_whatsapp_user,unseen_msg_count,photo_ts,thumb_ts,"
                    "photo_id_timestamp,wa_name,status,sort_name,number,raw_contact_id,display_name,phone_type,"
                    "phone_label,given_name,family_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (c["jid"], c["wa"], 0, 0, c.get("thumb_ts", 0), c.get("photo_id", 0), c.get("wa_name"),
                     c.get("status"), c["name"], c["number"], c["raw"], c["name"], 2, "mobile", c["name"], ""))
    con.commit()
    path.write_bytes(con.serialize())


def put(root: Path, rel: str, data: bytes | str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode() if isinstance(data, str) else data)


# ---------------------------------------------------------------------------------------------------------
def build_corpus(out: Path) -> dict[str, dict]:
    """Create corpus/<device>/fs/... and corpus/<device>/ground_truth.json. Returns {device: {'fs','truth'}}."""
    out = Path(out)
    A, B = out / "alice" / "fs", out / "bob" / "fs"
    for d in (A, B):
        if d.exists():
            raise FileExistsError(f"{d} exists; refusing to overwrite")
    la, lb = Log(), Log()
    adb, bdb = MsgDb(), MsgDb()
    truth_a: dict = {}
    truth_b: dict = {}

    # ---- contacts (alice) --------------------------------------------------------------------------
    adds = {CAROL: T("2012-02-13 06:58:30.000"), BOB: T("2013-09-25 14:14:24.161"), DAVE: T("2013-09-25 14:20:10.000"),
            ERIN: T("2013-09-25 14:21:00.000"), FRANK: T("2013-09-25 14:22:00.000"),
            HEIDI: T("2013-09-25 14:23:00.000"), EVE: T("2013-09-20 12:00:00.000")}
    names = {BOB: "Bob Test", CAROL: "Carol Test", DAVE: "Dave Test", ERIN: "Erin Test", FRANK: "Frank Test",
             HEIDI: "Heidi Test", GRACE: "Grace Phonebook", EVE: "Eve Test"}
    photo_id: dict[str, int] = {}
    for row, (n, t) in enumerate(adds.items(), start=1):
        photo_id[n] = la.contact_add(t, n, row, t // 1000 - 5)
    a_contacts = []
    for row, n in enumerate([BOB, CAROL, DAVE, ERIN, FRANK, HEIDI, GRACE], start=1):
        wa = n != GRACE
        a_contacts.append({"jid": jid(n), "wa": int(wa), "name": names[n], "number": "+" + n, "raw": row,
                           "wa_name": names[n].split()[0] if wa else None, "status": "Hey there!" if wa else None,
                           "thumb_ts": adds[n] // 1000 - 5 if wa else 0, "photo_id": photo_id[n] if wa else 0})
    final_contacts = [c for c in a_contacts if c["jid"] != jid(DAVE)]        # Dave deleted by the user
    truth_a["contacts_in_db"] = sorted(c["jid"] for c in final_contacts)
    truth_a["non_whatsapp_contacts"] = [jid(GRACE)]
    # 'added' = the "found 0 similar contacts" event (ts+40 ms); avatar done = "updated photo id" event (ts+203 ms)
    truth_a["contact_added"] = {jid(n): fmt(adds[n] + 40) for n in (CAROL, BOB, DAVE, ERIN, FRANK, HEIDI)}
    truth_a["contact_avatar_done"] = {jid(n): fmt(adds[n] + 203) for n in (CAROL, BOB, DAVE, ERIN, FRANK, HEIDI)}
    truth_a["deleted_contacts_from_logs"] = [jid(DAVE)]
    truth_a["deleted_contacts_not_detectable_from_logs"] = [jid(EVE)]   # their log file was purged
    truth_a["orphan_avatars"] = sorted([jid(DAVE), jid(EVE)])

    # ---- blocking (alice) -----------------------------------------------------------------------
    la.block(T("2013-09-27 16:25:09.487"), ERIN)
    la.block(T("2013-09-27 16:30:00.100"), FRANK)
    la.unblock(T("2013-09-27 16:38:42.313"))         # cumulative: does not say who
    la.block(T("2013-10-03 09:00:00.500"), HEIDI)
    truth_a["blocks"] = {jid(ERIN): "INDETERMINATE", jid(FRANK): "INDETERMINATE", jid(HEIDI): "BLOCKED"}
    truth_a["block_times"] = {jid(ERIN): fmt(T("2013-09-27 16:25:09.487")), jid(FRANK): fmt(T("2013-09-27 16:30:00.100")),
                              jid(HEIDI): fmt(T("2013-10-03 09:00:00.500"))}
    # bob blocks then unblocks a single contact -> unambiguous
    lb.block(T("2013-10-02 10:00:00.000"), CAROL)
    lb.unblock(T("2013-10-02 10:05:00.000"))
    lb.block(T("2013-10-04 08:00:00.000"), ERIN)
    truth_b = {"blocks": {jid(CAROL): "UNBLOCKED", jid(ERIN): "BLOCKED"}}

    # ---- Fig-3 replay: 1-to-1 chronology with carol -------------------------------------------------
    adb.add(jid(CAROL), False, "1329115800-1", 1329116347000, "Message 1", recv=1329116349643)
    adb.add(jid(CAROL), True, "1329116349-1", 1329116423505, "Reply 1", status=5, recv=1329116423532,
            server=1329116423900, device=1329116424200)
    adb.add(jid(CAROL), False, "1329115800-2", 1329116791000, "Message 2", recv=1329116793357)
    adb.add(jid(CAROL), True, "1329116349-2", 1329116941607, "Reply 2", status=5, recv=1329116941626,
            server=1329116941900, device=1329116942100)
    truth_a["chat_carol_2012"] = [
        {"key_id": "1329115800-1", "dir": "in", "text": "Message 1", "time": "2012-02-13 06:59:09.643 UTC"},
        {"key_id": "1329116349-1", "dir": "out", "text": "Reply 1", "time": "2012-02-13 07:00:23.505 UTC"},
        {"key_id": "1329115800-2", "dir": "in", "text": "Message 2", "time": "2012-02-13 07:06:33.357 UTC"},
        {"key_id": "1329116349-2", "dir": "out", "text": "Reply 2", "time": "2012-02-13 07:09:01.607 UTC"}]

    # ---- deleted messages (Figs 13/14) ---------------------------------------------------------------
    t_d1 = T("2013-03-14 09:37:44.621")
    adb.add(jid(CAROL), True, "1363253484-1", t_d1, "D1: sent, delivered, later deleted", status=5,
            server=T("2013-03-14 09:37:44.887"), device=T("2013-03-14 09:37:45.190"))
    la.send(t_d1, CAROL, "1363253484-1", T("2013-03-14 09:37:44.887"), T("2013-03-14 09:37:45.190"))
    adb.add(jid(CAROL), False, "1363250000-3", T("2013-03-14 09:40:00.000"), "M0: stays in the live db",
            recv=T("2013-03-14 09:40:00.250"))
    la.receive(T("2013-03-14 09:40:00.250"), CAROL, "1363250000-3")
    snap_before = T("2013-03-14 10:00:00.000")          # time of the first backup
    backup1 = adb.snapshot()                            # contains Fig-3 msgs, D1, M0
    t_d2 = T("2013-03-14 10:10:00.000")
    adb.add(jid(CAROL), False, "1363250000-7", t_d2, "D2: received after the backup, later deleted", recv=t_d2 + 300)
    la.receive(t_d2 + 300, CAROL, "1363250000-7")
    la.delete(T("2013-03-14 10:49:22.737"), "1363253484-1")
    la.delete(T("2013-03-14 10:49:30.100"), "1363250000-7")
    adb.delete_key("1363253484-1")
    adb.delete_key("1363250000-7")
    truth_a["deleted_messages"] = {
        "1363253484-1": {"deleted_at": "2013-03-14 10:49:22.737 UTC", "direction": "out", "partner": jid(CAROL),
                         "exchanged_at": "2013-03-14 09:37:44.621 UTC", "server_ack_at": "2013-03-14 09:37:44.887 UTC",
                         "delivered_at": "2013-03-14 09:37:45.190 UTC", "state": "DELIVERED",
                         "in_backup": "msgstore-2013-03-14.crypt", "content": "D1: sent, delivered, later deleted"},
        "1363250000-7": {"deleted_at": "2013-03-14 10:49:30.100 UTC", "direction": "in", "partner": jid(CAROL),
                         "exchanged_at": "2013-03-14 10:10:00.300 UTC", "server_ack_at": None, "delivered_at": None,
                         "state": "RECEIVED", "in_backup": None, "content": None}}

    # ---- whole conversation deleted (heidi) ----------------------------------------------------------
    adb.add(jid(HEIDI), True, "1380700000-1", T("2013-10-02 11:00:00.000"), "Hi Heidi", status=5,
            server=T("2013-10-02 11:00:00.400"), device=T("2013-10-02 11:00:01.100"))
    la.send(T("2013-10-02 11:00:00.000"), HEIDI, "1380700000-1", T("2013-10-02 11:00:00.400"), T("2013-10-02 11:00:01.100"))
    adb.add(jid(HEIDI), False, "1380700100-3", T("2013-10-02 11:01:00.000"), "Hi back", recv=T("2013-10-02 11:01:00.500"))
    la.receive(T("2013-10-02 11:01:00.500"), HEIDI, "1380700100-3")
    la.delete(T("2013-10-02 12:00:00.000"), "1380700000-1")
    la.delete(T("2013-10-02 12:00:00.010"), "1380700100-3")
    adb.delete_conversation(jid(HEIDI))
    truth_a["deleted_conversation"] = {"partner": jid(HEIDI), "keys": ["1380700000-1", "1380700100-3"]}
    truth_a["deleted_messages"]["1380700000-1"] = {
        "deleted_at": "2013-10-02 12:00:00.000 UTC", "direction": "out", "partner": jid(HEIDI),
        "exchanged_at": "2013-10-02 11:00:00.000 UTC", "server_ack_at": "2013-10-02 11:00:00.400 UTC",
        "delivered_at": "2013-10-02 11:00:01.100 UTC", "state": "DELIVERED", "in_backup": None, "content": None}
    truth_a["deleted_messages"]["1380700100-3"] = {
        "deleted_at": "2013-10-02 12:00:00.010 UTC", "direction": "in", "partner": jid(HEIDI),
        "exchanged_at": "2013-10-02 11:01:00.500 UTC", "server_ack_at": None, "delivered_at": None,
        "state": "RECEIVED", "in_backup": None, "content": None}

    # ---- message states (Fig 8) ----------------------------------------------------------------------
    s1 = 1381932937884
    adb.add(jid(CAROL), True, "1381932918-1", s1, "state test: delivered", status=5, recv=1381932937888,
            server=1381933025551, device=1381933319135)
    adb.add(jid(ERIN), True, "1381932918-2", T("2013-10-16 14:16:00.000"), "state test: on server only", status=4,
            recv=T("2013-10-16 14:16:00.004"), server=T("2013-10-16 14:17:05.600"))
    adb.add(jid(FRANK), True, "1381932918-3", T("2013-10-16 14:16:30.000"), "state test: not yet sent", status=0,
            recv=T("2013-10-16 14:16:30.003"))
    truth_a["states"] = {
        "1381932918-1": {"state": "DELIVERED", "created_at": "2013-10-16 14:15:37.884 UTC",
                         "server_ack_at": "2013-10-16 14:17:05.551 UTC", "delivered_at": "2013-10-16 14:21:59.135 UTC",
                         "waited_for_server_s": 87.667, "server_to_recipient_s": 293.584},
        "1381932918-2": {"state": "ON_SERVER_NOT_DELIVERED", "delivered_at": None},
        "1381932918-3": {"state": "NOT_YET_SENT_TO_SERVER", "server_ack_at": None}}

    # ---- media / vcard / geo, alice -> bob -----------------------------------------------------------
    img = fake_bytes("img1", 40267, b"\xff\xd8\xff\xe0SYNTHETIC-PLACEHOLDER", b"\xff\xd9")
    img2 = fake_bytes("img2", 12000, b"\xff\xd8\xff\xe0SYNTHETIC-PLACEHOLDER", b"\xff\xd9")
    sname, sname2 = server_name(img, ".jpg"), server_name(img2, ".jpg")
    thumb = fake_bytes("thumb", 300, b"THUMB")
    t_img = T("2013-10-17 10:05:00.000")
    common = dict(mime="image/jpeg", size=len(img), hash=b64sha(img), raw=thumb)
    adb.add(jid(BOB), True, "1382000000-1", t_img, None, status=5, wa_type=1, server=t_img + 700, device=t_img + 2100,
            url=f"https://mms834.whatsapp.net/d/{sname}", name="IMG-20131017-WA0000.jpg", **common)
    bdb.add(jid(ALICE), False, "1382000000-1", t_img, None, wa_type=1, recv=t_img + 2000,
            url=f"https://mms834.whatsapp.net/d/Zm9vYmFyU3ludGg/{sname}", name=None, **common)
    t_img2 = T("2013-10-17 10:06:00.000")
    common2 = dict(mime="image/jpeg", size=len(img2), hash=b64sha(img2), raw=thumb)
    adb.add(jid(BOB), True, "1382000000-4", t_img2, None, status=5, wa_type=1, server=t_img2 + 700, device=t_img2 + 2100,
            url=f"https://mms834.whatsapp.net/d/{sname2}", name="IMG-20131017-WA0001.jpg", **common2)
    bdb.add(jid(ALICE), False, "1382000000-4", t_img2, None, wa_type=1, recv=t_img2 + 2000,
            url=f"https://mms834.whatsapp.net/d/Zm9vYmFyU3ludGg/{sname2}", name=None, **common2)
    put(A, f"{SD}/Media/Sent/IMG-20131017-WA0000.jpg", img)
    put(A, f"{SD}/Media/Sent/IMG-20131017-WA0001.jpg", img2)
    put(B, f"{SD}/Media/IMG-20131017-WA0003.jpg", img)            # bob downloaded only the first image
    vc = "BEGIN:VCARD\nVERSION:3.0\nN:;Alex Sample;;;\nFN:Alex Sample\nTEL;type=CELL:+12025550150\nEND:VCARD"
    t_vc = T("2013-10-17 10:07:00.000")
    adb.add(jid(BOB), True, "1382000000-2", t_vc, vc, status=5, wa_type=4, server=t_vc + 500, device=t_vc + 900,
            name="Alex Sample", raw=b"")
    bdb.add(jid(ALICE), False, "1382000000-2", t_vc, vc, wa_type=4, recv=t_vc + 1000, name="Alex Sample")
    t_geo = T("2013-10-17 10:08:00.000")
    geo_thumb = fake_bytes("geo", 200, b"MAPTHUMB")
    adb.add(jid(BOB), True, "1382000000-3", t_geo, None, status=5, wa_type=5, server=t_geo + 500, device=t_geo + 900,
            lat=51.5007, lon=-0.1246, raw=geo_thumb)
    bdb.add(jid(ALICE), False, "1382000000-3", t_geo, None, wa_type=5, recv=t_geo + 1000, lat=51.5007, lon=-0.1246,
            raw=geo_thumb)
    truth_a["media"] = {"1382000000-1": {"media_name": "IMG-20131017-WA0000.jpg", "server_filename": sname,
                                         "matched_file": "IMG-20131017-WA0000.jpg", "size": len(img)},
                        "1382000000-4": {"media_name": "IMG-20131017-WA0001.jpg", "server_filename": sname2,
                                         "matched_file": "IMG-20131017-WA0001.jpg", "size": len(img2)}}
    truth_b["media"] = {"1382000000-1": {"media_name": None, "server_filename": sname,
                                         "matched_file": "IMG-20131017-WA0003.jpg", "matched_by": "sha256"},
                        "1382000000-4": {"media_name": None, "server_filename": sname2, "matched_file": None}}
    truth_a["contact_card"] = {"key_id": "1382000000-2", "full_name": "Alex Sample", "phones": ["+12025550150"]}
    truth_a["location"] = {"key_id": "1382000000-3", "latitude": 51.5007, "longitude": -0.1246}
    truth_a["correlated_with_bob"] = ["1382000000-1", "1382000000-2", "1382000000-3", "1382000000-4", "1382694005-1"]

    # ---- broadcast (Fig 9) -------------------------------------------------------------------------------
    t_bc = 1382694005000 + 123
    recips = [BOB, CAROL, DAVE]
    for r in recips + ["broadcast"]:
        adb.add(jid(r) if r != "broadcast" else "broadcast", True, "1382694005-1", t_bc, "Broadcast test", status=5,
                needs_push=2, recipient_count=3, resource=",".join(jid(x) for x in recips),
                server=t_bc + 400, device=t_bc + 1500)
    bdb.add(jid(ALICE), False, "%~1382694005-1", t_bc, "Broadcast test", recv=t_bc + 1600)
    truth_a["broadcast"] = {"key_id": "1382694005-1", "recipients": sorted(jid(x) for x in recips), "count": 3,
                            "sent_at": "2013-10-25 09:40:05.123 UTC"}
    truth_b["broadcast_received"] = {"key_id": "%~1382694005-1", "sender_key_id": "1382694005-1", "from": jid(ALICE)}

    # ---- group (Fig 11, alice = D creator, bob = E, carol = F) -----------------------------------------------
    gid = f"{ALICE}-1384187045@g.us"
    t_c, t_bj, t_cj = 1384187045000, 1384187045970, 1384252848773
    t_cl, t_bl = 1384467096987, 1384508994642
    for key, who, op, t, data in (("1384187045-1", ALICE, 1, t_c, "wa test group"), ("1384187045-2", BOB, 4, t_bj, None),
                                  ("1384252848-1", CAROL, 4, t_cj, None), ("1384467096-1", CAROL, 5, t_cl, None),
                                  ("1384508994-1", BOB, 5, t_bl, None)):
        adb.add(gid, True, key, t, data, status=6, recv=t + 450, resource=jid(who), size=op)
    adb.add(gid, True, "1384243000-1", T("2013-11-12 08:00:00.123"), "Message from Alice", status=4)
    adb.add(gid, False, "1384243100-1", T("2013-11-12 09:00:00.000"), "Message from Bob (before Carol joined)",
            resource=jid(BOB))
    adb.add(gid, False, "1384243200-1", T("2013-11-13 12:00:00.000"), "Message from Carol (member)",
            resource=jid(CAROL))
    adb.add(gid, True, "1384243300-1", T("2013-11-15 12:00:00.500"), "Message from Alice (everyone else left)", status=4)
    gname = "wa test group"
    la.add(1384187044900, f"newgroup/go create group: {ALICE}-{gname}@temp")
    la.add(1384187045146, f"groupmgr/onGroupCreated/gid: {gid}/{gname}/{t_c}", level="W")
    la.add(1384187045204, f"xmpp/writer/write/req-add-participants {gid} |", f"[{jid(BOB)}]", level="E")
    la.add(1384187045453, "groupmgr/onGroupAddUser/jid:", f"{jid(BOB)}/gid:{gid}")
    la.add(1384252848700, f"xmpp/writer/write/req-add-participants {gid} |", f"[{jid(CAROL)}]", level="E")
    la.add(1384252848773, "groupmgr/onGroupAddUser/jid:", f"{jid(CAROL)}/gid:{gid}")
    la.add(1384467096987, "groupmgr/onGroupRemoveUser/jid:", f"{jid(CAROL)}/gid:{gid}/", "removed_by:null")
    la.add(1384508994642, "groupmgr/onGroupRemoveUser/jid:", f"{jid(BOB)}/gid:{gid}/", "removed_by:null")
    truth_a["group"] = {
        "gid": gid, "creator": ALICE, "created_at": "2013-11-11 16:24:05 UTC", "name": gname,
        "timeline": [("2013-11-11 16:24:05.000 UTC", "create", jid(ALICE)), ("2013-11-11 16:24:05.970 UTC", "join", jid(BOB)),
                     ("2013-11-12 10:40:48.773 UTC", "join", jid(CAROL)), ("2013-11-14 22:11:36.987 UTC", "leave", jid(CAROL)),
                     ("2013-11-15 09:49:54.642 UTC", "leave", jid(BOB))],
        "members_at": [("2013-11-11 16:24:05.500 UTC", [jid(ALICE)]),
                       ("2013-11-11 17:00:00.000 UTC", sorted([jid(ALICE), jid(BOB)])),
                       ("2013-11-12 10:40:48.773 UTC", sorted([jid(ALICE), jid(BOB), jid(CAROL)])),
                       ("2013-11-14 22:11:36.987 UTC", sorted([jid(ALICE), jid(BOB)])),
                       ("2013-11-15 09:49:54.642 UTC", [jid(ALICE)])],
        "message_members": {"1384243000-1": sorted([jid(ALICE), jid(BOB)]),
                            "1384243100-1": sorted([jid(ALICE), jid(BOB)]),
                            "1384243200-1": sorted([jid(ALICE), jid(BOB), jid(CAROL)]),
                            "1384243300-1": [jid(ALICE)]}}

    # ---- finish alice's msgstore & backups ---------------------------------------------------------------
    live = adb.snapshot()
    put(A, f"{DATA}/databases/msgstore.db", live)
    put(A, f"{SD}/Databases/msgstore-2013-03-14.crypt", encrypt_backup(backup1, PAPER_KEY))
    put(A, f"{SD}/Databases/msgstore.db.crypt", encrypt_backup(live, PAPER_KEY))
    write_wa_db(A / f"{DATA}/databases/wa.db", final_contacts)
    purged = {time.strftime("%Y-%m-%d", time.gmtime(adds[EVE] // 1000))}
    written = la.write(A / f"{DATA}/files/Logs", purged_dates=purged)
    truth_a["log_files"] = written

    # avatars / settings (alice)
    for n in (BOB, CAROL, DAVE, ERIN, FRANK, HEIDI, EVE):
        put(A, f"{DATA}/files/Avatars/{jid(n)}.j", fake_bytes(f"av{n}", 900, b"AVATAR"))
    for n in (BOB, DAVE):
        put(A, f"{SD}/ProfilePictures/{jid(n)}.j", fake_bytes(f"av{n}", 900, b"AVATAR"))
    put(A, f"{DATA}/files/me", ALICE)
    me_jpg = fake_bytes("me", 700, b"MEJPG")
    put(A, f"{DATA}/files/me.jpg", me_jpg)
    truth_a["identity"] = {"registered_number": ALICE, "sim_number": SIM_OTHER, "sim_mismatch": True,
                           "me_jpg_sha256": hashlib.sha256(me_jpg).hexdigest()}

    # ---- bob ------------------------------------------------------------------------------------------------
    put(B, f"{DATA}/databases/msgstore.db", bdb.snapshot())
    write_wa_db(B / f"{DATA}/databases/wa.db", [
        {"jid": jid(ALICE), "wa": 1, "name": "Alice Test", "number": "+" + ALICE, "raw": 1, "wa_name": "Alice"},
        {"jid": jid(CAROL), "wa": 1, "name": "Carol Test", "number": "+" + CAROL, "raw": 2, "wa_name": "Carol"}])
    lb.write(B / f"{DATA}/files/Logs")
    put(B, f"{DATA}/files/me", BOB)

    # ---- write truth ------------------------------------------------------------------------------------------
    for name, tr in (("alice", truth_a), ("bob", truth_b)):
        (out / name / "ground_truth.json").write_text(json.dumps(tr, indent=2, sort_keys=True), encoding="utf-8")
    return {"alice": {"fs": A, "truth": truth_a}, "bob": {"fs": B, "truth": truth_b}}


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "corpus")
    build_corpus(target)
    print("synthetic corpus written to", target.resolve())
