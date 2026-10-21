# Reproduction report

**Paper:** "Forensic Analysis of WhatsApp Messenger on Android Smartphones" (2014)
**Date:** 2026-10-21 · **Scope approved:** Track A only (no installs, no downloads, no system changes)
**Evidence:** `docs/test_run.txt` (81 tests, 0 failures; 17/17 injected bugs detected)

## 1. Verdict (read this first)

| Question | Answer |
|---|---|
| Were the paper's **experiments** reproduced (real WhatsApp 2.11 on YouWave / Android 4.0.4, imaged with FTK Imager 3.1)? | **No.** Not possible with legitimate sources (see PLAN.md section 3 and docs/deviations.md D-01/D-02). |
| Was the paper's **analysis methodology** implemented and tested? | **Yes**, for all 13 findings, against *synthetic* artifacts built to the paper's documented formats. |
| Do the tests show real WhatsApp 2.11 behaves as the paper says? | **No.** Synthetic data was built from the same description, so passing tests show the *implementation is faithful to the paper*, not that the paper is right about the app. |
| What gives the tests teeth beyond circularity? | (a) Log parsers are run on the paper's **own printed log figures** and reproduce the paper's quoted dates. (b) Epoch values in the paper's record figures decode to exactly the dates in its text, which also fixed the time zone as UTC. (c) Ground truth is computed in the generator separately from the parsers. (d) Negative tests enforce the paper's stated limits. (e) Mutation check, see below. |

**Therefore: "reproduction successful" is NOT claimed.** What is supported is "analysis pipeline implemented and verified against the paper's specification".

## 2. What was built

| Component | Path | Notes |
|---|---|---|
| Pure-Python AES-128/192/256 (ECB, PKCS#7) | `wa_forensics/aes.py` | Verified with the FIPS-197 vectors (all three key sizes). No third-party packages |
| Log parser | `wa_forensics/logparser.py` | Handles wrapped lines, `[...]` elisions, optional thread tags, rotated logs |
| Analyzers | `contacts.py chat.py media.py groups.py deleted.py backups.py settings.py` | One module per paper subsection |
| Acquisition stage | `acquisition.py` | Hash-verified, read-only extraction + custody log (stand-in for FTK Imager, D-02) |
| Synthetic generator | `wa_synth/generate.py` | 2 fictional devices, deterministic, ground-truth manifests, fictional numbers only |
| Pipeline / CLI | `analyze.py`, `run_pipeline.py`, `python -m wa_forensics` | JSON reports |
| Tests | `tests/` (81) | see below |
| Spec / deviations | `docs/spec.md`, `docs/deviations.md` | 22 numbered deviations, assumptions and paper inconsistencies |

Run everything: `python -m unittest discover -s tests -t .` · demo: `python run_pipeline.py output` · mutation check: `python tools/mutation_check.py`.
Environment: Python 3.12.10, SQLite 3.49.1, Windows 11; standard library only.

## 3. Findings and evidence

"Validated" = automated test passes on synthetic data and, where marked **P**, also on the paper's own printed figures/values.

| # | Paper claim | Status | Tests |
|---|---|---|---|
| F1 | Contact list from `wa_contacts`; jid = `phone@s.whatsapp.net`; non-WhatsApp numbers flagged; avatar timestamp units (10-digit s vs 13-digit ms) | Validated | `F1_Contacts` (5) |
| F2 | Contact-add time from logs (Fig 1: 14:14:24) | Validated, **P** | `F2_ContactAddTime`, `Fig1ContactAdd` |
| F3 | Block time from logs; unblock event has no jid; status only determinable in the paper's cases | Validated, **P** (Fig 2) | `F3_Blocking`, `Fig2Blocking`, negative tests |
| F4 | Deleted contacts = logged-added minus DB; deletion time not obtainable; avatar survives deletion | Validated | `F4_DeletedContacts`, negative tests |
| F5 | Chat chronology; `key_id` correlates sender and recipient records | Validated, **P** (Fig 3 dates) | `F5_ChatHistory`, `QuotedTimestamps` |
| F6 | Media: URL filename + SHA-256 correlate sender/recipient; recipient file found by hash although `media_name` is empty | Validated | `F6_Media` |
| F7 | vCard and geo records | Validated | `F7_ContactCardAndLocation` |
| F8 | Status 0/4/5 state machine and the three timestamps (Fig 8: 14:15:37.884 / 14:17:05.551 / 14:21:59.135) | Validated, **P** | `F8_MessageState`, `QuotedTimestamps` |
| F9 | Broadcast partners (sender rows, `broadcast` self row, `%` key on recipient) | Validated | `F9_Broadcast` |
| F10 | Group id decodes to creator and creation time (Fig 15: 2013-03-12 09:02:23); control messages; membership at any time (Figs 11/12); messages checked against membership | Validated, **P** | `F10_Groups`, `Fig15Group`, `test_fig11_composition` |
| F11 | Deleted messages: who, when, delivery state recovered from logs; content not recoverable (Figs 13/14) | Validated, **P** | `F11_*`, `Fig13_14DeletedMessage` |
| F12 | `.crypt` backups decrypt with the published key and contain messages deleted from the live DB | Validated (synthetic backups only, D-09) | `F12_Backups`, `test_aes` |
| F13 | `me` number vs SIM mismatch; `me.jpg`; orphan avatars evidence contact after contact-record deletion | Validated | `F13_Settings`, `F4_*` |

Test totals: `test_aes` 6, `test_paper_figures` 14, `test_pipeline` 41, `test_limits_negative` 9, `test_acquisition` 11 = 81.

### Test-quality checks
- **Mutation check** (`tools/mutation_check.py`): 17 plausible bugs injected one at a time (unit slips, swapped status codes, wrong key/hash, off-by-one membership, disabled integrity checks...). The first run had **2 survivors**, which exposed real gaps (no avatar-flag assertion; no test for "image changed during acquisition"). Tests were added; now **17/17 killed**.
- **Test-data errors found and fixed** while writing the tests: two hand-computed expectations in the generator were wrong (a reply time and a broadcast time). The parser was right in both cases, which I confirmed by recomputing the epochs by hand before correcting the expectations.
- An earlier mutation run was discarded because its baseline was not green; the numbers above come from a green baseline.

## 4. Limits of this work (do not skip)
1. Synthetic data, so no new empirical evidence about WhatsApp (D-01).
2. The receive-side log-event format is **my invention** (D-07); the paper never shows it. Deleted *incoming* message recovery depends on it.
3. `.crypt` mode/padding and plaintext format are assumptions (D-09). Real 2014-era backup files were never available to test against.
4. Time zone UTC is inferred from the paper's examples (D-06), not stated by it.
5. SQLite free-page carving is not implemented (D-20).
6. Paper-internal inconsistencies were resolved by choice (D-16 to D-18); a different reading is possible.
7. Text extraction of the PDF was done with a hand-written stdlib script; some sentences were lost. All figures were viewed as images, but Fig 12 renders blank. Anything the lost sentences said is not reflected here.

## 5. Not done / possible next steps
- **Track B** (Android 4.x x86 VM in VirtualBox, push synthetic artifacts, suspend, extract with open tools): not started. It needs your approval for large downloads and may be slow under the active hypervisor. It would validate the acquisition path only, not WhatsApp.
- If you can legitimately supply real 2.11-era artifacts (e.g. from your own old test device with synthetic accounts), the pipeline could be run against them, which is the only way to turn this into true empirical reproduction. Assumptions D-07 and D-09 would then be tested.
