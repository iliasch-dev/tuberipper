from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import utils
from enums import Speed
from enums import Type

class HomePage:

    config = utils.load_config("config.json")
    driver_wait_sec = config["WEBDRIVER_TIMEOUT"]
    screenshot_path = config["SCREENCAP_PATH"]

    def __init__(self, logger, driver,db_conn):
        self.logger = logger
        self.driver = driver
        self.db_conn = db_conn

        self.reject_cookies_button = (By.XPATH, '//button[.//span[text()="Reject all"]]')
        self.cookies_modal_title = (By.CSS_SELECTOR, "yt-formatted-string.style-scope.ytd-consent-bump-v2-lightbox")

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
        url = self.config["YOUTUBE_URL"]
        self.logger.info(f"Accessing Youtube url:{url}" )
        try: 
            self.driver.get(url)
            self.is_cookies_modal_displayed()
        except Exception as e: 
            self.logger.error(f"Error navigating to Youtube: {e}") 
            
        
    def navigate_to_channel_page(self,channel,type):      
        url = f"{self.config["YOUTUBE_URL"]}/{channel}/{type}"
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
        

    def click_reject_button(self):
        self.logger.info("Clicking Reject cookies button")
        reject_button = WebDriverWait(self.driver, self.driver_wait_sec).until(EC.element_to_be_clickable(self.reject_cookies_button))  
        utils.highlight_element(self.driver, reject_button)
        try: 
            reject_button.click()
            self.is_displayed()
        except Exception as e: 
            self.logger.error(f"Error navigating to Login Modal: {e}")
        utils.randomSleep(Speed.FAST)

