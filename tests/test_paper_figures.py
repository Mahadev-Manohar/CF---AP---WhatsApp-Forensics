"""Parser tests on the paper's OWN figures, transcribed verbatim from research/paper_figures/ (redactions kept).

These do not depend on the synthetic generator, so they check that the parser understands the log formats the
paper actually printed, and that the derived values equal the values quoted in the paper's text.
"""

import unittest
from datetime import datetime, timezone

from tests import support  # noqa: F401
from wa_forensics import chat, contacts, groups, logparser
from wa_forensics.timeutil import from_ms, from_s, iso

R = "39331XXXXXXX@s.whatsapp.net"

FIG1 = f"""\
2013-09-25 14:14:24.161 I: [1] contactpicker/create
2013-09-25 14:14:24.162 I: [1] 1 contacts selected for picker
                                (is_broadcast=false) | time: 1
2013-09-25 14:14:24.201 I: [89] found 0 similar contacts to row_id=1
                                jid={R}
                                key=1-331XXXXXXX phone=2 iswa=true | time: 0
2013-09-25 14:14:24.201 I: [89] app/sendGetProfilePhoto photo_id:0 type:2
                                jid:{R}
[...]
2013-09-25 14:14:24.343 I: [82] xmpp/reader/read/profilephotoreceived
                                39331XXXXXXX@s.whatsapp.net id:1363544071
                                type:preview has_data:true
[...]
2013-09-25 14:14:24.344 I: [1] contact fetched by jid={R}
                                result=row_id=1 jid={R}
                                key=1-331XXXXXXX phone=2 iswa=true count=1 | time: 1
2013-09-25 14:14:24.364 I: [67] updated photo id for contact
                                jid={R}
                                photo_id_timestamp=1380118464344 thumb_ts=1363544071
                                photo_ts=0 | time: 20
"""

FIG2 = """\
2013-09-27 16:25:09.487 I: [90] xmpp/reader/read/blocklist/add
                                39320XXXXXXX@s.whatsapp.net
2013-09-27 16:38:42.313 I: [87] xmpp/writer/write/blocklist
2013-09-27 16:38:42.575 I: [90] general_request_success/3
"""

FIG13 = """\
[...]
2013-03-14 10:49:22.737 I: msgstore/delete 1363253484-1
"""

FIG14 = """\
2013-03-14 09:37:44.621 I: msgstore/add/send 39366XXXXXXX@s.whatsapp.net
                                1363253484-1 0
2013-03-14 09:37:44.648 I: xmpp/writer/write/message 39366XXXXXXX@s.whatsapp.net
                                1363253484-1 | time: 1
2013-03-14 09:37:44.887 I: xmpp/reader/read/message/receipt/server
                                39366XXXXXXX@s.whatsapp.net 1363253484-1
2013-03-14 09:37:45.190 I: xmpp/reader/read/message/receipt/device
                                39366XXXXXXX@s.whatsapp.net 1363253484-1
"""

FIG15 = """\
2013-03-12 09:02:24.523 I: newgroup/go create group:
                                39333XXXXXXX-prova gruppo@temp
[...]
2013-03-12 09:02:25.146 W: groupmgr/onGroupCreated/gid:
                                39333XXXXXXX-1363078943@g.us/prova gruppo/1363078943000
[...]
2013-03-12 09:02:25.204 E: xmpp/writer/write/req-add-participants 39333XXXXXXX-1363078943@g.us |
                                [39366XXXXXXX@s.whatsapp.net, 39320XXXXXXX@s.whatsapp.net]
[...]
2013-03-12 09:02:25.453 I: groupmgr/onGroupAddUser/jid:
                                39366XXXXXXX@s.whatsapp.net/gid:39333XXXXXXX-1363078943@g.us
2013-03-12 09:02:25.454 I: groupmgr/addParticipantToList:[39333XXXXXXX-1363078943@g.us |
                                39366XXXXXXX@s.whatsapp.net] old pas:
2013-03-12 09:02:25.456 I: msgstore/add/send 39333XXXXXXX-1363078943@g.us 1363079263-5 0
[...]
2013-03-12 09:02:25.459 I: groupmgr/onGroupAddUser/jid:
                                39320XXXXXXX@s.whatsapp.net/gid:39333XXXXXXX-1363078943@g.us
[...]
2013-03-12 09:11:03.875 I: groupmgr/onGroupRemoveUser/jid:
                                39320XXXXXXX@s.whatsapp.net/gid:39333XXXXXXX-1363078943@g.us/
                                removed_by:null
"""


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


