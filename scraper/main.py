from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from apscheduler.schedulers.blocking import BlockingScheduler

from .page_objects.actions_youtube import ActionYoutube
from . import db_client
from . import utils

import selenium
import random
import logging
import os
import tempfile
from datetime import datetime


log_path = os.environ.get('LOG_PATH', 'tuberipper.log')
os.makedirs(os.path.dirname(log_path), exist_ok=True) if os.path.dirname(log_path) else None
logging.basicConfig(filename=log_path, level=logging.INFO, format='%(asctime)s - TUBERIPPER MAIN - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

config = utils.load_config("config.json")


def _initialize_stealthy_driver():
    chromedriver_path = config["CHROMEDRIVER_PATH"]
    logger.info("Initializing chromedriver")
    chrome_options = Options()
    user_agents = []
    with open('user_agents.txt', 'r') as file:
        for line in file:
            user_agents.append(line.strip())
    user_data_dir = tempfile.mkdtemp(".selenium")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-external-intent-requests")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    # chrome_options.add_argument("--headless")
    chrome_prefs = {"profile.managed_default_content_settings.images": 1}
    chrome_options.add_experimental_option("prefs", chrome_prefs)
    chrome_options.add_argument("--enable-javascript")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("window-size=1920,1080")
    if chromedriver_path != "":
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)
    return driver


def _run_scrape():
    logger.info("Starting scrape run")
    db_conn = db_client.init_database()
    driver = _initialize_stealthy_driver()
    try:
        logger.info(f"Selenium version: {selenium.__version__}")
        logger.info("Chromedriver version: %s", driver.capabilities['chrome']['chromedriverVersion'])
        youtube_actions = ActionYoutube(logger, driver, db_conn)
        youtube_actions.scrap_video_audio()
    finally:
        db_conn.close()
        driver.quit()
        logger.info("Scrape run complete")


def main():
    logger.info("Tuberipper scheduler starting")

    db_conn = db_client.init_database()
    schedule = db_client.get_schedule(db_conn)
    db_conn.close()

    scheduler = BlockingScheduler()

    def job():
        db_conn = db_client.init_database()
        schedule = db_client.get_schedule(db_conn)
        db_conn.close()

        if schedule['enabled']:
            _run_scrape()
        else:
            logger.info("Scraper is disabled — skipping run")

        # Re-read interval in case it was changed via the webapp
        db_conn = db_client.init_database()
        updated = db_client.get_schedule(db_conn)
        db_conn.close()
        scheduler.reschedule_job('scrape', trigger='interval', minutes=updated['interval_minutes'])
        logger.info(f"Next run in {updated['interval_minutes']} minutes")

    scheduler.add_job(
        job,
        trigger='interval',
        minutes=schedule['interval_minutes'],
        id='scrape',
        next_run_time=datetime.now()  # run immediately on startup
    )

    logger.info(f"Scheduler started — interval: {schedule['interval_minutes']} minutes, enabled: {schedule['enabled']}")
    scheduler.start()


if __name__ == "__main__":
    main()
