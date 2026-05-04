from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from apscheduler.schedulers.background import BackgroundScheduler

from .page_objects.actions_youtube import ActionYoutube
from . import db_client
from . import utils

import selenium
import random
import logging
import os
import shutil
import tempfile
from datetime import datetime


log_path = os.environ.get('LOG_PATH', 'tuberipper.log')
if os.path.dirname(log_path):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(filename=log_path, level=logging.INFO,
                    format='%(asctime)s - TUBERIPPER MAIN - %(levelname)s: %(message)s',
                    force=True)
logger = logging.getLogger(__name__)

config = utils.load_config("config.json")


def _initialize_stealthy_driver():
    chromedriver_path = config["CHROMEDRIVER_PATH"]
    # prefer system chromedriver (Docker) over config path if it doesn't exist locally
    if not chromedriver_path or not os.path.exists(chromedriver_path):
        chromedriver_path = shutil.which('chromedriver') or ''
    logger.info("Initializing chromedriver: %s", chromedriver_path or 'auto')
    chrome_options = Options()
    # point at system chromium binary when present (Docker apt install)
    chromium_bin = shutil.which('chromium') or shutil.which('chromium-browser')
    if chromium_bin:
        chrome_options.binary_location = chromium_bin
    user_agents = []
    with open('user_agents.txt', 'r') as file:
        for line in file:
            user_agents.append(line.strip())
    user_data_dir = tempfile.mkdtemp(suffix=".selenium")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument(f"--crash-dumps-dir={user_data_dir}")
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-external-intent-requests")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_prefs = {"profile.managed_default_content_settings.images": 1}
    chrome_options.add_experimental_option("prefs", chrome_prefs)
    chrome_options.add_argument("--enable-javascript")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("window-size=1920,1080")
    if chromedriver_path:
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)
    return driver, user_data_dir


def _run_scrape():
    logger.info("Starting scrape run")
    db_conn = db_client.init_database()
    driver = None
    user_data_dir = None
    try:
        driver, user_data_dir = _initialize_stealthy_driver()
        logger.info(f"Selenium version: {selenium.__version__}")
        logger.info("Chromedriver version: %s", driver.capabilities['chrome']['chromedriverVersion'])
        youtube_actions = ActionYoutube(logger, driver, db_conn)
        youtube_actions.scrap_video_audio()
    finally:
        db_conn.close()
        if driver:
            driver.quit()
        if user_data_dir:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        logger.info("Scrape run complete")


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
                _run_scrape()
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

    logger.info(f"Scheduler started — interval: {schedule['interval_minutes']} minutes, enabled: {schedule['enabled']}")
    scheduler.start()
    return scheduler
