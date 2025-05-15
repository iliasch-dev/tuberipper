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
from enums import Speed
from PIL import Image
import re
import unicodedata

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_API_TOKEN = "REDACTED_API_TOKEN"  # Replace with your Pushover app token
PUSHOVER_USER_KEY = "REDACTED_USER_KEY"    # Replace with your Pushover user key

def load_config(filename):
    with open(filename, "r") as file:
        return json.load(file)
    
config = load_config("config.json")


def staticSleep(waitTime):
    logging.info(f"Sleeping {waitTime}s")
    time.sleep(waitTime)

def randomSleep(speed):
    if speed == Speed.SLOW:
        waitTime= random.randint(15, 30)
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
    timestamp = str(now.strftime("%d%m%Y"))
    return timestamp

def clear_directory_contents(directory_path):
    try:
        # List all files and directories in the directory
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
        extension = ".png"  # Specify the extension you want to clean (e.g., ".txt")
        for file in os.listdir(directory):
            # Check if the file has the specified extension
            if file.endswith(extension):
                # Construct the full file path
                file_path = os.path.join(directory, file)
                # Remove the file
                os.remove(file_path)          


def highlight_element(driver, element):
    driver = element._parent
    original_style = element.get_attribute('style')
    driver.execute_script("arguments[0].setAttribute('style', arguments[1]);",
                          element, "border: 2px solid red;")
    time.sleep(1)  # Highlight for 2 seconds
    driver.execute_script("arguments[0].setAttribute('style', arguments[1]);",
                          element, original_style)


def scroll_by_amount(driver, scroll_amount):
    # Calculate new scroll position
    current_scroll_position = driver.execute_script("return window.pageYOffset")
    logging.info(f"Current scroll position: {current_scroll_position}")
    new_scroll_position = driver.execute_script("return window.pageYOffset + %s;" % scroll_amount)
    logging.info(f"New Scroll position: {new_scroll_position}")
    # Scroll to the new position
    driver.execute_script("window.scrollTo('%s', '%s');" % (current_scroll_position, new_scroll_position))


# Step 3: Download the thumbnail image
def download_thumbnail(url):
    headers = {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    response = requests.get(url,headers=headers)
    response.raise_for_status()  # Optional: throws an error for bad responses
    # Load image from response
    original_image = Image.open(BytesIO(response.content)).convert("RGB")
    # Convert to JPEG in-memory
    jpeg_data = BytesIO()
    original_image.save(jpeg_data, format='JPEG')
    jpeg_data.seek(0)

    return jpeg_data

def embed_thumbnail(mp3_file, image_data, title=None, album=None, artist=None):
    audio_file = eyed3.load(mp3_file)
    image_data.seek(0)  # Ensure the image data pointer is at the start
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
    # 1. Replace Windows-forbidden characters and control characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', replace_with, name)
    
    # 2. Optionally normalize and remove non-ASCII characters (e.g., €)
    if ascii_only:
        # Normalize Unicode to remove accents and convert to closest ASCII
        name = unicodedata.normalize('NFKD', name)
        name = name.encode('ascii', 'ignore').decode('ascii')

    # 3. Replace additional user-defined symbols
    # You can customize this set
    extra_forbidden = r'[€©™•…“”‘’–—·¿¡]'
    name = re.sub(extra_forbidden, replace_with, name)

    # 4. Collapse multiple underscores (or replace_with character)
    name = re.sub(f'{re.escape(replace_with)}+', replace_with, name)

    # 5. Strip leading/trailing spaces or replacement characters
    return name.strip().strip(replace_with)

def grab_video_info(url):
    ydl_opts_info = {}
    video_title=""
    video_duration=""
    video_thumbnail_url=""
    try:
         with yt_dlp.YoutubeDL(ydl_opts_info) as ydl: 
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title')  # Video title
            video_title = sanitize_title(video_title)   
            video_duration = info.get('duration')  # Duration in seconds
            video_thumbnail_url = info.get('thumbnail')  # Thumbnail URL
            logging.info(f"Video title: {video_title}")
            logging.info(f"Original video duration: {video_duration} seconds")
            logging.info(f"Thumbnail URL: {video_thumbnail_url}")
    except Exception as e:
            logging.error(f"Error extracting information from video: {e}")
    return video_title,video_duration, video_thumbnail_url
        


def scrap_audio(url,channel,yldlp_client):
    # Step 1: Get the original video duration, title, and thumbnail
    video_title,video_duration, video_thumbnail_url = grab_video_info(url)
    if video_title!="":
        logging.info("Converting video to mp3 file")
        scraps_dir =  config["RIPS_PATH"]
        if not os.path.exists(scraps_dir):
            os.makedirs(scraps_dir)
            logging.info(f"Directory '{scraps_dir}' created.")
        # Step 2: Download and convert to mp3
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
                'client': [yldlp_client]  # or 'web', 'tvhtml5', 'ios', etc.
                }
            },
            #'postprocessor_args': ['-t', '60'],  #TOBEREMOVED
            'quiet': True  # Optional: suppress yt-dlp output
        }
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            try:
                ydl.download([url])
            except Exception as e:
                logging.error(f"Error scrapping youtube video {e}")
        thumbnail_image = download_thumbnail(video_thumbnail_url)
        full_audio_path = os.path.join(scraps_dir, audio_filename_ext)
        embed_thumbnail( os.path.join(scraps_dir,audio_filename_ext), thumbnail_image, video_title,video_title,channel)
        audio_duration = get_audio_duration_ffprobe(os.path.join(scraps_dir,audio_filename_ext))
        logging.info(f"Downloaded MP3 duration: {audio_duration} seconds")
        # Step 6: Compare durations
        duration_tolerance = 10 #10 sec fault tolerance
        if abs(video_duration - audio_duration) <= duration_tolerance:
            logging.info("Durations match!")
            target_dir = "/media/chronalis/tuberipper/"
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)  # Optional: create if it doesn't exist
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
            # Check if the file exists before attempting to delete it
            if os.path.exists(audio_file_path):
                os.remove(audio_file_path)
                logging.info(f"Deleted MP3 file: {audio_file_path} due to duration mismatch.")
            else:
                logging.warning(f"MP3 file {audio_file_path} not found for deletion.")
        

def download_audio_using_pytube(youtube_url,channel, output_path="scraps"):
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
        image_file.name = "image.jpg"  # Pushover needs a filename
        files = {
            "attachment": image_file
        }
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

