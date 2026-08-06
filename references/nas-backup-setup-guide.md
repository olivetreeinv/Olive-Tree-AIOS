# NAS Backup / File Store / File Access Setup Guide

Complete, step-by-step setup for a **Synology DS223j** + **MacBook Air M4** + **two iPhone 14s**, with Google Drive kept as the company source of truth.

Written for DSM 7.2. Every part ends with a **✅ You'll know it worked when…** check. Follow the parts in order — later parts assume earlier ones are done.

---

## Your hardware, and the one fact that shapes everything

| Item | Spec | Consequence |
|---|---|---|
| Synology **DS223j** | 2-bay, Realtek RTD1619B, **1 GB RAM (soldered), ext4 only** | **No Btrfs.** So no Active Backup for Business, no snapshots, no self-healing checksums. We design around this. |
| Drives | 2× 4 TB Seagate IronWolf | SHR / RAID-1 → **~3.6 TB usable, mirrored** |
| Network | 1× 1GbE, **no Wi-Fi** | Must be wired to the router |

**What the DS223j *does* do, which is everything you need here:** Cloud Sync (pull Google Drive down), Time Machine over SMB, Synology Drive + Synology Photos, Hyper Backup (offsite), QuickConnect + mobile apps.

**RAID-1 is not a backup.** The two mirrored drives protect against *one drive dying*. They do **not** protect against accidental deletion, ransomware, theft, or fire. That is what the offsite copy in Part 7 is for.

---

## The whole system in one picture

```
                 ┌──────────────────────────┐
   Google Drive  │   Google Workspace        │  ← live source of truth
   (cloud)       │   ~17 Olive Tree folders  │
                 └───────────┬──────────────┘
                             │ Cloud Sync (DOWNLOAD-only, nightly)
                             │ converts Docs/Sheets → .docx/.xlsx/.pptx
                             ▼
   ┌──────────────────────────────────────────────────────────┐
   │             Synology DS223j  (SHR/RAID-1, ~3.6 TB)        │
   │                                                            │
   │  /GoogleDrive-Backup  ← Cloud Sync mirror (read-only copy) │
   │  /TimeMachine         ← Mac backups (SMB, quota-capped)    │
   │  /Photos              ← Synology Photos (both iPhones)     │
   │  /Team-Shared         ← shared working files (2 users)     │
   │  /homes/brian /homes/<teammate>  ← private home folders    │
   └───────┬───────────────┬──────────────────┬────────────────┘
           │ Time Machine   │ Synology Drive   │ Synology Photos
           │ (SMB)          │ + Finder (SMB)   │ + DS file
           ▼                ▼                  ▼
     MacBook Air M4    Mac + both iPhones   both iPhone 14s
                      (anywhere via QuickConnect + 2FA)

   Offsite (3-2-1):  DS223j ──Hyper Backup──▶ rotated USB drive
                     (or Synology C2 / Backblaze B2)
                     backs up only NAS-unique data: /Photos + /TimeMachine
```

**Why this is already close to 3-2-1 (3 copies, 2 media, 1 offsite):**
- **Google Drive docs** → 3 copies (Google cloud + NAS Cloud Sync + originals on your Mac). Covered.
- **Mac** → 2 copies (the Mac itself + Time Machine on the NAS).
- The only data living *only* on the NAS is **phone photos + Time Machine history** → that's exactly what Part 7's offsite copy protects. If both iPhones already use iCloud Photos, offsite is optional (see Part 7).

---

## Part 0 — Pre-flight

1. Seat both IronWolf drives in the DS223j. **First-time setup erases them** — make sure nothing is on them.
2. Run a wired Ethernet cable from the DS223j to your router. (No Wi-Fi on this model.)
3. Power on. Wait ~2 min for the blue status light to stop blinking.
4. On the Mac, go to **https://find.synology.com** (or install **Synology Assistant**). It will find the NAS on your network.
5. In your **router**, reserve a fixed IP for the NAS (DHCP reservation, by its MAC address). Stable IP = reliable Time Machine + remote access. Note the IP — call it `NAS_IP` below.

