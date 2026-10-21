"""Findings F1-F13: parser output vs. the generator's independently computed ground truth (synthetic data)."""

import unittest

from tests import support
from wa_forensics import backups, chat, groups, media
from wa_forensics.case import Case
from wa_forensics.timeutil import from_ms, iso

C = support.corpus()
TA, TB = C["alice"]["truth"], C["bob"]["truth"]
A, B = support.alice(), support.bob()


class F1_Contacts(unittest.TestCase):
    def test_contact_list(self):
        self.assertEqual(sorted(c["jid"] for c in A["contacts"]), TA["contacts_in_db"])

    def test_non_whatsapp_numbers_flagged(self):
        flagged = [c["jid"] for c in A["contacts"] if not c["is_whatsapp_user"]]
        self.assertEqual(flagged, TA["non_whatsapp_contacts"])

    def test_avatar_files_linked_to_contacts(self):
        """Table 1 rows 4/5: <jid>.j exists for every WhatsApp contact except the non-user number."""
        flags = {c["jid"]: c["has_avatar_file"] for c in A["contacts"]}
        for jid, has in flags.items():
            self.assertEqual(has, jid not in TA["non_whatsapp_contacts"], jid)

    def test_jid_structure(self):
        for c in A["contacts"]:
            self.assertEqual(c["jid"], c["phone"] + "@s.whatsapp.net")

    def test_avatar_timestamps_use_correct_units(self):
        bob = next(c for c in A["contacts"] if c["jid"].startswith("12025550102"))
        self.assertEqual(bob["avatar_downloaded_at"], "2013-09-25 14:14:24.364 UTC")   # 13-digit ms field
        self.assertEqual(bob["avatar_set_at"], "2013-09-25 14:14:19 UTC")              # 10-digit s field


class F2_ContactAddTime(unittest.TestCase):
    def test_added_and_avatar_times(self):
        got = {j: iso_ for j, v in A["contact_added"].items() for iso_ in [v["added_at"]]}
        self.assertEqual(got, TA["contact_added"])
        self.assertEqual({j: v["avatar_done_at"] for j, v in A["contact_added"].items()}, TA["contact_avatar_done"])


class F3_Blocking(unittest.TestCase):
    def test_alice_statuses_and_times(self):
        self.assertEqual({j: v["status"] for j, v in A["blocks"].items()}, TA["blocks"])
        self.assertEqual({j: v["blocked_at"] for j, v in A["blocks"].items()}, TA["block_times"])

    def test_bob_unambiguous_unblock(self):
        self.assertEqual({j: v["status"] for j, v in B["blocks"].items()}, TB["blocks"])

    def test_blocked_at_given_time(self):
        from wa_forensics import contacts, logparser
        ev = logparser.load_logs(Case(C["alice"]["fs"]).logs_dir)
        erin = "12025550105@s.whatsapp.net"
        t = lambda s: from_ms(__import__("wa_synth.generate", fromlist=["T"]).T(s))
        self.assertIsNone(contacts.blocked_status_at(ev, erin, t("2013-09-27 16:00:00")))      # not yet blocked
        self.assertEqual(contacts.blocked_status_at(ev, erin, t("2013-09-27 16:26:00")), "BLOCKED")
        self.assertEqual(contacts.blocked_status_at(ev, erin, t("2013-09-27 16:40:00")), "INDETERMINATE")


class F4_DeletedContacts(unittest.TestCase):
    def test_deleted_contact_recovered_from_logs(self):
        self.assertEqual(A["deleted_contacts_from_logs"], TA["deleted_contacts_from_logs"])

    def test_avatar_of_deleted_contacts_remains(self):
        self.assertEqual(A["orphan_avatars"], TA["orphan_avatars"])

    def test_deleted_contact_with_purged_log_only_found_via_avatar(self):
        eve = TA["deleted_contacts_not_detectable_from_logs"][0]
        self.assertNotIn(eve, A["deleted_contacts_from_logs"])
        self.assertIn(eve, A["orphan_avatars"])


