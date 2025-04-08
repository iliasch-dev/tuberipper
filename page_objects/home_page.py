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

        self.login_button_locator = (By.CSS_SELECTOR, "div[data-test-id='simple-login-button']")
        self.unath_header_logo_locator = (By.CSS_SELECTOR, "div[data-test-id='unauth-header-logo']")

    def is_displayed(self):
        try:  
            WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.login_button_locator))
            WebDriverWait(self.driver, self.driver_wait_sec).until(EC.visibility_of_element_located(self.unath_header_logo_locator))         
            self.logger.info("Navigated to Youtube Homepage")
            return True
        except Exception as e:
            self.logger.error(f"Error displaying Youtube page: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp()+"_pinterest_homepage_display_failed.png")
            return False
        
    def navigate_to_channel_page(self,channel,type):      
        url = f"{self.config["YOUTUBE_URL"]}/{channel}/{type}"
        self.logger.info(f"Accessing Youtube url:{url}" )
        try: 
            self.driver.get(url)
            self.is_displayed()
        except Exception as e: 
            self.logger.error(f"Error navigating to Youtube: {e}") 


