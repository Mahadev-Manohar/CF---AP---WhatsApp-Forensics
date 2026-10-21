# Deviations from the paper, assumptions, and paper inconsistencies

Paper: "Forensic Analysis of WhatsApp Messenger on Android Smartphones" (2014 manuscript, CC-BY-NC-ND).
IDs are referenced from code comments and from REPORT.md.

## A. Environment / method deviations (what was NOT reproduced)

| ID | Paper | This project | Consequence |
|---|---|---|---|
| D-01 | Real WhatsApp 2.11 run on YouWave VMs, Android 4.0.4, interactive experiments | **Not run.** Artifacts are generated synthetically from the paper's tables and figures (`wa_synth/`). YouWave is unobtainable from a legitimate source, WhatsApp 2.11 is unobtainable officially and its servers reject old clients | The paper's *empirical observations* are **not independently reproduced**. Only the *analysis rules* are implemented and verified. Tests prove the implementation is faithful to the paper's description, not that real WhatsApp behaves so |
| D-02 | Open `youwave_vm01.vdi` in FTK Imager 3.1, export files | Evidence container is a tar archive; `wa_forensics/acquisition.py` verifies hashes, extracts read-only, verifies a manifest and writes a custody log | Same forensic discipline, different tooling and container. No VDI parsing was done (Track B, not approved or started) |
| D-03 | SqliteMan, Notepad++ | Python `sqlite3` (SQLite 3.49.1), custom log parser | Automated instead of manual |
| D-04 | Geolocation messages generated on a physical phone | Synthetic geo record (fictional coordinates) | No evidence about real location-service behaviour |
| D-05 | Real contacts' phone numbers (redacted in the paper) | Fictional numbers, NANP 202-555-01xx | None for the analysis; a test asserts all generated numbers are in that range |

## B. Assumptions I had to make (the paper does not specify)

| ID | Assumption | Where | Risk |
|---|---|---|---|
| D-06 | All timestamps (DB epochs and log lines) are **UTC**. Evidence: epoch values in Figs 3, 8, 11 and the group id decode to exactly the dates printed in the paper's text under UTC (e.g. 1381932937884 -> 2013-10-16 14:15:37.884). Asserted in `tests/test_paper_figures.py::QuotedTimestamps` | `timeutil.py` | Low. The paper never states a zone, but 100% of the quoted examples agree |
| D-07 | The **receive-side log event** is not shown in the paper. I defined `msgstore/add/receive <jid> <key_id> 0` by analogy with `msgstore/add/send` | `logparser.py`, generator | **Medium.** Real logs may use a different string. Only affects deleted-message recovery for *incoming* messages |
| D-08 | Field names: the PDF text lost underscores; they were restored from the figure headers (`key_remote_jid`, `receipt_server_timestamp`, `media_wa_type`...). `_id` for the sequence number is assumed. Column set = Tables 2-5 | generator, `chat.py` | Low |
| D-09 | `.crypt` backup = AES-192, **ECB**, PKCS#7, plaintext = raw SQLite file, with the key printed in the paper. Mode/padding/plaintext format are not stated in the paper | `aes.py`, `backups.py` | Medium for real files; irrelevant for synthetic ones. Wrong key / non-SQLite plaintext is rejected |
| D-10 | Broadcast sender records: `remote_resource` holds the recipient list **comma-separated** (Fig 9a is truncated). The analysis treats the per-recipient `key_remote_jid` rows as authoritative and only cross-checks the list | `groups.py` | Low |
| D-11 | Recipient-side broadcast `key_id` is `%~<id>` in Fig 9(b) but "%" + id in the text. Both forms are accepted | `chat.py` | Low |
| D-12 | "Contact added" time := first `found 0 similar contacts` event for the jid (Fig 1 line 4). Avatar completion (line 17) is kept as corroboration | `contacts.py` | Low |
| D-13 | Block-status rule: formalisation of the paper's conditions (a)/(b). A block names the contact; a cumulative unblock event resolves a status only if exactly one contact could still be blocked, otherwise the candidates become INDETERMINATE (and stay so). The paper gives no rule for more complex sequences | `contacts.block_history` | Conservative by design |
| D-14 | `me` file: ASCII phone number (as the paper says). Real file may carry more | `settings.py` | Low |
| D-15 | Table 1 paths: capitalisation is inconsistent in the paper (`Whatsapp`/`WhatsApp`, `comm.whatsapp`). Used `com.whatsapp` and a case-insensitive lookup | `case.py` | None |

## C. Inconsistencies inside the paper (and which reading I implemented)

| ID | Inconsistency | Implemented |
|---|---|---|
| D-16 | Table 3 defines `status` as 0=received, 4=waiting on server, 5=received by destination, but Sec. 4.2.4 says an *outgoing* record with status 0 is **not yet delivered to the server** | Sec. 4.2.4 semantics for outgoing messages; incoming status 0 = received |
| D-17 | Table 3: `timestamp` = "record insertion time" for incoming messages; Sec. 4.2.2 reads the receive time from `received_timestamp`; Sec. 4.2.5 says group-message receipt time is in `timestamp` | Message time = `timestamp` (outgoing) / `received_timestamp` (incoming, falling back to `timestamp`); group-membership checks use `timestamp` |
| D-18 | Sec. 4.1.4 says the **deletion time** of a contact cannot be determined; the Conclusion says the correlation recovers deleted contacts "and their time of deletion" | Sec. 4.1.4 (it is the detailed, argued one). A negative test asserts that no deletion time is reported |
| D-19 | Sec. 3 claims the fixed AES key "is used on all devices"; the paper is dated 2014 and applies to WhatsApp 2.11-era `.crypt` files only | Used only against synthetic backups |

## D. Not implemented

| ID | Item | Why |
|---|---|---|
| D-20 | Carving of deleted SQLite records / free pages (Sec. 4.1.4, 4.2.6) | The paper delegates it to other tools and gives no method. Recovery here is only via logs and backups |
| D-21 | Fig 12 (group composition timeline picture) | Not extractable from the PDF (blank render); reproduced from Fig 11 + text instead (`test_fig11_composition`) |
| D-22 | Audio/video-specific handling, `thumb_image`, `send_timestamp` | No evidentiary value per the paper, or never populated |
