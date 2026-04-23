from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import time
import re

from .. import utils
from ..enums import Speed, Type


class HomePage:

    config = utils.load_config("config.json")
    driver_wait_sec = config['WEBDRIVER_TIMEOUT']
    screenshot_path = config['SCREENCAP_PATH']

    # YouTube changes tab markup often; use several strategies (class, paper-tab, tab link).
    _LIVE_TAB_LOCATORS = (
        (By.XPATH, "//*[contains(@class,'yt-tab-shape__tab')][normalize-space()='Live']"),
        (By.XPATH, "//tp-yt-paper-tab[.//text()[normalize-space()='Live']]"),
        (By.XPATH, "//a[contains(@href,'/streams')][not(contains(@href,'/shorts'))]"),
    )
    _VIDEOS_TAB_LOCATORS = (
        (By.XPATH, "//*[contains(@class,'yt-tab-shape__tab')][normalize-space()='Videos']"),
        (By.XPATH, "//tp-yt-paper-tab[.//text()[normalize-space()='Videos']]"),
        (By.XPATH, "//a[contains(@href,'/videos')][not(contains(@href,'/shorts'))]"),
    )

    # Consent UI varies by region/locale and A/B tests; banner may not appear at all.
    _REJECT_COOKIE_LOCATORS = (
        (By.XPATH, "//ytd-consent-bump-v2-lightbox//button[.//*[normalize-space()='Reject all']]"),
        (By.XPATH, "//ytd-consent-bump-v2-lightbox//button[contains(normalize-space(.), 'Reject all')]"),
        (By.XPATH, "//button[.//span[normalize-space()='Reject all']]"),
        (By.XPATH, "//tp-yt-paper-dialog//button[contains(., 'Reject all')]"),
        (By.XPATH, "//*[@role='dialog']//button[.//*[contains(normalize-space(.), 'Reject all')]]"),
    )
    _ACCEPT_COOKIE_LOCATORS = (
        (By.XPATH, "//ytd-consent-bump-v2-lightbox//button[.//*[normalize-space()='Accept all']]"),
        (By.XPATH, "//ytd-consent-bump-v2-lightbox//button[contains(normalize-space(.), 'Accept all')]"),
        (By.XPATH, "//button[.//span[normalize-space()='Accept all']]"),
        (By.XPATH, '//button[.//span[text()="Acccept all"]]'),
        (By.XPATH, "//tp-yt-paper-dialog//button[contains(., 'Accept all')]"),
    )
    _YOUTUBE_SHELL_LOCATORS = (
        (By.CSS_SELECTOR, "ytd-app"),
        (By.CSS_SELECTOR, "ytd-masthead"),
        (By.CSS_SELECTOR, "#masthead-container"),
    )

    # Channel /streams and /videos: tiles lazy-load; img class names change; prefer grid + watch links.
    _CHANNEL_GRID_LOCATORS = (
        (By.CSS_SELECTOR, "#primary ytd-rich-grid-media a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "ytd-rich-grid-media a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "ytd-grid-video-renderer a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "ytd-rich-grid-media"),
        (By.CSS_SELECTOR, "ytd-grid-video-renderer"),
        (By.CSS_SELECTOR, "a#thumbnail img.ytCoreImageHost"),
        (By.CSS_SELECTOR, "ytd-rich-grid-media a#thumbnail img"),
        (By.CSS_SELECTOR, "a#thumbnail img"),
    )
    _FIRST_VIDEO_LINK_LOCATORS = (
        (By.CSS_SELECTOR, "#primary ytd-rich-grid-media a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "ytd-rich-grid-media a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "ytd-grid-video-renderer a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "#primary a#thumbnail[href*='watch?v=']"),
        (By.CSS_SELECTOR, "a#thumbnail[href*='watch?v=']"),
    )

    def __init__(self, logger, driver, db_conn):
        self.logger = logger
        self.driver = driver
        self.db_conn = db_conn

        self.first_column_row_thumbnail = (By.CSS_SELECTOR, "a#thumbnail img.ytCoreImageHost")
        self.sign_in_button = (By.CSS_SELECTOR, 'span[role="text"]:contains("Sign in")')
        self.live_ring = (By.CLASS_NAME, "yt-spec-avatar-shape--live-ring")

    def is_displayed(self):
        try:
            if self._youtube_shell_ready():
                self.logger.info("Navigated to Youtube Homepage as anonymous user")
                return True
            self.logger.error("YouTube page shell not detected")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp() + "_homepage_display_failed.png")
            return False
        except Exception as e:
            self.logger.error(f"Error displaying Youtube page: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp() + "_homepage_display_failed.png")
            return False

    def navigate_to_youtube(self):
        url = self.config['YOUTUBE_URL']
        self.logger.info(f"Accessing Youtube url:{url}")
        try:
            self.driver.get(url)
        except Exception as e:
            self.logger.error(f"Error navigating to Youtube: {e}")

    def navigate_to_channel_page(self, channel, type):
        url = f"{self.config['YOUTUBE_URL']}{channel}/{type}"
        self.logger.info(f"Accessing Youtube channel url:{url}")
        try:
            self.driver.get(url)
        except Exception as e:
            self.logger.error(f"Error navigating to Youtube: {e}")

    def _nudge_lazy_channel_content(self):
        try:
            self.driver.execute_script(
                "window.scrollTo(0, Math.min(1500, Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) || 1500));"
            )
            time.sleep(0.9)
        except Exception:
            pass

    def _wait_for_channel_grid(self):
        budget = float(self.driver_wait_sec)
        start = time.monotonic()
        for attempt in range(5):
            remaining = budget - (time.monotonic() - start)
            if remaining < 2:
                break
            chunk = min(12, remaining)
            # Short per-locator waits so every fallback selector gets a turn within the chunk.
            if self._wait_for_any_locator(self._CHANNEL_GRID_LOCATORS, chunk, per_try_sec=4):
                return
            self.logger.info("Channel grid not ready yet; scroll nudge %s/5", attempt + 1)
            self._nudge_lazy_channel_content()
        raise TimeoutException("Channel video grid did not become visible in time")

    def _wait_for_any_locator(self, locators, total_timeout_sec, per_try_sec=8):
        deadline = time.monotonic() + float(total_timeout_sec)
        for by, locator in locators:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                WebDriverWait(self.driver, min(per_try_sec, remaining)).until(
                    EC.visibility_of_element_located((by, locator))
                )
                return True
            except Exception:
                continue
        return False

    def _first_clickable(self, locators, total_timeout_sec, per_try_sec=4):
        deadline = time.monotonic() + float(total_timeout_sec)
        for by, locator in locators:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return WebDriverWait(self.driver, max(1.0, min(per_try_sec, remaining))).until(
                    EC.element_to_be_clickable((by, locator))
                )
            except Exception:
                continue
        return None

    def _first_visible_video_link(self, timeout_sec=None):
        t = float(timeout_sec if timeout_sec is not None else self.driver_wait_sec)
        deadline = time.monotonic() + t
        for by, locator in self._FIRST_VIDEO_LINK_LOCATORS:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return WebDriverWait(self.driver, max(1.0, min(10, remaining))).until(
                    EC.visibility_of_element_located((by, locator))
                )
            except Exception:
                continue
        return None

    def _youtube_shell_ready(self, timeout_sec=None):
        t = float(timeout_sec if timeout_sec is not None else min(25, float(self.driver_wait_sec)))
        return self._wait_for_any_locator(self._YOUTUBE_SHELL_LOCATORS, t, per_try_sec=8)

    def is_live_tab_dispalyed(self):
        try:
            url = (self.driver.current_url or "").lower()
            if "/streams" in url:
                self.logger.info("Already on /streams; waiting for channel grid")
                self._wait_for_channel_grid()
                self.logger.info("Live streams grid loaded")
                return True
            if self._wait_for_any_locator(self._LIVE_TAB_LOCATORS, self.driver_wait_sec):
                self.logger.info("Live tab strip matched")
                return True
            self.logger.info("Live tab strip not found; waiting for channel grid")
            self._wait_for_channel_grid()
            self.logger.info("Live content grid loaded")
            return True
        except Exception as e:
            self.logger.error(f"Error displaying Live Tab: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp() + "_homepage_live_tab_navigation_failed.png")
            return False

    def is_videos_tab_dispalyed(self):
        try:
            url = (self.driver.current_url or "").lower()
            if "/videos" in url:
                self.logger.info("Already on /videos; waiting for channel grid")
                self._wait_for_channel_grid()
                self.logger.info("Videos grid loaded")
                return True
            if self._wait_for_any_locator(self._VIDEOS_TAB_LOCATORS, self.driver_wait_sec):
                self.logger.info("Videos tab strip matched")
                return True
            self.logger.info("Videos tab strip not found; waiting for channel grid")
            self._wait_for_channel_grid()
            self.logger.info("Videos grid loaded")
            return True
        except Exception as e:
            self.logger.error(f"Error displaying Videos Tab: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp() + "_homepage_videos_tab_navigation_failed.png")
            return False

    def get_first_thumbnail(self):
        try:
            video_id = None
            anchor = self._first_visible_video_link()
            if anchor is not None:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", anchor)
                utils.highlight_element(self.driver, anchor)
                href = anchor.get_attribute("href") or ""
                m = re.search(r"[?&]v=([^&]+)", href)
                if m:
                    video_id = m.group(1)
                    self.logger.info("YouTube Video ID (from thumbnail link): %s", video_id)
            if video_id:
                self.logger.info("First channel video tile resolved")
                return video_id

            thumbnail = WebDriverWait(self.driver, float(self.driver_wait_sec)).until(
                EC.visibility_of_element_located(self.first_column_row_thumbnail)
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", thumbnail)
            utils.highlight_element(self.driver, thumbnail)
            img_src = thumbnail.get_attribute("src") or ""
            match = re.search(r"/vi/([^/]+)/", img_src)
            if match:
                video_id = match.group(1)
                self.logger.info("YouTube Video ID (from image src): %s", video_id)
            else:
                self.logger.error("Video ID not found in src %s", img_src)
            self.logger.info("First Thumbnail displayed")
            return video_id
        except Exception as e:
            self.logger.error(f"Error displaying First thumbnail: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp() + "_homepage_first_thumbnail_display_failed.png")

    def click_first_thumbnail(self):
        try:
            thumbnail = WebDriverWait(self.driver, self.driver_wait_sec).until(
                EC.visibility_of_element_located(self.first_column_row_thumbnail)
            )
            utils.highlight_element(self.driver, thumbnail)
            thumbnail.click()
            self.logger.info(f"Clicked First Thumbnail")
        except Exception as e:
            self.logger.error(f"Error clicking First thumbnail: {e}")
            self.driver.save_screenshot(self.screenshot_path + utils.timestamp() + "_homepage_first_thumbnail_click_failed.png")

    def click_accept_button(self):
        self.logger.info("Clicking Accept cookies if consent dialog is shown")
        btn = self._first_clickable(
            self._ACCEPT_COOKIE_LOCATORS,
            min(20, float(self.driver_wait_sec)),
        )
        if btn:
            try:
                utils.highlight_element(self.driver, btn)
                btn.click()
                self.logger.info("Accepted cookie consent")
                utils.randomSleep(Speed.FAST)
            except Exception as e:
                self.logger.warning(f"Accept cookies click failed: {e}")
        else:
            self.logger.info("No Accept-all cookie button found; continuing")
        self.is_displayed()

    def click_reject_button(self):
        self.logger.info("Rejecting cookie consent if dialog is shown")
        btn = self._first_clickable(
            self._REJECT_COOKIE_LOCATORS,
            min(20, float(self.driver_wait_sec)),
        )
        if btn:
            try:
                utils.highlight_element(self.driver, btn)
                btn.click()
                self.logger.info("Dismissed cookie consent (reject)")
                utils.randomSleep(Speed.FAST)
            except Exception as e:
                self.logger.warning(f"Reject cookies click failed: {e}")
        else:
            self.logger.info("No cookie consent dialog to dismiss")
        self.is_displayed()

    def is_live_ring_present(self):
        try:
            live_ring = WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located(self.live_ring)
            )
            if live_ring.is_displayed():
                self.logger.info("Live-Ring displayed! Seems like a live-stream is in progress!")
                return True
            return False
        except Exception:
            return False
