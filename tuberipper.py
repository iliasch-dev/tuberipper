from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from page_objects.actions_youtube import ActionYoutube

import selenium
import random
import logging
import tempfile
import time
import db_psql_client
import argparse
import utils


logging.basicConfig(filename='tuberipper.log', level=logging.INFO, format='%(asctime)s - TUBERIPPER MAIN - %(levelname)s: %(message)s')
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
    # Create a temporary directory for Chrome's user data
    user_data_dir = tempfile.mkdtemp(".selenium")
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")  # Set the newly created directory as gthe user data directory
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-external-intent-requests")
    chrome_options.add_argument("--disable-web-security") 
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    #chrome_options.add_argument("--headless")
    chrome_prefs = {"profile.managed_default_content_settings.images": 1} #use 2 for blocking and 3 to block 3rd party
    chrome_options.add_experimental_option("prefs", chrome_prefs)    
    chrome_options.add_argument("--enable-javascript")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    if chromedriver_path!="":
        service = Service(executable_path=chromedriver_path ) 
        driver = webdriver.Chrome(service=service,options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)
    return driver

def main():
    #random delay
    logger.info(f"Tuberipper initialized")
    #init all things
    db_conn = db_psql_client.init_database()
    driver = _initialize_stealthy_driver()
    capabilities = driver.capabilities
    logger.info(f"Selenium version: {selenium.__version__}")
    logger.info("Chromedriver version: %s", capabilities['chrome']['chromedriverVersion'])
  
    #business as usual
    # x_actions = ActionX(driver,db_conn,llm_clients) 
    youtube_actions = ActionYoutube(logger,driver,db_conn) 
    youtube_actions.scrap_video_audio()

    # x_actions.login()
    # x_actions.post()

    #exit actions
    db_conn.close()
    driver.quit()
    logger.info("That's all folks!")

 
if __name__ == "__main__":

    main()

