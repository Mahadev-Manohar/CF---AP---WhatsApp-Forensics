# Specification distilled from the paper

Sources: Tables 1-5 and Sec. 4 of the paper; log formats transcribed from Figs 1, 2, 13, 14, 15
(`research/paper_figures/`). Phone numbers in the figures are redacted (`XXXXXXX`); the log parser accepts that.

## Artifacts (Table 1)
| Artifact | Path in extracted tree | Used by |
|---|---|---|
| contacts DB `wa.db` | `data/data/com.whatsapp/databases/` | `contacts.py` |
| chat DB `msgstore.db` | same | `chat.py` and others |
| backups `msgstore.db.crypt`, `msgstore-<date>.crypt` | `mnt/sdcard/WhatsApp/Databases/` | `backups.py` |
| avatars `<jid>.j` | `files/Avatars/`, `mnt/sdcard/WhatsApp/ProfilePictures/` | `contacts.orphan_avatars` |
| logs `whatsapp.log`, `whatsapp-<date>.log` | `files/Logs/` | `logparser.py` |
| received / sent media | `mnt/sdcard/WhatsApp/Media/`, `.../Media/Sent/` | `media.py` |
| `me`, `me.jpg` | `files/` | `settings.py` |

## Log grammar
`YYYY-MM-DD HH:MM:SS.mmm <L>: [thread]? text` + indented continuation lines; `[...]` = elision (figures only).

| Event (text starts with) | Meaning | Used for |
|---|---|---|
| `found 0 similar contacts to row_id=N jid=J` | new contact discovered | contact-add time (F2) |
| `updated photo id for contact jid=J photo_id_timestamp=.. thumb_ts=..` | avatar downloaded | F2 corroboration |
| `xmpp/reader/read/blocklist/add J` | J blocked | F3 |
| `xmpp/writer/write/blocklist` (no jid) | unblock, cumulative | F3 |
| `msgstore/add/send J KEY 0` | message sent | F11 |
| `msgstore/add/receive J KEY 0` | message received (**assumed**, D-07) | F11 |
| `xmpp/reader/read/message/receipt/server J KEY`, `.../device J KEY` | server / recipient acks | F8, F11 |
| `msgstore/delete KEY` | message deleted | F11 |
| `newgroup/go create group: <creator>-<name>@temp`; `groupmgr/onGroupCreated/gid: G/<name>/<epoch ms>`; `groupmgr/onGroupAddUser/jid: J/gid:G`; `groupmgr/onGroupRemoveUser/jid: J/gid:G/ removed_by:X` | group lifecycle | F10, F11 |

## Message database semantics
- `key_from_me` 0 in / 1 out; `key_id` = `<sender app start epoch s>-<counter>`, shared by sender and recipient.
- Outgoing `status`: 0 not yet at server, 4 on server, 5 delivered; 6 = control message. Times: `timestamp` (created),
  `receipt_server_timestamp`, `receipt_device_timestamp`; `-1` = not set.
- `media_wa_type`: 0 text, 1 image, 2 audio, 3 video, 4 contact card (vCard in `data`), 5 geo (`latitude`/`longitude`, map in `raw_data`).
- `media_hash` = base64(SHA-256(file)); `media_url` last component = server file name; recipient's `media_name` is empty.
- Broadcast: sender has one row per recipient + one `broadcast` row (`needs_push=2`); recipient has one row with `%`-prefixed `key_id`.
- Group: `key_remote_jid` = `<creator>-<epoch s>@g.us`; control rows `status=6`, `media_size` 1 create / 4 join / 5 leave, user in `remote_resource`.

## Findings F1-F13 (the validation targets)
F1 contact list | F2 contact-add time | F3 blocked contacts + unblock ambiguity | F4 deleted contacts (no deletion time) |
F5 chat chronology + sender/recipient correlation | F6 media correlation by name/URL/hash | F7 vCard + geolocation |
F8 message delivery state machine | F9 broadcast partners | F10 group id, control messages, membership timeline |
F11 deleted messages from logs (content lost) | F12 `.crypt` backups recover deleted messages | F13 `me`/`me.jpg`, SIM mismatch, orphan avatars