**✅ You'll know it worked when…** `find.synology.com` shows the DS223j as "Not installed / Ready to set up" and you have a reserved IP for it in the router.

---

## Part 1 — First boot & storage

1. Click **Connect** in the finder page → the DSM install wizard opens.
2. Install **DSM 7.2** (let it download the latest).
3. Create the administrator account:
   - **Do NOT name it `admin`** (that's the account attackers guess first).
   - Use a long, unique password. Save it in your password manager.
4. Device name: e.g. `olive-nas`.
5. **DSM auto-update:** choose "Install important updates automatically", set the window to overnight (e.g. 3–5 AM).
6. Skip/decline the "Synology Account" prompt for now — you'll set it up in Part 6 for QuickConnect.
7. Open **Storage Manager**:
   - Create a **Storage Pool** → choose **SHR** (Synology Hybrid RAID, 1-disk redundancy). This mirrors the two 4 TB drives.
   - Create a **Volume** on it → file system will be **ext4** (only option on this model). Use the full space.
   - Let it run the parity/consistency check in the background (can take hours — you can keep working).

**✅ You'll know it worked when…** Storage Manager shows one Storage Pool + one Volume, status **Healthy**, ~3.6 TB capacity.

---

## Part 2 — Users, groups & shared folders (you + teammate)

**Enable home folders first:**
1. **Control Panel → User & Group → Advanced** tab → check **Enable user home service** → Apply. Every user now gets a private `home` folder automatically.

**Create the accounts:**
2. **Control Panel → User & Group → User → Create:**
   - `brian` — strong password, email = brian@olivetreeinv.io.
   - `<teammate>` — their name, their email.
3. **Group → Create** a group called `staff`; add both users to it.

**Create the shared folders** (Control Panel → Shared Folder → Create):

| Folder | Who can access | Notes |
|---|---|---|
| `Team-Shared` | `staff` group → Read/Write | Shared working files |
| `GoogleDrive-Backup` | `brian` → Read/Write; teammate → Read-only | Cloud Sync writes here (Part 3) |
| `TimeMachine` | `brian` → Read/Write | Mac backups (Part 4) |
| `Photos` | `staff` → Read/Write | Phone photo vault (Part 5) |

- Private per-person files live in each user's own **home** folder (created automatically in step 1) — no setup needed.
- For each shared folder, on the **Advanced** tab of its settings, **enable the Recycle Bin**. Since this model has no snapshots, the Recycle Bin is your safety net for accidental deletes. Set **Control Panel → Task Scheduler** to empty recycle bins older than 30 days monthly (keeps the volume from filling).

**✅ You'll know it worked when…** Both users can log into DSM (`http://NAS_IP:5000`), each sees their own home folder, and both see `Team-Shared` but only Brian can write to `GoogleDrive-Backup`.

---

## Part 3 — Google Drive backup (Cloud Sync)

This pulls your entire Google Drive down to the NAS on a schedule, **one-way**. The NAS never writes back to Google, so it can't corrupt your source of truth.

1. **Package Center → install Cloud Sync.**
2. Open Cloud Sync → **+** → choose **Google Drive** → **Next** → sign in and authorize `brian@olivetreeinv.io`.
3. Configure the connection:
   - **Sync direction:** **Download remote changes only** ← critical. (Not "Two-way".)
   - **Local path:** `GoogleDrive-Backup`.
   - **Remote path:** root (`/`) to grab everything, or pick specific folders (e.g. `Olive Tree Investments - *`).
4. **Advanced settings:**
   - **Enable "Convert Google Online documents to Microsoft Office format on download."** This turns native Docs/Sheets/Slides into real `.docx` / `.xlsx` / `.pptx` files. Without this, you'd only back up unusable pointer files. **This is the whole reason a Google Drive backup is more than a folder copy.**
   - **Don't sync files in the recycle/trash.**
5. **Schedule:** open the connection's schedule and set it to run **nightly** (e.g. 1 AM). Continuous sync works, but on 1 GB of RAM a nightly window is gentler on the box.
6. Let the first full sync run — it can take a while depending on Drive size. Watch the Cloud Sync activity log.

> **Note:** This backs up the Google *account's* files. Your ~17 top-level company folders (Deals, Marketing, Legal Docs, GovCon Bid Documents, Meetings, Systems, BPO, Taxes 2023–2025, etc.) all come down under this one connection. If your teammate has company files under a *different* Google account, add a second Cloud Sync connection for them into a subfolder.

**✅ You'll know it worked when…** In File Station, open `GoogleDrive-Backup` and find a known file — e.g. something under `Olive Tree Investments - Deals` — now present as a `.docx` or `.xlsx` you can open.

---

## Part 4 — Mac backup (Time Machine over SMB)

1. **Control Panel → File Services → SMB** tab → **Enable SMB service** → Apply.
2. **Control Panel → File Services → Advanced** tab (or the "Time Machine" section) → **Set Time Machine folders** → select `TimeMachine`.
3. Set a **quota** on the `TimeMachine` folder so backups can't eat the whole volume: **Control Panel → Shared Folder → `TimeMachine` → Edit → Advanced → Quota → 1500 GB** (~1.5 TB). Time Machine will keep the most recent backups within that cap and drop the oldest.
4. On the **MacBook Air M4**:
   - **System Settings → General → Time Machine → Add Backup Disk…**
   - Pick the NAS `TimeMachine` share (it appears as a network disk). Authenticate as `brian`.
   - **Check "Encrypt Backup"** and set an encryption password (store it in your password manager — you need it to restore).
   - Let the **first backup run over the wired network if possible** — the initial full backup of an M4 can be tens to hundreds of GB. After that it backs up hourly over Wi-Fi automatically.

**✅ You'll know it worked when…** On the Mac, `tmutil status` (Terminal) shows a completed backup, and the Time Machine menu shows "Latest backup: today". Then test a restore: enter Time Machine, pick an older version of a test file, restore it.

---

## Part 5 — File access (Mac + both iPhones)

### Mac
- **Synology Drive Client** (download from Synology's site) → connect to the NAS via `NAS_IP` (local) or QuickConnect ID (Part 6). Sync or **pin** `Team-Shared`. Use **On-Demand Sync** to keep files in the cloud and only download on open — saves the M4's SSD.
- Or, for quick access without the client: in Finder, **Go → Connect to Server → `smb://NAS_IP`** → mount `Team-Shared`.

### Both iPhones
Install these three apps (App Store), sign into each with the right user (`brian` / teammate):
- **Synology Drive** — browse, open, and sync files (Team-Shared, home folder).
- **DS file** — lightweight file browser / on-the-spot download & upload.
- **Synology Photos** — the phone photo backup (below).

### Phone photo backup (Synology Photos)
1. **Package Center → install Synology Photos** on the NAS.
2. On each iPhone, open the **Synology Photos** app → sign in → **Settings → Photo Backup → enable**.
   - Back up to each user's **personal space**, so Brian's phone and the teammate's phone don't mix. (Or point both at the shared `Photos` folder if you *want* them pooled — your call.)
   - Enable "Background backup" so it uploads without opening the app.

**✅ You'll know it worked when…** From a phone on cellular data, you open Synology Drive and open a `Team-Shared` file; and a photo you just took shows up in Synology Photos within a few minutes.

---

## Part 6 — Remote access (anywhere) + security hardening

Because the NAS is about to be reachable from the internet, do the hardening steps — they're not optional.

### QuickConnect (no port-forwarding — the safe default)
1. **Control Panel → External Access → QuickConnect** → **Enable QuickConnect** → sign in / create a **Synology Account**.
2. Set a **QuickConnect ID**, e.g. `olive-nas`. You'll now reach the NAS at **`https://olive-nas.quickconnect.to`** and via that same ID in all the DS mobile apps and Synology Drive Client — from anywhere, with **no ports opened on your router**. Synology relays the connection.

### Hardening checklist (do all of these)
- **Control Panel → Security → Account → 2-Factor Authentication:** require it for **every** account. Use an authenticator app.
- **Control Panel → Security → Protection → Auto Block:** enable — block an IP after e.g. 5 failed logins in 5 minutes.
- **Control Panel → Security → Firewall:** enable; allow your local subnet + QuickConnect, deny the rest.
- **Control Panel → Login Portal → DSM → enable HTTPS** and "Automatically redirect HTTP to HTTPS."
- **Disable the built-in `admin` and `guest` accounts** (User & Group — they should already be off since you named your admin something else).
- **Do NOT port-forward 5000/5001** (or any DSM port) on your router. QuickConnect makes that unnecessary; open ports are the #1 way these boxes get hit.
- Keep **DSM + every package on auto-update**.

### Higher-security alternative (optional)
If you'd rather not use QuickConnect's relay at all, install **Synology VPN Server** (or the **Tailscale** package) and reach the NAS only through a VPN tunnel. More secure, slightly more setup, and phones need the VPN/Tailscale app running. QuickConnect + 2FA is fine for your use; this is the upgrade path if you ever want it.

**✅ You'll know it worked when…** From a phone on **cellular only** (Wi-Fi off), you open `https://olive-nas.quickconnect.to`, get prompted for 2FA, and reach your files. And a deliberate wrong-password attempt shows up under Security → Auto Block.

---

## Part 7 — Offsite backup (completing 3-2-1)

The NAS mirror protects one drive dying. Offsite protects against theft, fire, and ransomware. You only need to back up the **NAS-unique** data — `/Photos` and `/TimeMachine` — because your Google Drive docs already have a cloud copy.

1. **Package Center → install Hyper Backup.**
2. Create a backup task → source = **`Photos` + `TimeMachine`** (add `Team-Shared` if you want).
3. Pick a destination (see cost table).
4. Schedule it weekly; enable backup versioning + integrity check.

### Destination options — cost flagged (per your cost rule)

| Option | Cost | Notes |
|---|---|---|
| **Rotated USB drive (recommended start)** | **~$60 one-time** (4 TB USB), **$0/mo** | Hyper Backup → local USB (plug into the NAS's USB port). Keep it off-site (office/relative's house), swap monthly. Cheapest honest offsite. |
| **Synology C2** | ~$3/TB/mo | Tightest integration, one-click restore. |
| **Backblaze B2** | ~$6/TB/mo | Cheapest name-brand cloud, S3-compatible. |

**Recommendation:** start with the **rotated USB drive** — one-time cost, and if both iPhones already have **iCloud Photos** on, the only truly irreplaceable NAS-only data is small. Upgrade to **Synology C2** later *only if* you know you won't actually rotate a USB drive by hand.

**✅ You'll know it worked when…** The first Hyper Backup task completes green, and you use its **Restore** wizard to pull one file back to a test folder.

---

## Part 8 — Final end-to-end verification

Run this checklist once everything's built. **Test restores, not just backups** — an untested backup is a hope, not a backup.

- [ ] **Cloud Sync:** a Google Doc appears as a `.docx` under `GoogleDrive-Backup`.
- [ ] **Time Machine:** `tmutil status` shows a completed backup; a test file restores from an older snapshot.
- [ ] **Synology Photos:** a new photo from *each* iPhone lands in `/Photos` within minutes.
- [ ] **Remote access:** phone on cellular opens a file via QuickConnect, 2FA prompts.
- [ ] **Hyper Backup:** first job green; restore-one-file test passes.
- [ ] **Security:** 2FA enforced on all accounts; a failed login triggers Auto Block.

---

## Quick reference

| Job | Package / App | Direction |
|---|---|---|
| Google Drive → NAS | Cloud Sync | Download-only, nightly |
| Mac → NAS | Time Machine (SMB) | Hourly |
| iPhones → NAS (photos) | Synology Photos | Background auto-backup |
| File access (Mac/phones) | Synology Drive, DS file, Finder SMB | Two-way / on-demand |
| Anywhere access | QuickConnect + 2FA | — |
| NAS → offsite | Hyper Backup | Weekly |

**Maintenance:** DSM + packages auto-update; check Storage Manager health monthly; confirm Hyper Backup ran green weekly; run IronWolf S.M.A.R.T. extended test quarterly (Storage Manager → HDD → Health Info).
