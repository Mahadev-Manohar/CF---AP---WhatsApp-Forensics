"""Negative tests: the limitations the paper states must also hold in the implementation.

An analyser that "knew too much" (e.g. dated a contact deletion or resolved an ambiguous unblock) would be
claiming something the artifacts cannot support.
"""

import unittest

from tests import support
from wa_forensics import contacts, logparser
from wa_forensics.case import Case

A = support.alice()
C = support.corpus()


class PaperLimits(unittest.TestCase):
    def test_ambiguous_unblock_not_resolved(self):
        """Sec. 4.1.3: with several blocked users and a cumulative unblock event, status is unknowable."""
        st = {j: v["status"] for j, v in A["blocks"].items()}
        self.assertEqual(st["12025550105@s.whatsapp.net"], contacts.INDETERMINATE)
        self.assertEqual(st["12025550106@s.whatsapp.net"], contacts.INDETERMINATE)

    def test_unblock_event_has_no_jid(self):
        ev = logparser.load_logs(Case(C["alice"]["fs"]).logs_dir)
        self.assertTrue(all("jid" not in e.fields for e in ev if e.kind == "unblock"))

    def test_deletion_time_of_contact_not_reported(self):
        """Sec. 4.1.4: deletion events carry no jid, so no deletion time may be given."""
        for v in A["contact_added"].values():
            self.assertNotIn("deleted_at", v)
        self.assertIsInstance(A["deleted_contacts_from_logs"], list)       # only ids, no times

    def test_purged_log_hides_contact_add(self):
        """Sec. 4.1.2/4.1.4 caveat: inferences need the log file to still exist."""
        self.assertNotIn("12025550109@s.whatsapp.net", A["contact_added"])
        self.assertNotIn("whatsapp-2013-09-20.log", C["alice"]["truth"]["log_files"])

    def test_deleted_message_content_not_recovered_from_logs(self):
        for d in A["deleted_messages_from_logs"]:
            self.assertFalse(d["content_recoverable_from_logs"])

    def test_deleted_message_missing_from_backups_has_no_content(self):
        got = {r["key_id"] for r in A["deleted_messages_from_backups"]}
        for key in ("1363250000-7", "1380700000-1", "1380700100-3"):
            self.assertNotIn(key, got)

    def test_never_blocked_contact_has_no_status(self):
        ev = logparser.load_logs(Case(C["alice"]["fs"]).logs_dir)
        from wa_forensics.timeutil import from_ms
        self.assertIsNone(contacts.blocked_status_at(ev, "99999@s.whatsapp.net", from_ms(1380000000000)))

    def test_blocked_by_others_not_detectable(self):
        """Sec. 4.1.3: nothing is stored on the blocked side; the output exposes no 'blocked_me' notion."""
        self.assertNotIn("blocked_by", A)
        self.assertNotIn("blocked_me", A)

    def test_corrupt_log_lines_are_tolerated(self):
        """Garbage before the first record is ignored; a stray indented line is absorbed into the previous record
        (so that record is no longer classified) rather than crashing or inventing an event."""
        text = ("garbage first line\n"
                "2013-01-01 00:00:00.000 I: msgstore/delete 1-1\n"
                "2013-01-01 00:00:01.000 I: msgstore/delete 2-2\n"
                "   stray continuation\n")
        ev = logparser.parse_text(text)
        self.assertEqual([e.kind for e in ev], ["msg_delete", "other"])
        self.assertEqual(ev[0].fields["key_id"], "1-1")


if __name__ == "__main__":
    unittest.main()
