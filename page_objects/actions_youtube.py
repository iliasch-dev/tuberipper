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

    def __init__(self, logger, driver,db_conn):

        self.driver = driver
        self.db_conn = db_conn
        self.logger = logger

        self.home_page = HomePage(logger,driver,db_conn)


    def scrap_video_audio(self): 
        self.logger.info("Looking for videos to audio-scrap")
        self.home_page.navigate_to_youtube()
        self.home_page.click_reject_button()
        self.home_page.navigate_to_channel_page("@RetropolisGreece",Type.STREAM.value)
        time.sleep(10)
        

   