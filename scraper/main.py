from playwright.sync_api import sync_playwright

from apscheduler.schedulers.background import BackgroundScheduler

from .page_objects.actions_youtube import ActionYoutube
from . import db_client
from . import utils
from .enums import Format

import importlib.metadata
import random
import logging
import os
import threading
import subprocess
from datetime import datetime, timedelta


log_path = os.environ.get('LOG_PATH', 'tuberipper.log')
if os.path.dirname(log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(filename=log_path, level=logging.INFO,
                    format='%(asctime)s - TUBERIPPER MAIN - %(levelname)s: %(message)s',
                    force=True)
logger = logging.getLogger(__name__)

config = utils.load_config("config.json")

_scrape_lock = threading.Lock()


def _launch_browser(pw):
    with open('user_agents.txt', 'r') as file:
        user_agents = [line.strip() for line in file]
    browser = pw.chromium.launch(
        channel="chromium",
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-notifications",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
        ],
    )
    context = browser.new_context(
        user_agent=random.choice(user_agents),
        viewport={"width": 1920, "height": 1080},
    )
    context.set_default_timeout(float(config["WEBDRIVER_TIMEOUT"]) * 1000)
    page = context.new_page()
    return browser, context, page


def is_scraping():
    return _scrape_lock.locked()


def kill_all():
    """Force-terminate any running Playwright/Chromium, yt-dlp and ffmpeg processes.
    The scrape's own try/finally releases _scrape_lock once its Playwright/subprocess
    calls raise as a result — this does not touch the lock directly."""
    killed_any = False
    for pattern in ("ms-playwright", "yt-dlp", "ffmpeg"):
        result = subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True)
        if result.returncode == 0:
            killed_any = True
    if killed_any:
        logger.warning("Manual kill triggered — terminated running Playwright/yt-dlp/ffmpeg processes")
        return {"ok": True, "message": "Killed running scraper process(es)"}
    logger.info("Manual kill triggered — no matching processes were running")
    return {"ok": False, "message": "Nothing was running"}


def _do_scrape(action):
    db_conn = db_client.init_database()
    try:
        with sync_playwright() as pw:
            browser, context, page = _launch_browser(pw)
            try:
                logger.info(f"Playwright version: {importlib.metadata.version('playwright')}")
                logger.info("Chromium version: %s", browser.version)
                youtube_actions = ActionYoutube(logger, page, db_conn)
                action(youtube_actions)
            finally:
                context.close()
                browser.close()
    finally:
        db_conn.close()


def _run_scrape():
    logger.info("Starting scrape run")
    if not _scrape_lock.acquire(blocking=False):
        logger.warning("Skipping scheduled scrape run — a scrape is already in progress")
        return False
    try:
        _do_scrape(lambda ya: ya.scrap_video_audio())
        return True
    finally:
        _scrape_lock.release()
        logger.info("Scrape run complete")


def trigger_channel_scrape(channel_id):
    """Kick off a one-off scrape for a single channel in a background thread.
    Returns (started: bool, message: str) immediately, without waiting for the scrape."""
    if not _scrape_lock.acquire(blocking=False):
        return False, "A scrape is already running — try again shortly"

    def worker():
        try:
            db_conn = db_client.init_database()
            channel = db_client.get_channel_by_id(db_conn, channel_id)
            db_conn.close()
            if channel is None:
                logger.warning(f"Manual scrape requested for unknown channel id {channel_id}")
                return
            logger.info(f"Starting manual scrape for channel:{channel['channel']}")
            _do_scrape(lambda ya: ya.scrap_one_channel(channel))
            logger.info(f"Manual scrape complete for channel:{channel['channel']}")
        except Exception as e:
            logger.error(f"Unhandled error in manual channel scrape: {utils.clean_error(e)}")
        finally:
            _scrape_lock.release()

    threading.Thread(target=worker, daemon=True).start()
    return True, "Scrape started"


