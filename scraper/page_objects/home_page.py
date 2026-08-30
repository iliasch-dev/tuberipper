from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import time
import re

from .. import utils
from ..enums import Speed, Type


class HomePage:

    config = utils.load_config("config.json")
    driver_wait_sec = config['WEBDRIVER_TIMEOUT']
    screenshot_path = config['SCREENCAP_PATH']

    def __init__(self, logger, page, db_conn):
        self.logger = logger
        self.page = page
        self.db_conn = db_conn

    # YouTube changes tab markup often; use several strategies (class, paper-tab, tab link).
    def _live_tab_locator(self):
        return (
            self.page.locator("xpath=//*[contains(@class,'yt-tab-shape__tab')][normalize-space()='Live']")
            .or_(self.page.locator("xpath=//tp-yt-paper-tab[.//text()[normalize-space()='Live']]"))
            .or_(self.page.locator("xpath=//a[contains(@href,'/streams')][not(contains(@href,'/shorts'))]"))
        )

    def _videos_tab_locator(self):
        return (
            self.page.locator("xpath=//*[contains(@class,'yt-tab-shape__tab')][normalize-space()='Videos']")
            .or_(self.page.locator("xpath=//tp-yt-paper-tab[.//text()[normalize-space()='Videos']]"))
            .or_(self.page.locator("xpath=//a[contains(@href,'/videos')][not(contains(@href,'/shorts'))]"))
        )

    # Consent UI varies by region/locale and A/B tests; banner may not appear at all.
    def _reject_cookie_locator(self):
        return (
            self.page.locator("xpath=//ytd-consent-bump-v2-lightbox//button[.//*[normalize-space()='Reject all']]")
            .or_(self.page.locator("xpath=//ytd-consent-bump-v2-lightbox//button[contains(normalize-space(.), 'Reject all')]"))
            .or_(self.page.locator("xpath=//button[.//span[normalize-space()='Reject all']]"))
            .or_(self.page.locator("xpath=//tp-yt-paper-dialog//button[contains(., 'Reject all')]"))
            .or_(self.page.locator("xpath=//*[@role='dialog']//button[.//*[contains(normalize-space(.), 'Reject all')]]"))
        )

    def _accept_cookie_locator(self):
        return (
            self.page.locator("xpath=//ytd-consent-bump-v2-lightbox//button[.//*[normalize-space()='Accept all']]")
            .or_(self.page.locator("xpath=//ytd-consent-bump-v2-lightbox//button[contains(normalize-space(.), 'Accept all')]"))
            .or_(self.page.locator("xpath=//button[.//span[normalize-space()='Accept all']]"))
            .or_(self.page.locator('xpath=//button[.//span[text()="Acccept all"]]'))
            .or_(self.page.locator("xpath=//tp-yt-paper-dialog//button[contains(., 'Accept all')]"))
        )

    def _youtube_shell_locator(self):
        return self.page.locator("ytd-app, ytd-masthead, #masthead-container")

    # Channel /streams and /videos: tiles lazy-load; img class names change; prefer grid + watch links.
    # YouTube also uses shelf-based layouts (ytd-rich-shelf-renderer) and compact lists on some channels.
    def _channel_grid_locator(self):
        return self.page.locator(
            "#primary ytd-rich-grid-media a#thumbnail[href*='watch?v='], "
            "ytd-rich-grid-media a#thumbnail[href*='watch?v='], "
            "ytd-grid-video-renderer a#thumbnail[href*='watch?v='], "
            "ytd-rich-item-renderer a#thumbnail[href*='watch?v='], "
            "a#thumbnail[href*='watch?v='], "
            "ytd-rich-grid-media, "
            "ytd-grid-video-renderer, "
            "ytd-rich-item-renderer, "
            "a#thumbnail img.ytCoreImageHost, "
            "a#thumbnail img"
        )

    def _first_video_link_locator(self):
        return self.page.locator(
            "#primary ytd-rich-grid-media a#thumbnail[href*='watch?v='], "
            "ytd-rich-grid-media a#thumbnail[href*='watch?v='], "
            "ytd-grid-video-renderer a#thumbnail[href*='watch?v='], "
            "ytd-rich-item-renderer a#thumbnail[href*='watch?v='], "
            "#primary a#thumbnail[href*='watch?v='], "
            "a#thumbnail[href*='watch?v=']"
        )

    def _first_column_row_thumbnail_locator(self):
        return self.page.locator("a#thumbnail img.ytCoreImageHost")

    def _live_ring_locator(self):
        return self.page.locator(".yt-spec-avatar-shape--live-ring")

    def is_displayed(self):
        try:
            if self._youtube_shell_ready():
                self.logger.info("Navigated to Youtube Homepage as anonymous user")
                return True
            self.logger.error("YouTube page shell not detected after waiting — page may not have loaded")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_display_failed.png")
            return False
        except Exception as e:
            self.logger.error(f"Failed to verify YouTube page loaded: {utils.clean_error(e)}")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_display_failed.png")
            return False

    def navigate_to_youtube(self):
        url = self.config['YOUTUBE_URL']
        self.logger.info(f"Accessing Youtube url:{url}")
        try:
            self.page.goto(url)
        except Exception as e:
            self.logger.error(f"Failed to navigate to YouTube homepage: {utils.clean_error(e)}")

    def navigate_to_channel_page(self, channel, type):
        url = f"{self.config['YOUTUBE_URL']}{channel}/{type}"
        self.logger.info(f"Accessing Youtube channel url:{url}")
        try:
            self.page.goto(url)
        except Exception as e:
            self.logger.error(f"Failed to navigate to channel page {url}: {utils.clean_error(e)}")

    def _nudge_lazy_channel_content(self):
        try:
            self.page.evaluate(
                "window.scrollTo(0, Math.min(1500, Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) || 1500));"
            )
            time.sleep(0.9)
        except Exception:
            pass

    def _wait_for_channel_grid(self):
        budget = float(self.driver_wait_sec)
        start = time.monotonic()
        grid = self._channel_grid_locator()
        for attempt in range(5):
            remaining = budget - (time.monotonic() - start)
            if remaining < 2:
                break
            chunk = min(12, remaining)
            try:
                grid.first.wait_for(state="visible", timeout=chunk * 1000)
                return
            except PlaywrightTimeoutError:
                pass
            self.logger.info("Channel grid not ready yet; scroll nudge %s/5", attempt + 1)
            self._nudge_lazy_channel_content()
        raise PlaywrightTimeoutError("Channel video grid did not become visible in time")

    def _wait_visible(self, locator, timeout_sec):
        try:
            locator.first.wait_for(state="visible", timeout=float(timeout_sec) * 1000)
            return True
        except PlaywrightTimeoutError:
            return False

    def _first_clickable(self, locator, timeout_sec):
        try:
            locator.first.wait_for(state="visible", timeout=float(timeout_sec) * 1000)
            return locator.first
        except PlaywrightTimeoutError:
            return None

    def _first_visible_video_link(self, timeout_sec=None):
        t = float(timeout_sec if timeout_sec is not None else self.driver_wait_sec)
        locator = self._first_video_link_locator()
        try:
            locator.first.wait_for(state="visible", timeout=t * 1000)
            return locator.first
        except PlaywrightTimeoutError:
            return None

    def _youtube_shell_ready(self, timeout_sec=None):
        t = float(timeout_sec if timeout_sec is not None else min(25, float(self.driver_wait_sec)))
        return self._wait_visible(self._youtube_shell_locator(), t)

    def is_live_tab_dispalyed(self):
        try:
            url = (self.page.url or "").lower()
            if "/streams" in url:
                self.logger.info("Already on /streams; waiting for channel grid")
                self._wait_for_channel_grid()
                self.logger.info("Live streams grid loaded")
                return True
            if self._wait_visible(self._live_tab_locator(), self.driver_wait_sec):
                self.logger.info("Live tab strip matched")
                return True
            self.logger.info("Live tab strip not found; waiting for channel grid")
            self._wait_for_channel_grid()
            self.logger.info("Live content grid loaded")
            return True
        except PlaywrightTimeoutError:
            self.logger.warning("Timed out waiting for live streams grid — YouTube may not have rendered the page")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_live_tab_navigation_failed.png")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load live streams tab: {utils.clean_error(e)}")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_live_tab_navigation_failed.png")
            return False

    def is_videos_tab_dispalyed(self):
        try:
            url = (self.page.url or "").lower()
            if "/videos" in url:
                self.logger.info("Already on /videos; waiting for channel grid")
                self._wait_for_channel_grid()
                self.logger.info("Videos grid loaded")
                return True
            if self._wait_visible(self._videos_tab_locator(), self.driver_wait_sec):
                self.logger.info("Videos tab strip matched")
                return True
            self.logger.info("Videos tab strip not found; waiting for channel grid")
            self._wait_for_channel_grid()
            self.logger.info("Videos grid loaded")
            return True
        except PlaywrightTimeoutError:
            self.logger.warning("Timed out waiting for videos grid — YouTube may not have rendered the page")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_videos_tab_navigation_failed.png")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load videos tab: {utils.clean_error(e)}")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_videos_tab_navigation_failed.png")
            return False

    def _js_extract_first_video_id(self):
        """Layout-agnostic fallback: scan all page links for the first watch?v= URL."""
        try:
            script = """
                () => {
                    const links = Array.from(document.querySelectorAll('a[href*="watch?v="]'));
                    for (const a of links) {
                        const m = (a.href || '').match(/[?&]v=([A-Za-z0-9_-]{11})/);
                        if (m) return m[1];
                    }
                    return null;
                }
            """
            return self.page.evaluate(script)
        except Exception:
            return None

    def get_first_thumbnail(self):
        try:
            video_id = None
            anchor = self._first_visible_video_link()
            if anchor is not None:
                anchor.scroll_into_view_if_needed()
                utils.highlight_element(anchor)
                href = anchor.get_attribute("href") or ""
                m = re.search(r"[?&]v=([^&]+)", href)
                if m:
                    video_id = m.group(1)
                    self.logger.info("YouTube Video ID (from thumbnail link): %s", video_id)
            if video_id:
                self.logger.info("First channel video tile resolved")
                return video_id

            thumbnail = self._first_column_row_thumbnail_locator().first
            thumbnail.wait_for(state="visible", timeout=float(self.driver_wait_sec) * 1000)
            thumbnail.scroll_into_view_if_needed()
            utils.highlight_element(thumbnail)
            img_src = thumbnail.get_attribute("src") or ""
            match = re.search(r"/vi/([^/]+)/", img_src)
            if match:
                video_id = match.group(1)
                self.logger.info("YouTube Video ID (from image src): %s", video_id)
            else:
                self.logger.error(f"Could not extract video ID from thumbnail src: {img_src[:80]}")
            self.logger.info("First Thumbnail displayed")
            return video_id
        except PlaywrightTimeoutError:
            self.logger.warning("CSS selectors timed out — trying JS fallback")
            video_id = self._js_extract_first_video_id()
            if video_id:
                self.logger.info("YouTube Video ID (from JS fallback): %s", video_id)
                return video_id
            self.logger.error("Timed out waiting for first thumbnail — video grid did not load")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_first_thumbnail_display_failed.png")
        except Exception as e:
            self.logger.error(f"Failed to get first thumbnail: {utils.clean_error(e)}")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_first_thumbnail_display_failed.png")

    def click_first_thumbnail(self):
        try:
            thumbnail = self._first_column_row_thumbnail_locator().first
            thumbnail.wait_for(state="visible", timeout=float(self.driver_wait_sec) * 1000)
            utils.highlight_element(thumbnail)
            thumbnail.click()
            self.logger.info("Clicked First Thumbnail")
        except PlaywrightTimeoutError:
            self.logger.error("Timed out waiting for first thumbnail to become clickable")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_first_thumbnail_click_failed.png")
        except Exception as e:
            self.logger.error(f"Failed to click first thumbnail: {utils.clean_error(e)}")
            self.page.screenshot(path=self.screenshot_path + utils.timestamp() + "_homepage_first_thumbnail_click_failed.png")

    def click_accept_button(self):
        self.logger.info("Clicking Accept cookies if consent dialog is shown")
        btn = self._first_clickable(self._accept_cookie_locator(), min(20, float(self.driver_wait_sec)))
        if btn:
            try:
                utils.highlight_element(btn)
                btn.click()
                self.logger.info("Accepted cookie consent")
                utils.randomSleep(Speed.FAST)
            except Exception as e:
                self.logger.warning(f"Accept cookies click failed: {utils.clean_error(e)}")
        else:
            self.logger.info("No Accept-all cookie button found; continuing")
        self.is_displayed()

    def click_reject_button(self):
        self.logger.info("Rejecting cookie consent if dialog is shown")
        btn = self._first_clickable(self._reject_cookie_locator(), min(20, float(self.driver_wait_sec)))
        if btn:
            try:
                utils.highlight_element(btn)
                btn.click()
                self.logger.info("Dismissed cookie consent (reject)")
                utils.randomSleep(Speed.FAST)
            except Exception as e:
                self.logger.warning(f"Reject cookies click failed: {utils.clean_error(e)}")
        else:
            self.logger.info("No cookie consent dialog to dismiss")
        self.is_displayed()

    def is_live_ring_present(self):
        try:
            live_ring = self._live_ring_locator().first
            live_ring.wait_for(state="visible", timeout=5000)
            if live_ring.is_visible():
                self.logger.info("Live-Ring displayed! Seems like a live-stream is in progress!")
                return True
            return False
        except Exception:
            return False
