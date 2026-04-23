from datetime import datetime
import os
import json
import random
import time
import logging
import shutil

import yt_dlp
import subprocess
import eyed3
import requests
from io import BytesIO
from pytube import YouTube
from .enums import Speed
from PIL import Image
import re
import unicodedata

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_API_TOKEN = "REDACTED_API_TOKEN"
PUSHOVER_USER_KEY = "REDACTED_USER_KEY"

def clean_error(e):
    """Return a single-line error summary, stripping Selenium's verbose Stacktrace block."""
    msg = str(e).split('\nStacktrace:')[0].strip()
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def load_config(filename):
    with open(filename, "r") as file:
        return json.load(file)

config = load_config("config.json")


def _yt_dlp_auth_options():
    """
    YouTube often returns a bot check (sign-in required) when yt-dlp has no session cookies.
    Set YTDLP_COOKIES_FILE to a Netscape-format cookies.txt, or YTDLP_COOKIES_FROM_BROWSER (e.g. chrome, firefox).
    Alternatively place youtube_cookies.txt or cookies.txt under COOKIES_PATH.
    See https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies
    """
    out = {}
    cf = config.get("YTDLP_COOKIES_FILE") or config.get("YT_DLP_COOKIES_FILE")
    if isinstance(cf, str) and cf.strip():
        path = os.path.abspath(os.path.expanduser(cf.strip()))
        if os.path.isfile(path):
            out["cookiefile"] = path
            logging.info("yt-dlp using cookie file: %s", path)
            return out
        logging.warning("YTDLP_COOKIES_FILE set but file not found: %s", path)

    browser = config.get("YTDLP_COOKIES_FROM_BROWSER") or config.get("COOKIES_FROM_BROWSER")
    if isinstance(browser, str) and browser.strip():
        out["cookiesfrombrowser"] = (browser.strip().lower(),)
        logging.info("yt-dlp using cookies from browser: %s", browser.strip().lower())
        return out

    folder = config.get("COOKIES_PATH")
    if isinstance(folder, str) and folder.strip():
        base = folder.strip().rstrip(os.sep)
        for fname in ("youtube_cookies.txt", "cookies.txt", "yt_cookies.txt"):
            path = os.path.abspath(os.path.join(base, fname))
            if os.path.isfile(path):
                out["cookiefile"] = path
                logging.info("yt-dlp using cookie file: %s", path)
                return out
    return out


def _yt_dlp_common_options():
    """Cookies (if configured) + EJS solver from GitHub (requires Deno on PATH)."""
    opts = _yt_dlp_auth_options()
    opts["remote_components"] = {"ejs:github"}
    return opts


def staticSleep(waitTime):
    logging.info(f"Sleeping {waitTime}s")
    time.sleep(waitTime)

def randomSleep(speed):
    if speed == Speed.SLOW:
        waitTime = random.randint(15, 30)
    elif speed == Speed.MEDIUM:
        waitTime = random.randint(5, 10)
    elif speed == Speed.FAST:
        waitTime = random.randint(2, 4)
    else:
        raise ValueError("Invalid speed")
    logging.info(f"Sleeping {waitTime}s")
    time.sleep(waitTime)

def timestamp():
    now = datetime.now()
    return str(now.strftime("%d%m%Y"))

def clear_directory_contents(directory_path):
    try:
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
                logging.info(f"Deleted file: {item_path}")
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                logging.info(f"Deleted directory: {item_path}")
        logging.info(f"All contents of directory '{directory_path}' have been removed.")
    except Exception as e:
        logging.error(f"Error clearing directory contents: {e}")

def delete_temp():
    if os.path.exists("temp/"):
        shutil.rmtree("temp/")
        logging.info(f"Directory temp/ directory deleted successfully.")

def clean_screencaps():
    directory = "screencap/"
    extension = ".png"
    for file in os.listdir(directory):
        if file.endswith(extension):
            file_path = os.path.join(directory, file)
            os.remove(file_path)


def highlight_element(driver, element):
    driver = element._parent
    original_style = element.get_attribute('style')
    driver.execute_script("arguments[0].setAttribute('style', arguments[1]);",
                          element, "border: 2px solid red;")
    time.sleep(1)
    driver.execute_script("arguments[0].setAttribute('style', arguments[1]);",
                          element, original_style)


def scroll_by_amount(driver, scroll_amount):
    current_scroll_position = driver.execute_script("return window.pageYOffset")
    logging.info(f"Current scroll position: {current_scroll_position}")
    new_scroll_position = driver.execute_script("return window.pageYOffset + %s;" % scroll_amount)
    logging.info(f"New Scroll position: {new_scroll_position}")
    driver.execute_script("window.scrollTo('%s', '%s');" % (current_scroll_position, new_scroll_position))


