from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import utils
from enums import Speed
from enums import Type
import re

class HomePage:

    config = utils.load_config("config.json")
    driver_wait_sec = config['WEBDRIVER_TIMEOUT']
    screenshot_path = config['SCREENCAP_PATH']

    def __init__(self, logger, driver,db_conn):
        self.logger = logger
        self.driver = driver
        self.db_conn = db_conn

        self.accept_cookies_button = (By.XPATH, '//button[.//span[text()="Acccept all"]]')
        self.reject_cookies_button = (By.XPATH, '//button[.//span[text()="Reject all"]]')
        self.cookies_modal_title = (By.CSS_SELECTOR, "yt-formatted-string.style-scope.ytd-consent-bump-v2-lightbox")
        self.live_tab = (By.XPATH, "//div[contains(@class, 'yt-tab-shape-wiz__tab') and contains(@class, 'yt-tab-shape-wiz__tab--tab-selected') and text()='Live']")
        self.videos_tab = (By.XPATH, "//div[contains(@class, 'yt-tab-shape-wiz__tab') and contains(@class, 'yt-tab-shape-wiz__tab--tab-selected') and text()='Videos']")
        self.first_column_row_thumbnail = (By.CSS_SELECTOR, "yt-image img.yt-core-image")
        self.sign_in_button = (By.CSS_SELECTOR, 'span[role="text"]:contains("Sign in")')

    def is_displayed(self):
        try:  
            WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.reject_cookies_button))
            self.logger.info("Navigated to Youtube Homepage as anonymous user")
            return True
        except Exception as e:
            self.logger.error(f"Error displaying Youtube page: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp()+"_homepage_display_failed.png")
            return False
        
    def navigate_to_youtube(self):
        url = self.config['YOUTUBE_URL']
        self.logger.info(f"Accessing Youtube url:{url}" )
        try: 
            self.driver.get(url)
            self.is_cookies_modal_displayed()
        except Exception as e: 
            self.logger.error(f"Error navigating to Youtube: {e}") 
            
    

    def navigate_to_channel_page(self,channel,type):      
        url = f"{self.config['YOUTUBE_URL']}{channel}/{type}"
        self.logger.info(f"Accessing Youtube channel url:{url}" )
        try: 
            self.driver.get(url)
        except Exception as e: 
            self.logger.error(f"Error navigating to Youtube: {e}") 


    def is_cookies_modal_displayed(self):
        try:  
            WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.reject_cookies_button))
            #WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.cookies_modal_title))
            self.logger.info(f"Cookies modal displayed" )
            return True    
        except Exception as e:
            self.logger.error(f"Error displaying Cookies modal: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp()+"_homepage_cookies_modal_failed.png")
            return False
        
    def is_live_tab_dispalyed(self):
        try:  
            WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.live_tab))
            self.logger.info(f"Live-Tab displayed" )
            return True    
        except Exception as e:
            self.logger.error(f"Error displaying Live Tab: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp()+"_homepage_live_tab_navigation_failed.png")
            return False
        
    def is_videos_tab_dispalyed(self):
        try:  
            WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.videos_tab))
            self.logger.info(f"Video-Tab displayed" )
            return True    
        except Exception as e:
            self.logger.error(f"Error displaying Videos Tab: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp()+"_homepage_videos_tab_navigation_failed.png")
            return False
        

    def get_first_thumbnail(self):
        try:  
            thumbnail = WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.first_column_row_thumbnail))
            utils.highlight_element(self.driver, thumbnail)
            img_src = thumbnail.get_attribute("src")
            match = re.search(r'/vi/([^/]+)/', img_src)
            if match:
                video_id = match.group(1)
                self.logger.info("YouTube Video ID:", video_id)
            else:
                self.logger.error("Video ID not found in src:", img_src)
            self.logger.info(f"First Thumbnail displayed" )
            return video_id    
        except Exception as e:
            self.logger.error(f"Error displaying First thumbnail: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp()+"_homepage_first_thumbnail_display_failed.png")


    def click_first_thumbnail(self):
        try:  
            thumbnail = WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.first_column_row_thumbnail))
            utils.highlight_element(self.driver, thumbnail)
            thumbnail.click()
            self.logger.info(f"Clicked First Thumbnail" )
        except Exception as e:
            self.logger.error(f"Error clicking First thumbnail: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp()+"_homepage_first_thumbnail_click_failed.png")
        

    def click_accept_button(self):
        self.logger.info("Clicking Accept cookies button")
        reject_button = WebDriverWait(self.driver, self.driver_wait_sec).until(EC.element_to_be_clickable(self.accept_cookies_button))  
        utils.highlight_element(self.driver, reject_button)
        try: 
            reject_button.click()
            self.is_displayed()
        except Exception as e: 
            self.logger.error(f"Error clicking Accept button: {e}")
        utils.randomSleep(Speed.FAST)


    def click_reject_button(self):
        self.logger.info("Clicking Reject cookies button")
        try: 
            reject_button = WebDriverWait(self.driver, self.driver_wait_sec).until(EC.element_to_be_clickable(self.reject_cookies_button))  
            utils.highlight_element(self.driver, reject_button)      
            reject_button.click()
            self.is_displayed()
        except Exception as e: 
            self.logger.error(f"Error clicking Reject button: {e}")
        utils.randomSleep(Speed.FAST)

