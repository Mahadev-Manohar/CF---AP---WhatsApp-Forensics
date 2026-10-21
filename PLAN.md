# Reproduction plan: "Forensic Analysis of WhatsApp Messenger on Android Smartphones"

Status: **Track A approved and implemented (see REPORT.md). Track B not started.** Nothing was installed and no system settings were changed; Track A uses the Python standard library only.
Original draft text follows.
Only read-only inspection, web research and stdlib-only PDF extraction were done (outputs in `research/`, `tools/`).

## 1. System inspection (2026-10-21)

| Item | Finding | Implication |
|---|---|---|
| OS | Windows 11 Home SL 10.0.26300, x64 | |
| CPU / RAM | i5-12450H, 8C/12T, 15.6 GB | Enough for 1 small Android VM |
| Disk | C: 125.9 GB free, D: 8.5 GB free | Work on C: only |
| Virtualization | Firmware flag reads `False` but `HypervisorPresent=True`, VBS/HVCI running | Hypervisor is active (Hyper-V/WSL2/Docker). Reading "False" is expected while a hypervisor owns VT-x. Third-party VMs run through the Windows Hypervisor Platform backend (slower) |
| Installed | Python 3.12.10 (+3.14 launcher), Git 2.54, Node 24, VS Code, Docker Desktop 29.7 (WSL2 backend), VirtualBox 7.2.8 (not on PATH; one existing VM: Kali), winget | Python `sqlite3` + `hashlib` in stdlib cover most of the analysis |
| Not installed | Java, adb, sqlite3 CLI, 7-Zip, QEMU, PDF libs, pytest | Need approval to install (see section 6) |
| Project dir | Only the paper PDF | |

## 2. Paper methodology (extracted)

- **Approach**: controlled experiments per scenario (1-to-1, group, broadcast, multimedia, contact card, geolocation, block/unblock, delete). One software-emulated device per role.
- **Testbed**: YouWave VMs, Android 4.0.4, WhatsApp Messenger 2.11. After each experiment the VM is suspended, the `youwave_vm01.vdi` disk is opened with **FTK Imager 3.1**, the files are exported, then inspected with **SqliteMan** (SQLite v3 DBs) and **Notepad++** (logs). Geolocation was the only experiment done on a physical phone (YouWave has no GPS), using the backup mechanism.
- **Artifacts (Table 1)**: `wa.db`, `msgstore.db` (`/data/data/com.whatsapp/databases`), `msgstore*.crypt` backups (`/mnt/sdcard/Whatsapp/Databases`, AES-192, one fixed key published in the paper), avatars (`files/Avatars`, `sdcard/WhatsApp/ProfilePictures`, `<jid>.j`), logs (`files/Logs/whatsapp*.log`), media (`Media`, `Media/Sent`), preferences (`files/me`, `me.jpg`).
- **Schemas**: Tables 2-5 (`wa_contacts`, `messages`, `chat_list`) are fully specified in the paper.
- **Expected findings to reproduce** (each becomes a validation test, see section 5):
  F1 contact list + jid format; F2 contact-add time from logs (Fig 1); F3 blocked contacts from logs, with the unblock-ambiguity limit (Fig 2); F4 deleted contacts via log-vs-DB diff, no deletion time; F5 chat chronology and key_id correlation across sender/receiver; F6 media: sender/receiver correlation by `media_url` filename and SHA-256 hash, and matching a recipient file with an empty `media_name` by hash; F7 vCard and geo records; F8 message state machine (status 0/4/5 and three timestamps, Fig 8); F9 broadcast (`broadcast` jid, `needs_push=2`, `%` key_id prefix on recipients); F10 group id = `creator-epoch@g.us`, control messages (`status=6`, `media_size` 1/4/5), membership timeline (Fig 12); F11 deleted messages recovered from logs (`msgstore/delete`, `msgstore/add/send`, receipt/server, receipt/device); F12 `.crypt` backup decryption and recovery of messages deleted from the live DB; F13 `me` phone number vs. SIM, `me.jpg` avatar persistence.
- **Text-extraction caveat**: some sentences and every figure were not text-extractable. I rendered the 15 figures to PNG (`research/paper_figures/`) and read the log figures. Remaining figures (record tables, Figs 3-12) still need transcribing, and I will do that in Milestone 1.

## 3. Availability of original components (legitimate sources only)

| Component | Verdict | Notes |
|---|---|---|
| **YouWave** | **Not legitimately obtainable.** | Developer site reported offline since ~2022, last release 2017, only third-party mirrors (FileHippo, FilePlanet). Mirrors are unofficial and the product is old adware-era software that bundles an Android-x86 stack. I will **not** download it. |
| **Android 4.0.4** | **Obtainable, with caveats.** | The official Android SDK once shipped an Intel x86 ICS image (API 15, listed as 4.0.3/4.0.4_r02). Whether Google's repository still serves it must be verified. The AOSP source is also available but building it is heavy. Android-x86 project releases are another candidate. |
| **WhatsApp 2.11** | **Obtainable only from third-party APK mirrors, and useless.** | WhatsApp expires old clients and servers reject them, so a 2.11 client cannot register or exchange messages. No official archive exists. I won't fetch it. This blocks **live** generation of artifacts: the paper's experiments cannot be re-run as originally done. |
| **FTK Imager 3.1** | **Not obtainable officially.** | Exterro hosts only newer builds (4.x, behind a sign-up form), possibly some past versions. A 3.1.x copy exists on a training site's Google Drive (unverified). Free modern FTK Imager is a legitimate substitute. The paper only uses it to browse a VDI and export files, which can also be done with open tools. |
| SqliteMan / Notepad++ | Replaceable | Python `sqlite3` plus DB Browser for SQLite and VS Code. |

