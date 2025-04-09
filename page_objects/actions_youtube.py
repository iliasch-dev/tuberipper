from page_objects.home_page import HomePage

from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import StaleElementReferenceException

from enums import Speed
from enums import Type
from enums import Format
import logging
import utils
import os
import time
import db_psql_client



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

        channels = db_psql_client.get_all_channels(self.db_conn)
        if channels is not None:
            for channel in channels:
                if(channel['scrap_streams']):
                    self.home_page.navigate_to_channel_page(channel['channel'],Type.STREAM.value)
                    self.home_page.is_live_tab_dispalyed()
                    video_id = self.home_page.get_first_thumbnail()
                    self.home_page.click_first_thumbnail()
                    if not db_psql_client.check_video_id_exists(self.db_conn,video_id, Format.AUDIO.value):
                        url = self.config["YOUTUBE_URL"]+"watch?v="+video_id
                        result = utils.scrap_audio(url,channel['channel'])
                        if result is not None and all(value not in [None, "", [], {}, set()] for value in result.values()):
                            logging.info("Saving in DB")
                if(channel['scrap_videos']):           
                    self.home_page.navigate_to_channel_page(channel['channel'],Type.VIDEO.value)
                    self.home_page.is_videos_tab_dispalyed()
                    video_id = self.home_page.get_first_thumbnail()
                    self.home_page.click_first_thumbnail()
                    if not db_psql_client.check_video_id_exists(self.db_conn,video_id, Format.AUDIO.value):
                        url = self.config["YOUTUBE_URL"]+"watch?v="+video_id
                        result = utils.scrap_audio(url,channel['channel'])
                        if result is not None and all(value not in [None, "", [], {}, set()] for value in result.values()):
                            logging.info("Saving in DB")
                time.sleep(5)
        else:
            print("No channels found or an error occurred.")
        

   