class F5_ChatHistory(unittest.TestCase):
    def test_fig3_style_conversation(self):
        carol = A["conversations"]["12025550103@s.whatsapp.net"]
        got = [{"key_id": m["key_id"], "dir": m["dir"], "text": m["text"], "time": m["time"]} for m in carol
               if m["key_id"] in {t["key_id"] for t in TA["chat_carol_2012"]}]
        self.assertEqual(got, TA["chat_carol_2012"])

    def test_chronological_order(self):
        for jid, msgs in A["conversations"].items():
            self.assertEqual([m["time"] for m in msgs], sorted(m["time"] for m in msgs), jid)

    def test_chat_list_reflects_surviving_conversations(self):
        jids = {r["key_remote_jid"] for r in A["chat_list"]}
        self.assertIn("12025550103@s.whatsapp.net", jids)
        self.assertNotIn("12025550108@s.whatsapp.net", jids)     # conversation deleted -> chat_list row removed
        self.assertNotIn("broadcast", jids)

    def test_sender_recipient_correlation_by_key_id(self):
        a = chat.load_messages_from_file(Case(C["alice"]["fs"]).msgstore_db)
        b = chat.load_messages_from_file(Case(C["bob"]["fs"]).msgstore_db)
        pairs = chat.correlate(a, b)
        self.assertEqual(sorted({s.norm_key_id for s, _ in pairs}), sorted(TA["correlated_with_bob"]))
        for s, r in pairs:
            self.assertTrue(s.from_me and not r.from_me)
            self.assertEqual(s.data, r.data)

    def test_key_id_structure(self):
        self.assertEqual(chat.key_id_parts("1363253484-1"), (1363253484, 1))
        self.assertEqual(chat.key_id_parts("%~1382694005-1"), (1382694005, 1))


class F6_Media(unittest.TestCase):
    def test_sender_side(self):
        rows = {m["key_id"]: m for m in A["media"] if m["direction"] == "out"}
        for key, t in TA["media"].items():
            r = rows[key]
            self.assertEqual(r["media_name"], t["media_name"])
            self.assertEqual(r["server_filename"], t["server_filename"])
            self.assertEqual(r["matched_file"], t["matched_file"])
            self.assertTrue(r["size_matches"])
            self.assertEqual(r["declared_size"], t["size"])

    def test_recipient_side_matched_by_hash_when_name_missing(self):
        rows = {m["key_id"]: m for m in B["media"]}
        r = rows["1382000000-1"]
        self.assertIsNone(r["media_name"])                       # recipient does not store the file name
        self.assertEqual(r["matched_file"], "IMG-20131017-WA0003.jpg")
        self.assertEqual(r["matched_by"], "sha256")
        self.assertEqual(r["server_filename"], TB["media"]["1382000000-1"]["server_filename"])

    def test_not_downloaded_file_is_not_found(self):
        self.assertIsNone({m["key_id"]: m for m in B["media"]}["1382000000-4"]["matched_file"])

    def test_sender_and_recipient_records_correlate(self):
        a = {m.key_id: m for m in chat.load_messages_from_file(Case(C["alice"]["fs"]).msgstore_db)}
        b = {m.key_id: m for m in chat.load_messages_from_file(Case(C["bob"]["fs"]).msgstore_db)}
        c = media.correlate_media(a["1382000000-1"], b["1382000000-1"])
        self.assertTrue(c["same_server_filename"] and c["same_hash"] and c["same_size"])
        self.assertTrue(c["urls_differ_in_host_path"])

    def test_hash_is_base64_sha256(self):
        self.assertEqual(media.media_hash_b64(b""), "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=")


class F7_ContactCardAndLocation(unittest.TestCase):
    def test_vcard(self):
        for side in (A, B):
            c = side["contact_cards"][0]
            self.assertEqual((c["key_id"], c["full_name"], c["phones"], c["name_given_by_sender"]),
                             (TA["contact_card"]["key_id"], "Alex Sample", ["+12025550150"], "Alex Sample"))

    def test_geolocation(self):
        for side in (A, B):
            loc = side["locations"][0]
            self.assertEqual((loc["latitude"], loc["longitude"]), (TA["location"]["latitude"], TA["location"]["longitude"]))
            self.assertTrue(loc["has_map_thumbnail"])


class F8_MessageState(unittest.TestCase):
    def test_three_states_and_timeline(self):
        flat = {m["key_id"]: m for msgs in A["conversations"].values() for m in msgs}
        for key, t in TA["states"].items():
            for field, val in t.items():
                self.assertEqual(flat[key].get(field), val, f"{key}.{field}")


class F9_Broadcast(unittest.TestCase):
    def test_sender_side(self):
        b = A["broadcasts_sent"][0]
        t = TA["broadcast"]
        self.assertEqual((b["key_id"], b["recipients"], b["recipient_count"], b["has_self_record"], b["sent_at"]),
                         (t["key_id"], t["recipients"], t["count"], True, t["sent_at"]))
        self.assertEqual(b["remote_resource_list"], t["recipients"])

    def test_recipient_side(self):
        r = B["broadcasts_received"][0]
        t = TB["broadcast_received"]
        self.assertEqual((r["key_id"], r["sender_key_id"], r["from"]), (t["key_id"], t["sender_key_id"], t["from"]))


