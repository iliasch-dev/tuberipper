from datetime import datetime
import os
import json
import random
import time
import logging
import shutil

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

def clean_error(e):
    """Return a single-line error summary."""
    msg = str(e).split('\nStacktrace:')[0].strip()
    return f"{type(e).__name__}: {msg}" if msg else type(e).__name__


def load_config(filename):
    with open(filename, "r") as file:
        return json.load(file)

config = load_config("config.json")



def _ytdlp_bin():
    venv_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "yt-dlp")
    return venv_bin if os.path.isfile(venv_bin) else "yt-dlp"

_COOKIES_PATH = "cookies/youtube_cookies.txt"

_YTDLP_BASE_ARGS = [
    "--js-runtimes", "node",
    # No player_client pin — let yt-dlp auto-select (currently visionos). A hardcoded
    # tv/web_safari client broke on recently-ended livestreams ("The page needs to be
    # reloaded") and plain "web" needs a PO token provider we don't have.
    "--force-ipv4",
    # must match the real browser/OS refresh_youtube_cookies.sh exports from (Linux Chrome) —
    # a UA/platform mismatch against the cookie jar's origin is itself a bot-detection signal.
    "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.7977.64 Safari/537.36",
    "--add-header", "Accept-Language:en-US,en;q=0.9",
] + (["--cookies", _COOKIES_PATH] if os.path.isfile(_COOKIES_PATH) else [])


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


def highlight_element(locator):
    original_style = locator.get_attribute('style') or ""
    locator.evaluate("(el, style) => el.setAttribute('style', style)", "border: 2px solid red;")
    time.sleep(1)
    locator.evaluate("(el, style) => el.setAttribute('style', style)", original_style)


def download_thumbnail(url):
    try:
        headers = {
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        response = requests.get(url, headers=headers, timeout=15)
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

_BOT_CHECK_MARKER = "Sign in to confirm you"


def _run_yt_dlp(cmd, timeout, retries=2, backoff=12):
    """YouTube's bot-check is intermittent even with valid cookies — a retry often
    succeeds where the previous attempt was flagged, so only retry on that specific error."""
    attempt = 0
    while True:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0 or attempt >= retries or _BOT_CHECK_MARKER not in result.stderr:
            return result
        attempt += 1
        logging.warning(f"yt-dlp hit YouTube's bot-check, retrying ({attempt}/{retries}) in {backoff}s")
        time.sleep(backoff)


def grab_video_info(url):
    video_title = ""
    video_duration = ""
    video_thumbnail_url = ""
    try:
        cmd = [_ytdlp_bin()] + _YTDLP_BASE_ARGS + ["-j", "--no-playlist", url]
        result = _run_yt_dlp(cmd, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip().splitlines()[-1])
        info = json.loads(result.stdout)
        video_title = sanitize_title(info.get("title", ""))
        video_duration = info.get("duration")
        video_thumbnail_url = info.get("thumbnail")
        logging.info(f"Video title: {video_title}")
        logging.info(f"Original video duration: {video_duration} seconds")
        logging.info(f"Thumbnail URL: {video_thumbnail_url}")
    except Exception as e:
        logging.error(f"Error extracting information from video: {e}")
    return video_title, video_duration, video_thumbnail_url


def scrap_audio(url, channel):
    video_title, video_duration, video_thumbnail_url = grab_video_info(url)
    if video_title != "":
        logging.info("Converting video to mp3 file")
        scraps_dir = config["RIPS_PATH"]
        if not os.path.exists(scraps_dir):
            os.makedirs(scraps_dir)
            logging.info(f"Directory '{scraps_dir}' created.")
        audio_filename = f"{channel}_{video_title}"
        audio_filename_ext = f"{channel}_{video_title}.mp3"
        try:
            cmd = [_ytdlp_bin()] + _YTDLP_BASE_ARGS + [
                "-f", "bestaudio/best",
                "-x", "--audio-format", "mp3", "--audio-quality", "192K",
                "-o", os.path.join(scraps_dir, f"{audio_filename}.%(ext)s"),
                url,
            ]
            result = _run_yt_dlp(cmd, timeout=600)
            if result.returncode != 0:
                logging.error(f"Error scrapping youtube video: {result.stderr.strip().splitlines()[-1]}")
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
            target_dir = config["TARGET_PATH"]
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
    api_token = config.get("PUSHOVER_API_TOKEN", "")
    user_key = config.get("PUSHOVER_USER_KEY", "")
    if not api_token or not user_key:
        logging.info("Pushover credentials not configured — skipping notification")
        return
    try:
        logging.info(f"Downloading thumbnail:{image_url}")
        image_response = requests.get(image_url, timeout=15)
        if image_response.status_code != 200:
            logging.error("Failed to download image.")
            return
        image_file = BytesIO(image_response.content)
        image_file.name = "image.jpg"
        files = {"attachment": image_file}
        data = {
            "token": api_token,
            "user": user_key,
            "message": message,
            "sound": "intermission"
        }
        response = requests.post(PUSHOVER_API_URL, data=data, files=files, timeout=15)
        if response.status_code == 200:
            logging.info("✅ Notification sent successfully.")
        else:
            logging.error("❌ Failed to send notification.")
            logging.error(response.text)
    except Exception as e:
        logging.error(f"Error sending push notification {e}")
