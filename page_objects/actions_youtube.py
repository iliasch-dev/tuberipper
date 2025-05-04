from page_objects.home_page import HomePage

from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import StaleElementReferenceException

from enums import Speed
from enums import Type
from enums import Ytl_Dlp_Clients
from enums import Format
import random
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
        ytl_dlp_client = random.choice(list(Ytl_Dlp_Clients)).value
        logging.info(f"Picking YT-DLP client: {ytl_dlp_client}")
        if channels is not None:
            for channel in channels: 
                logging.info(f"==========>Checking channel:{channel['channel']}<==========")     
                if(channel['scrap_streams']):
                    self.home_page.navigate_to_channel_page(channel['channel'],Type.STREAM.value)
                    self.home_page.is_live_tab_dispalyed()
                    if not self.home_page.is_live_ring_present():
                        video_id = self.home_page.get_first_thumbnail()
                        #self.home_page.click_first_thumbnail()
                        if not db_psql_client.check_video_id_exists(self.db_conn,video_id, Format.AUDIO.value):
                            logging.info(f"Stream with video id:{video_id} not scrapped, proceeding to scrap stream")
                            url = self.config["YOUTUBE_URL"]+"watch?v="+video_id
                            result = utils.scrap_audio(url,channel['channel'],ytl_dlp_client)                    
                            if result is not None and all(value not in [None, "", [], {}, set()] for value in result.values()):
                                logging.info("Saving rip data in DB")
                                db_psql_client.insert_rip_record(self.db_conn, channel['channel'], result['video_title'], result['video_duration'], Format.AUDIO.value, "STREAM", result['video_thumbnail_url'],video_id,result['audio_filename'])
                                logging.info(f"Sending pushover: title={result['video_title']}, image={result['video_thumbnail_url']}")
                                utils.send_pushover_notification(
                                    message=f"{channel['channel']} - {result['video_title']}",
                                    image_url=result['video_thumbnail_url']
                                )
                        else:
                            logging.info(f"No new LIVE-STREAMS found to scrap for channel:{channel['channel']}")
                if(channel['scrap_videos']):           
                    self.home_page.navigate_to_channel_page(channel['channel'],Type.VIDEO.value)
                    self.home_page.is_videos_tab_dispalyed()
                    video_id = self.home_page.get_first_thumbnail()
                    #self.home_page.click_first_thumbnail()
                    if not db_psql_client.check_video_id_exists(self.db_conn,video_id, Format.AUDIO.value):
                        logging.info(f"Video with video id:{video_id} not scrapped, proceeding to scrap video")
                        url = self.config["YOUTUBE_URL"]+"watch?v="+video_id
                        result = utils.scrap_audio(url,channel['channel'],ytl_dlp_client)                     
                        if result is not None and all(value not in [None, "", [], {}, set()] for value in result.values()):
                            logging.info("Saving rip data in DB")
                            db_psql_client.insert_rip_record(self.db_conn,  channel['channel'], result['video_title'], result['video_duration'], Format.AUDIO.value, "VIDEO", result['video_thumbnail_url'],video_id,result['audio_filename'])
                            logging.info(f"Sending pushover: title={result['video_title']}, image={result['video_thumbnail_url']}")
                            utils.send_pushover_notification(
                                message=f"{channel['channel']} - {result['video_title']}",
                                image_url=result['video_thumbnail_url']
                            )
                    else:
                        logging.info(f"No new VIDEOS found to scrap for channel:{channel['channel']}")
                time.sleep(5)
        else:
            logging.error("No channels found or an error occurred.")
        

   