class F10_Groups(unittest.TestCase):
    G = TA["group"]

    def test_group_id_decoding(self):
        info = A["group_info"][self.G["gid"]]
        self.assertEqual(info["creator"], self.G["creator"])
        self.assertEqual(info["created_at"][:19], self.G["created_at"][:19])

    def test_timeline(self):
        got = [(e["time"], e["op"], e["user"]) for e in A["group_timelines"][self.G["gid"]]]
        self.assertEqual(got, [tuple(x) for x in self.G["timeline"]])
        self.assertEqual(A["group_timelines"][self.G["gid"]][0]["name"], self.G["name"])

    def test_membership_at_time(self):
        live = chat.load_messages_from_file(Case(C["alice"]["fs"]).msgstore_db)
        ctrl = groups.group_control_events(live)[self.G["gid"]]
        from wa_synth.generate import T
        for when, members in self.G["members_at"]:
            self.assertEqual(sorted(groups.members_at(ctrl, from_ms(T(when[:-4])))), members, when)

    def test_message_sent_while_member(self):
        gm = {m["key_id"]: m for m in A["group_messages"]}
        for key, members in self.G["message_members"].items():
            self.assertEqual(gm[key]["members_at_time"], members, key)
            self.assertTrue(gm[key]["sender_was_member"], key)

    def test_log_events_agree_with_database_timeline(self):
        owner = f"{self.G['creator']}@s.whatsapp.net"
        db_t = [(e["op"], e["user"]) for e in A["group_timelines"][self.G["gid"]]]
        log_t = [(e["op"], owner if e["op"] == "create" else e["user"])      # creator is implicit in the log event
                 for e in A["group_events_from_logs"] if e["group"] == self.G["gid"]]
        self.assertEqual(log_t, db_t)


class F11_DeletedMessagesFromLogs(unittest.TestCase):
    def test_all_deleted_messages_found_with_details(self):
        got = {d["key_id"]: d for d in A["deleted_messages_from_logs"]}
        self.assertEqual(set(got), set(TA["deleted_messages"]))
        for key, t in TA["deleted_messages"].items():
            for field in ("deleted_at", "direction", "partner", "exchanged_at", "server_ack_at", "delivered_at", "state"):
                self.assertEqual(got[key][field], t[field], f"{key}.{field}")
            self.assertFalse(got[key]["still_in_live_db"])
            self.assertFalse(got[key]["content_recoverable_from_logs"])    # the paper: only content is lost

    def test_deleted_messages_absent_from_live_db(self):
        live_keys = {m["key_id"] for msgs in A["conversations"].values() for m in msgs}
        self.assertFalse(live_keys & set(TA["deleted_messages"]))


class F12_Backups(unittest.TestCase):
    def test_backups_decrypt_with_paper_key(self):
        self.assertEqual(A["backup_errors"], {})
        self.assertEqual(A["counts"]["backups"], 2)

    def test_message_deleted_from_live_db_recovered_from_backup(self):
        got = {r["key_id"]: r for r in A["deleted_messages_from_backups"]}
        d1 = TA["deleted_messages"]["1363253484-1"]
        self.assertIn("1363253484-1", got)
        self.assertEqual(got["1363253484-1"]["content"], d1["content"])
        self.assertEqual(got["1363253484-1"]["backups"], [d1["in_backup"]])

    def test_only_backed_up_messages_are_recovered(self):
        expected = {k for k, t in TA["deleted_messages"].items() if t["in_backup"]}
        self.assertEqual({r["key_id"] for r in A["deleted_messages_from_backups"]}, expected)

    def test_backup_is_not_synchronised_with_live_db(self):
        c = Case(C["alice"]["fs"])
        old = backups.messages_from_backup(c.backups_dir / "msgstore-2013-03-14.crypt")
        live = chat.load_messages_from_file(c.msgstore_db)
        self.assertNotEqual(len(old), len(live))
        self.assertTrue(any(m.key_id == "1363253484-1" for m in old))
        self.assertFalse(any(m.key_id == "1363253484-1" for m in live))

    def test_log_and_backup_combine_for_full_picture(self):
        d1 = next(d for d in A["deleted_messages_from_logs"] if d["key_id"] == "1363253484-1")
        rec = next(r for r in A["deleted_messages_from_backups"] if r["key_id"] == "1363253484-1")
        self.assertEqual((d1["partner"], d1["state"], rec["content"]), (rec["remote_jid"], "DELIVERED", rec["content"]))
        self.assertTrue(rec["content"])


class F13_Settings(unittest.TestCase):
    def test_registered_number_and_sim_mismatch(self):
        i, t = A["identity"], TA["identity"]
        self.assertEqual((i["registered_number"], i["sim_mismatch"], i["me_jpg_sha256"]),
                         (t["registered_number"], t["sim_mismatch"], t["me_jpg_sha256"]))

    def test_matching_sim_is_not_flagged(self):
        from wa_forensics.analyze import analyze
        self.assertFalse(analyze(C["alice"]["fs"], sim_number="+1 (202) 555-0101")["identity"]["sim_mismatch"])


if __name__ == "__main__":
    unittest.main()
