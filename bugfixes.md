# Bugfixes

## 02-10-2026 — Orphaned ffmpeg processes recording live streams indefinitely

**Commit:** `d2215b3` (fix zombie scraps)

### Symptom
Tuberipper was saturating the network. The `tuberipper-webapp-1` container had received ~100 GB in 4 days.
Five `ffmpeg` processes were running inside it, four of them recording the **same** live stream
(`FpbsnK5EJBk`, @DigitalLosersCorner) — one spawned per scheduled run (18:43, 19:38, 20:35, 21:31) — plus one
that had been running for ~25 hours from the previous day's stream (`ghiW5FOyER0`).

### Root cause
Three problems compounding:

1. **Live detection failed.** `scrap_single_channel` relies on `is_live_ring_present()` to skip channels that are
   currently live. The live-ring CSS selectors were timing out, so the JS fallback grabbed the first thumbnail on the
   streams tab — the in-progress live stream — and treated it as a finished VOD.
2. **yt-dlp timeout orphaned ffmpeg.** For a live URL, yt-dlp hands the download to an `ffmpeg` child that records
   the HLS stream. `_run_yt_dlp` used `subprocess.run(timeout=600)`, which kills yt-dlp after 10 minutes but
   leaves its ffmpeg child running until the stream ends.
3. **Infinite retry.** The rip then "failed" (`OSError: file not found ... .mp3`), no DB record was written, and the
   next scheduled run saw the video as un-ripped and spawned another recorder.

Side effect: the daily 04:30 staging cleanup only waits on `_scrape_lock`. Since the orphaned ffmpeg outlived the
scrape, the cleanup deleted its `.part` file while it was still writing to it — so it kept downloading into a
deleted inode, wasting bandwidth for nothing.

Log history showed this had happened before: `ghiW5FOyER0` was attempted 16 times and `U3Ouf5XP510` 4 times
(its reported duration kept growing — 6109s → 9709s → 10585s — i.e. it was live). Both eventually ripped
successfully once the stream ended; every orphan they left behind ran until then.

### Fix
- **`scraper/utils.py` — skip live streams.** `grab_video_info()` now returns yt-dlp's `live_status`, and
  `scrap_audio()` returns `None` early when it is `is_live`, `is_upcoming` or `post_live`. No DB record is written,
  so the video is picked up on a later run once it's a normal VOD. This no longer depends on the live-ring UI check.
- **`scraper/utils.py` — kill the whole process group on timeout.** New `_run_killable()` runs yt-dlp with
  `start_new_session=True` and, on timeout, `os.killpg(..., SIGKILL)`s the group (yt-dlp + ffmpeg), then re-raises
  `TimeoutExpired`. `_run_yt_dlp()` uses it instead of `subprocess.run`.
- **`scraper/main.py` — manual kill covers ffmpeg.** `kill_all()` now also `pkill`s `ffmpeg`.

### Verification
Run inside the rebuilt container:
- `grab_video_info('…FpbsnK5EJBk')` → `live_status = is_live`; `scrap_audio()` returned `None` without starting a download.
- `_run_killable(['bash','-c','sleep 100 & sleep 100'], 2)` → raised `TimeoutExpired` and both processes were killed.

### Known remaining risks (not addressed)
- **No backoff on failed rips.** A VOD whose download legitimately exceeds 10 minutes is killed cleanly but retried
  every run, re-downloading up to 10 minutes' worth each time. Not observed in the logs (all 600s timeouts were
  live streams). Possible fix: skip a video for a few hours after it fails, or raise the timeout.
- **Zombie processes.** The container has no init, so killed/orphaned children (including old `chrome`
  processes) remain as `<defunct>` entries. Harmless but they accumulate. Fix: `init: true` on the `webapp`
  service in `docker-compose.yml`.
- **Live-ring selectors are broken.** `CSS selectors timed out — trying JS fallback` appears for most channels.
  The live skip above makes this non-dangerous, but the page-object selectors likely need updating.
- **Playwright hang.** A hung scrape would hold `_scrape_lock` and block later runs (no network impact).
  Unlikely, since Playwright calls have their own timeouts.