def download_thumbnail(url):
    try:
        headers = {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        original_image = Image.open(BytesIO(response.content)).convert("RGB")
        jpeg_data = BytesIO()
        original_image.save(jpeg_data, format='JPEG')
        jpeg_data.seek(0)
        logging.info(f"downloaded thumbnail for url:{url}")
        return jpeg_data
    except Exception as e:
        logging.error("error capturing thumbnail")
        blank_image = Image.new('RGB', (1, 1), color='white')
        jpeg_data = BytesIO()
        blank_image.save(jpeg_data, format='JPEG')
        jpeg_data.seek(0)
        return jpeg_data


def embed_thumbnail(mp3_file, image_data, title=None, album=None, artist=None):
    audio_file = eyed3.load(mp3_file)
    image_data.seek(0)
    audio_file.tag.images.set(3, image_data.read(), 'image/jpeg')
    if title:
        audio_file.tag.title = title
    if album:
        audio_file.tag.album = album
    if artist:
        audio_file.tag.artist = artist
    audio_file.tag.save()


def get_audio_duration_ffprobe(filename):
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        filename
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    duration = json.loads(result.stdout)['format']['duration']
    return int(float(duration))

def sanitize_title(name, replace_with="_", ascii_only=False):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', replace_with, name)
    if ascii_only:
        name = unicodedata.normalize('NFKD', name)
        name = name.encode('ascii', 'ignore').decode('ascii')
    extra_forbidden = r'[€©™•…""''–—·¿¡]'
    name = re.sub(extra_forbidden, replace_with, name)
    name = re.sub(f'{re.escape(replace_with)}+', replace_with, name)
    return name.strip().strip(replace_with)

def grab_video_info(url):
    ydl_opts_info = {}
    ydl_opts_info.update(_yt_dlp_common_options())
    video_title = ""
    video_duration = ""
    video_thumbnail_url = ""
    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title')
            video_title = sanitize_title(video_title)
            video_duration = info.get('duration')
            video_thumbnail_url = info.get('thumbnail')
            logging.info(f"Video title: {video_title}")
            logging.info(f"Original video duration: {video_duration} seconds")
            logging.info(f"Thumbnail URL: {video_thumbnail_url}")
    except Exception as e:
        logging.error(f"Error extracting information from video: {e}")
    return video_title, video_duration, video_thumbnail_url


def scrap_audio(url, channel, yldlp_client):
    video_title, video_duration, video_thumbnail_url = grab_video_info(url)
    if video_title != "":
        logging.info("Converting video to mp3 file")
        scraps_dir = config["RIPS_PATH"]
        if not os.path.exists(scraps_dir):
            os.makedirs(scraps_dir)
            logging.info(f"Directory '{scraps_dir}' created.")
        audio_filename = f"{channel}_{video_title}"
        audio_filename_ext = f"{channel}_{video_title}.mp3"
        ydl_opts_download = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(scraps_dir, f'{audio_filename}.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'extractor_args': {
                'youtube': {
                    'client': [yldlp_client]
                }
            },
            'quiet': True
        }
        ydl_opts_download.update(_yt_dlp_common_options())
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            try:
                ydl.download([url])
            except Exception as e:
                logging.error(f"Error scrapping youtube video {e}")
        thumbnail_image = download_thumbnail(video_thumbnail_url)
        full_audio_path = os.path.join(scraps_dir, audio_filename_ext)
        embed_thumbnail(os.path.join(scraps_dir, audio_filename_ext), thumbnail_image, video_title, video_title, channel)
        audio_duration = get_audio_duration_ffprobe(os.path.join(scraps_dir, audio_filename_ext))
        logging.info(f"Downloaded MP3 duration: {audio_duration} seconds")
        duration_tolerance = 10
        if abs(video_duration - audio_duration) <= duration_tolerance:
            logging.info("Durations match!")
            target_dir = "/media/chronalis/tuberipper/"
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
                logging.info(f"Target directory '{target_dir}' created.")
            target_path = os.path.join(target_dir, audio_filename_ext)
            shutil.move(full_audio_path, target_path)
            logging.info(f"Moved MP3 file to {target_path}")
            return {
                "video_title": video_title,
                "video_duration": video_duration,
                "video_thumbnail_url": video_thumbnail_url,
                "audio_filename": audio_filename_ext
            }
        else:
            logging.error(f"Mismatch: video is {video_duration}s, audio is {audio_duration}s")
            audio_file_path = os.path.join(scraps_dir, f"{audio_filename_ext}")
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
                logging.info(f"Deleted MP3 file: {audio_file_path} due to duration mismatch.")
            else:
                logging.warning(f"MP3 file {audio_file_path} not found for deletion.")


def download_audio_using_pytube(youtube_url, channel, output_path="scraps"):
    try:
        yt = YouTube(youtube_url)
        video_title = yt.title
        video_duration = yt.length
        video_thumbnail_url = yt.thumbnail_url
        audio_stream = yt.streams.filter(only_audio=True).first()
        if audio_stream:
            audio_stream.download(output_path=output_path, filename=f"{channel}_{video_title}.mp3")
            logging.info(f"Downloaded audio for: {video_title} with duration: {video_duration} seconds")
        else:
            logging.error("No audio stream found!")
        return video_title, video_duration, video_thumbnail_url
    except Exception as e:
        logging.error(f"Error occurred: {e}")
        return None, None, None


def send_pushover_notification(message, image_url):
    try:
        logging.info(f"Downloading thumbnail:{image_url}")
        image_response = requests.get(image_url)
        if image_response.status_code != 200:
            logging.error("❌ Failed to download image.")
            return
        image_file = BytesIO(image_response.content)
        image_file.name = "image.jpg"
        files = {"attachment": image_file}
        data = {
            "token": PUSHOVER_API_TOKEN,
            "user": PUSHOVER_USER_KEY,
            "message": message,
            "sound": "intermission"
        }
        response = requests.post(PUSHOVER_API_URL, data=data, files=files)
        if response.status_code == 200:
            logging.info("✅ Notification sent successfully.")
        else:
            logging.error("❌ Failed to send notification.")
            logging.error(response.text)
    except Exception as e:
        logging.error(f"Error sending push notification {e}")