class Fig1ContactAdd(unittest.TestCase):
    def test_added_time_matches_paper(self):
        ev = logparser.parse_text(FIG1)
        added = contacts.contact_added_times(ev)
        self.assertEqual(list(added), [R])
        # Paper (Sec. 4.1.2): "on Sept. 25, 2013 at 14:14:24"
        self.assertEqual(added[R]["added_at"].replace(microsecond=0), utc(2013, 9, 25, 14, 14, 24))
        self.assertEqual(iso(added[R]["added_at"]), "2013-09-25 14:14:24.201 UTC")
        self.assertEqual(iso(added[R]["avatar_done_at"]), "2013-09-25 14:14:24.364 UTC")

    def test_photo_timestamps_in_fig1_are_consistent(self):
        # photo_id_timestamp (ms) of the avatar-download event equals the event's own time (+/- clock rounding)
        ev = [e for e in logparser.parse_text(FIG1) if e.kind == "contact_photo_updated"][0]
        self.assertEqual(from_ms(int(ev.fields["photo_id_timestamp"])), utc(2013, 9, 25, 14, 14, 24, 344000))
        self.assertEqual(from_s(int(ev.fields["thumb_ts"])), datetime.fromtimestamp(1363544071, tz=timezone.utc))

    def test_elision_and_continuations(self):
        ev = logparser.parse_text(FIG1)
        self.assertEqual(len(ev), 7)
        self.assertTrue(all("[...]" not in e.text for e in ev))


class Fig2Blocking(unittest.TestCase):
    def test_block_and_cumulative_unblock(self):
        ev = logparser.parse_text(FIG2)
        self.assertEqual([e.kind for e in ev], ["block_add", "unblock", "other"])
        self.assertEqual(ev[0].fields["jid"], "39320XXXXXXX@s.whatsapp.net")
        self.assertNotIn("jid", ev[1].fields)   # the unblock event carries no jid (paper, Sec. 4.1.3)
        st = contacts.block_history(ev)["39320XXXXXXX@s.whatsapp.net"]
        # only one contact was blocked when the unblock event occurred -> definitely unblocked
        self.assertEqual(st["status"], contacts.UNBLOCKED)


class Fig13_14DeletedMessage(unittest.TestCase):
    def test_deleted_message_reconstruction(self):
        from wa_forensics import deleted
        ev = logparser.parse_text(FIG14) + logparser.parse_text(FIG13)
        out = deleted.deleted_from_logs(ev, live=[])
        self.assertEqual(len(out), 1)
        d = out[0]
        self.assertEqual(d["key_id"], "1363253484-1")
        self.assertEqual(d["deleted_at"], "2013-03-14 10:49:22.737 UTC")        # paper: March 14, 2013 10:49:22
        self.assertEqual(d["exchanged_at"], "2013-03-14 09:37:44.621 UTC")      # paper: 09:37:44
        self.assertEqual(d["partner"], "39366XXXXXXX@s.whatsapp.net")
        self.assertEqual(d["state"], "DELIVERED")
        self.assertEqual(d["server_ack_at"], "2013-03-14 09:37:44.887 UTC")
        self.assertEqual(d["delivered_at"], "2013-03-14 09:37:45.190 UTC")


class Fig15Group(unittest.TestCase):
    def test_group_events(self):
        ev = logparser.parse_text(FIG15)
        kinds = [e.kind for e in ev]
        self.assertIn("group_create_request", kinds)
        self.assertIn("group_add_request", kinds)
        created = next(e for e in ev if e.kind == "group_created")
        self.assertEqual(created.fields["name"], "prova gruppo")
        self.assertEqual(from_ms(int(created.fields["created_ms"])), utc(2013, 3, 12, 9, 2, 23))  # paper: 09:02:23
        timeline = groups.group_events_from_logs(ev)
        self.assertEqual([t["op"] for t in timeline], ["create", "join", "join", "leave"])
        self.assertEqual(timeline[-1]["user"], "39320XXXXXXX@s.whatsapp.net")
        self.assertIsNone(timeline[-1]["removed_by"])
        sends = [e for e in ev if e.kind == "msg_send"]
        self.assertEqual(sends[0].fields["key_id"], "1363079263-5")
        req = next(e for e in ev if e.kind == "group_add_request")
        self.assertIn("39366XXXXXXX@s.whatsapp.net", req.fields["jids"])
        self.assertIn("39320XXXXXXX@s.whatsapp.net", req.fields["jids"])

    def test_group_id_decoding(self):
        info = groups.parse_group_id("3933xxxxxxx-1363078943@g.us")
        self.assertEqual(info["creator"], "3933xxxxxxx")
        self.assertEqual(info["created_at"], utc(2013, 3, 12, 9, 2, 23))


