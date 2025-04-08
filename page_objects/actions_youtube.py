from page_objects.home_page import HomePage

from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import StaleElementReferenceException

from enums import Speed
from enums import Type
import logging
import utils
import os
import time


class ActionYoutube:
  
    config = utils.load_config("config.json")
    driver_wait_sec = config["WEBDRIVER_TIMEOUT"]
    screenshot_path = config["SCREENCAP_PATH"]

    def __init__(self, driver,db_conn):
        self.logger = logging.getLogger(__name__) 
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s -  BOT - %(levelname)s: %(message)s')
        file_handler = logging.FileHandler('bot.log')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.propagate = False

        self.driver = driver
        self.db_conn = db_conn

        self.home_page = HomePage(self.logger,driver,db_conn)


    def scrap_video_audio(self): 
        self.home_page.navigate_to_channel_page("@RetropolisGreece",Type.STREAM.value)
        time.sleep(10)

   