def trigger_url_scrape(url):
    """Rip a single YouTube URL on demand (no Playwright — straight to yt-dlp) in a
    background thread. Returns (started: bool, message: str) immediately."""
    video_id = utils.extract_video_id(url)
    if not video_id:
        return False, "Not a recognisable YouTube video URL"
    watch_url = config["YOUTUBE_URL"] + "watch?v=" + video_id

    # Manual rips deliberately bypass the already-ripped check (so an accidentally
    # deleted file can be re-ripped); the existing row is refreshed instead of duplicated.
    db_conn = db_client.init_database()
    try:
        already_ripped = db_client.check_video_id_exists(db_conn, video_id, Format.AUDIO.value)
    finally:
        db_conn.close()

    if not _scrape_lock.acquire(blocking=False):
        return False, "A scrape is already running — try again shortly"

    def worker():
        try:
            logger.info(f"==========>Manual URL {'re-rip' if already_ripped else 'rip'} requested: {watch_url}<==========")
            result = utils.scrap_audio(watch_url)
            if result is None or any(value in [None, "", [], {}, set()] for value in result.values()):
                logger.error(f"Manual URL rip failed for {watch_url}")
                return
            db_conn = db_client.init_database()
            try:
                logger.info("Saving rip data in DB")
                save = db_client.update_rip_record if already_ripped else db_client.insert_rip_record
                save(
                    db_conn, result['channel'], result['video_title'],
                    result['video_duration'], Format.AUDIO.value, result['media_type'],
                    result['video_thumbnail_url'], video_id, result['audio_filename']
                )
            finally:
                db_conn.close()
            logger.info(f"Sending pushover: title={result['video_title']}, image={result['video_thumbnail_url']}")
            utils.send_pushover_notification(
                message=f"{result['channel']} - {result['video_title']}",
                image_url=result['video_thumbnail_url']
            )
            logger.info(f"Manual URL rip complete for {watch_url}")
        except Exception as e:
            logger.error(f"Unhandled error in manual URL rip: {utils.clean_error(e)}")
        finally:
            _scrape_lock.release()

    threading.Thread(target=worker, daemon=True).start()
    return True, f"{'Re-rip' if already_ripped else 'Rip'} started for {video_id}"


def cleanup_staging():
    """Wipe RIPS_PATH (leftover .part downloads, duration-mismatch rejects, …).
    Holds _scrape_lock so it can never delete a file a running rip is still writing.
    Returns (ok: bool, message: str)."""
    if not _scrape_lock.acquire(blocking=False):
        return False, "A scrape is running — staging cleanup skipped"
    try:
        before = utils.staging_size_bytes()
        logger.info(f"Cleaning staging directory {config['RIPS_PATH']} ({utils.human_size(before)})")
        utils.clear_directory_contents(config["RIPS_PATH"])
        return True, f"Freed {utils.human_size(before)} from staging"
    except Exception as e:
        logger.error(f"Unhandled error in staging cleanup: {utils.clean_error(e)}")
        return False, "Staging cleanup failed — see log"
    finally:
        _scrape_lock.release()


def start_scheduler():
    logger.info("Tuberipper scheduler starting")

    db_conn = db_client.init_database()
    schedule = db_client.get_schedule(db_conn)
    db_conn.close()

    scheduler = BackgroundScheduler()

    def job():
        try:
            db_conn = db_client.init_database()
            schedule = db_client.get_schedule(db_conn)
            db_conn.close()

            if schedule['enabled']:
                ran = _run_scrape()
                if ran:
                    db_conn2 = db_client.init_database()
                    db_client.increment_run_count(db_conn2)
                    db_conn2.close()
            else:
                logger.info("Scraper is disabled — skipping run")

            db_conn = db_client.init_database()
            updated = db_client.get_schedule(db_conn)
            db_conn.close()
            scheduler.reschedule_job('scrape', trigger='interval', minutes=updated['interval_minutes'])
            logger.info(f"Next run in {updated['interval_minutes']} minutes")
        except Exception as e:
            logger.error(f"Unhandled error in scheduler job: {utils.clean_error(e)}")

    scheduler.add_job(
        job,
        trigger='interval',
        minutes=schedule['interval_minutes'],
        id='scrape',
        next_run_time=datetime.now()
    )

    def staging_job():
        ok, message = cleanup_staging()
        if ok:
            logger.info(f"Daily staging cleanup: {message}")
        else:
            # A rip was in progress — don't wait a whole day, try again in an hour.
            retry_at = datetime.now() + timedelta(hours=1)
            scheduler.modify_job('staging_cleanup', next_run_time=retry_at)
            logger.warning(f"Daily staging cleanup: {message}; retrying at {retry_at:%H:%M}")

    scheduler.add_job(staging_job, trigger='cron', hour=4, minute=30, id='staging_cleanup')

    logger.info(f"Scheduler started — interval: {schedule['interval_minutes']} minutes, enabled: {schedule['enabled']}")
    logger.info("Daily staging cleanup scheduled for 04:30")
    scheduler.start()
    return scheduler