class QuotedTimestamps(unittest.TestCase):
    """Epoch values in the paper's record figures vs. the dates printed in its text (all UTC)."""

    def test_fig3_chat(self):
        self.assertEqual(from_ms(1329116349643), utc(2012, 2, 13, 6, 59, 9, 643000))   # paper: "Feb. 13th, 2012 06:59:09"
        self.assertEqual(from_ms(1329116423505).replace(microsecond=0), utc(2012, 2, 13, 7, 0, 23))

    def test_fig8_state_changes(self):
        self.assertEqual(iso(from_ms(1381932937884)), "2013-10-16 14:15:37.884 UTC")
        self.assertEqual(iso(from_ms(1381933025551)), "2013-10-16 14:17:05.551 UTC")
        self.assertEqual(iso(from_ms(1381933319135)), "2013-10-16 14:21:59.135 UTC")

    def test_fig8_message_object(self):
        m = chat.Message(1, "x@s.whatsapp.net", True, "1381932918-1", 5, 1381932937884, 1381932937888,
                         1381933025551, 1381933319135, 0, None, None, 0, "t")
        self.assertEqual(m.state, "DELIVERED")
        tl = m.state_timeline()
        self.assertEqual(tl["created_at"], "2013-10-16 14:15:37.884 UTC")
        self.assertEqual(tl["server_ack_at"], "2013-10-16 14:17:05.551 UTC")
        self.assertEqual(tl["delivered_at"], "2013-10-16 14:21:59.135 UTC")

    def test_fig8_states_a_b_c(self):
        mk = lambda st, srv, dev: chat.Message(1, "x", True, "k", st, 1381932937884, 1381932937888, srv, dev, 0, None,
                                               None, 0, "t")
        self.assertEqual(mk(0, -1, -1).state, "NOT_YET_SENT_TO_SERVER")
        self.assertEqual(mk(4, 1381933025551, -1).state, "ON_SERVER_NOT_DELIVERED")
        self.assertEqual(mk(5, 1381933025551, 1381933319135).state, "DELIVERED")

    def test_fig11_group_times(self):
        for ms, text in ((1384187045000, "2013-11-11 16:24:05.000 UTC"), (1384252848773, "2013-11-12 10:40:48.773 UTC"),
                         (1384467096987, "2013-11-14 22:11:36.987 UTC"), (1384508994642, "2013-11-15 09:49:54.642 UTC")):
            self.assertEqual(iso(from_ms(ms)), text)

    def test_fig11_composition(self):
        # Reproduce Fig 11/12 verbatim: D creates, adds E; adds F; F leaves; E leaves.
        D, E, F = "D", "E", "F"
        mk = lambda row, who, size, ts, data=None: chat.Message(row, "393204-1384187045@g.us", True, f"k{row}", 6, ts, ts,
                                                              -1, -1, 0, None, who, 0, data, media_size=size)
        msgs = [mk(1, D, 1, 1384187045000, "wa test group"), mk(2, E, 4, 1384187045970), mk(3, F, 4, 1384252848773),
                mk(4, F, 5, 1384467096987), mk(5, E, 5, 1384508994642)]
        ctrl = groups.group_control_events(msgs)["393204-1384187045@g.us"]
        self.assertEqual([e.op for e in ctrl], ["create", "join", "join", "leave", "leave"])
        self.assertEqual(groups.members_at(ctrl, from_ms(1384200000000)), {D, E})
        self.assertEqual(groups.members_at(ctrl, from_ms(1384300000000)), {D, E, F})
        self.assertEqual(groups.members_at(ctrl, from_ms(1384500000000)), {D, E})
        self.assertEqual(groups.members_at(ctrl, from_ms(1384600000000)), {D})

    def test_broadcast_key_id_forms(self):
        m = chat.Message(1, "x", False, "%~1382694005-1", 0, 1, 1, -1, -1, 0, None, None, 0, "t")
        self.assertTrue(m.is_broadcast_copy)
        self.assertEqual(m.norm_key_id, "1382694005-1")
        m2 = chat.Message(1, "x", False, "%1382694005-1", 0, 1, 1, -1, -1, 0, None, None, 0, "t")
        self.assertEqual(m2.norm_key_id, "1382694005-1")


if __name__ == "__main__":
    unittest.main()