## 4. Original vs feasible alternatives (no silent substitution)

| Original | Alternative | Fidelity | Decision requested |
|---|---|---|---|
| YouWave VM | VirtualBox 7.2.8 (already installed) with an Android-x86 ICS/KitKat image, or Android SDK emulator (needs WHPX) | Different emulator, same Android family | Approve only the *optional* Track B below |
| Android 4.0.4 | Same version if the x86 image is available, otherwise nearest (4.0.3 or 4.4 x86) and documented | Exact or near | |
| WhatsApp 2.11 live | **Synthetic artifact generator** that reproduces 2.11's on-disk formats from the paper's tables and figures | Documents the format, not live app behavior | **Core approach (Track A)** |
| FTK Imager 3.1 | FTK Imager (current, free, with sign-up) or open tools: WSL2/Linux `qemu-img`/`vdfuse` + `debugfs`/`mount`, 7-Zip | Same function | Prefer open tools and no account |
| SqliteMan / Notepad++ | Python parsers plus DB Browser for SQLite | Better (automated) | |

**Honest bottom line:** the paper's *experiments* (running real WhatsApp 2.11 on YouWave) cannot be reproduced. Its *analytical claims* (how artifacts decode and correlate) can be reproduced and tested against synthetic data constructed to the paper's documented formats. Because the synthetic data is built from the same description, passing tests show that the **pipeline implements the paper's rules correctly**. They do **not** independently show that real WhatsApp 2.11 behaves that way. The report will say so.

## 5. Implementation plan

**Track A (core, no installs needed; stdlib Python + `unittest`)**

| # | Milestone | Deliverable | Validation criteria |
|---|---|---|---|
| M1 | Spec extraction | `docs/spec.md`: all tables, field semantics, log event grammar, figures transcribed | Every table row in the paper maps to a spec entry |
| M2 | Synthetic data generator (`wa_synth/`) | Builds a fake Android filesystem tree: `wa.db`, `msgstore.db`, `.crypt` backups (AES-192-ECB, paper key), logs in the Fig 1/2/13/14/15 formats, avatars, media (generated placeholder images, correct SHA-256), `me`, `me.jpg`. All phone numbers fictitious (reserved ranges, e.g. `+1 555-01xx`). Seeded and deterministic, with a machine-readable **ground-truth manifest** per scenario | Schema matches Tables 2-5 exactly. Ground truth is generated independently from the parsers |
| M3 | Acquisition emulation | Imaging/extraction stage: build a disk image, record SHA-256 before and after, read-only extraction, chain-of-custody log (stands in for the FTK step) | Hashes match, source never modified |
| M4 | Parsers/analyzers (`wa_forensics/`) | contacts, log parser, chat history, state machine, media correlation, broadcast/group/membership timeline, deleted-message recovery from logs and `.crypt`, settings, report (CSV/JSON/HTML) | Unit tests per finding F1-F13 |
| M5 | Scenario tests | One controlled scenario per paper experiment (1-to-1, offline/online delivery, group join/leave, broadcast, media, vCard, geo, block/unblock ambiguity, contact deletion, message deletion) | Parser output equals ground truth. **Negative tests** confirm the paper's stated limits (e.g. cannot tell which user was unblocked, cannot date contact deletion) |
| M6 | Paper-example replay | Recreate the paper's own worked examples (timestamps like 2013-09-25 14:14:24, group `…-1363078943@g.us` created 2013-03-12 09:02:23, state timeline 14:15:37.884, 14:17:05.551, 14:21:59.135) as fixtures | Derived values equal the values quoted in the paper |
| M7 | Report | `REPORT.md`: results table per finding with test evidence, plus a **deviations log** | No claim without a passing test or a stated limitation |

**Track B (optional, needs approvals): real Android 4.x VM acquisition demo**
Boot an Android x86 ICS image in VirtualBox, push the synthetic artifacts to `/data/data/com.whatsapp/...`, suspend the VM, extract with open tools or FTK Imager, and run Track A over the extracted tree. This validates the *acquisition path*, not WhatsApp itself. Dependencies: image source verified, WHPX/VirtualBox-on-Hyper-V performance, adb.

### Risks
1. YouWave/FTK 3.1/WhatsApp 2.11 unavailable → documented, substitutions explicit (section 4).
2. Synthetic data is circular (see bottom line) → mitigated by deriving expectations from the paper's quoted examples and by negative tests.
3. Figures not text-extractable → manual transcription from PNGs; ambiguity flagged.
4. VBS/Hyper-V makes VirtualBox slow or flaky → Track B optional, no security settings will be touched.
5. The paper's published AES key is a publicly known weakness of old WhatsApp versions. It is used only on synthetic backups.
6. Disk: D: has only 8.5 GB, so all work stays on C:.

## 6. Approvals I will need (nothing done yet)

| Action | Needed for | Elevation |
|---|---|---|
| `pip install pycryptodome pytest` (user-level venv inside the project) | AES-192 + test runner | No admin. Recommended. Alternative: pure-Python AES and `unittest` for zero installs |
| `pip install pypdf` or similar | Better figure/text re-extraction (optional) | No admin |
| Download DB Browser for SQLite (optional viewer) | Manual inspection | Installer, possibly admin |
| Verify/download Android SDK x86 API 15 image; Android platform-tools (adb) | Track B | Large download (~hundreds of MB), no admin |
| Android-x86 ISO | Track B alt. | Large download |
| FTK Imager (current) from Exterro | Track B, optional | Sign-up form, installer, admin |
| Any WSL/Hyper-V feature change | Track B alt. | **Admin. I will not do this without separate approval** |

I will not download YouWave, WhatsApp APKs, or any copy of FTK Imager from unofficial mirrors.
