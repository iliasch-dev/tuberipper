from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from PIL import Image
import os
import smtplib
import json
import random
import time
import requests
import logging
import shutil
import re
import emoji
import tempfile
import io



def load_config(filename):
    with open(filename, "r") as file:
        return json.load(file)


def send_email(subject, body, config):
    # Create message
    message = MIMEMultipart()
    message["From"] = config["SENDER_EMAIL"]
    message["To"] = config["RECEIVER_EMAIL"]
    message["Subject"] = subject
    # Email body
    message.attach(MIMEText(body, "html"))
    # Connect to SMTP server and send email
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(config["SENDER_EMAIL"], config["EMAIL_PASSWORD"])
        server.send_message(message)

def send_email_plain(subject, body, config):
    # Create message
    try:
        message = MIMEMultipart()
        message["From"] = config["SENDER_EMAIL"]
        message["To"] = config["RECEIVER_EMAIL"]
        message["Subject"] = subject
        # Email body
        message.attach(MIMEText(body, "plain"))
        # Connect to SMTP server and send email
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(config["SENDER_EMAIL"], config["EMAIL_PASSWORD"])
            server.send_message(message)
    except Exception as e:
        print(f"Error sending mail {e}")


#TODO: needs refactoring to work with different platforms
def select_filename(config):
    # List files in the directory
    files = os.listdir(config["IMAGE_SOURCE_PATH"])
    # Filter files to only include those with a ".jpg" extension
    jpg_files = [file for file in files if file.endswith(".jpg")]
    if jpg_files:
        # Sort JPG files alphabetically
        sorted_files = sorted(jpg_files)
        # Select the first filename (alphabetically)
        selected_filename = sorted_files[0]
        return selected_filename
    else:
        return None
    

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
    timestamp = str(now.strftime("%d%m%Y_%H%M%S"))
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


def tweet_contains_mention(text):
    words = text.split()  
    first_at_found = False
    for word in words:
        if "@" in word:
            if not first_at_found:
                first_at_found = True
                continue
            else:
                return True
    return False

def extract_first_username(s):
    # This regex finds the first substring that starts with @ followed by any character except for whitespace
    match = re.search(r'@\S+', s)
    if match:
        return match.group()
    else:
        return None
    

def load_users_from_file(number_of_users): 
    target_x_users = []
    logging.info(f"Loading up users from local file")
    with open('target_users.txt', 'r') as file:
        all_users = [line.strip() for line in file]
        target_x_users = random.sample(all_users, min(number_of_users, len(all_users)))
    logging.info(f"Picked {len(target_x_users)} users, Target Usernames: {target_x_users}")
    return target_x_users


def save_image_from_url(username, image_url):
    folder_path = "temp/"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            if (username != ""):
                file_name = f"{username}_{timestamp}.jpg"
            else: 
                file_name = f"{timestamp}.jpg"
            full_path = os.path.join(folder_path, file_name)
            with open(full_path, "wb") as f:
                content_type = response.headers.get('content-type')
                if content_type == 'image/webp':
                    # Convert WebP to JPEG using Pillow
                    img = Image.open(io.BytesIO(response.content))
                    img = img.convert("RGB")
                    img.save(f, "JPEG")
                elif content_type == 'image/png':
                    # Convert PNG to JPEG using Pillow
                    img = Image.open(io.BytesIO(response.content))
                    img = img.convert("RGB")
                    img.save(f, "JPEG")      
                else:
                    f.write(response.content)
                f.flush()  # Flush the write buffer
                os.fsync(f.fileno())  # Synchronize the file with disk
            return full_path
        else:
            logging.error(f"Failed to download the image from URL: {image_url} - HTTP Status Code: {response.status_code}")
    except Exception as e:
        logging.error("An error occurred while saving image to temp/: %s", str(e))


def save_image_from_url_to_dir(username, image_url, filename, dir):
    folder_path = dir
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            if (username != ""):
                file_name = f"{username}_{timestamp}_{filename}.jpg"
            else: 
                file_name = f"{filename}_{timestamp}.jpg"
            full_path = os.path.join(folder_path, file_name)
            with open(full_path, "wb") as f:
                f.write(response.content)
                f.flush()  # Flush the write buffer
                os.fsync(f.fileno())  # Synchronize the file with disk
            return full_path
        else:
            logging.error(f"Failed to download the image from URL: {image_url} - HTTP Status Code: {response.status_code}")
    except Exception as e:
        logging.error("An error occurred while saving image to temp/: %s", str(e))


    # def save_blob_to_tempfile(blob_data, file_extension='.jpg'):
    #     temp_file = None
    #     try:
    #         # Create a temporary file with the specified extension
    #         logging.info("Saving blob to temporary image file in /tmp")
    #         temp_file = tempfile.NamedTemporaryFile(suffix=file_extension, delete=False)
    #         temp_file_path = temp_file.name           
    #         # Write the blob data to the temporary file
    #         with open(temp_file_path, 'wb') as f:
    #             f.write(blob_data)          
    #         # Set full permissions to the file
    #         os.chmod(temp_file_path, 0o777)   
    #         logging.info(f"Absolute image path: {temp_file_path}")    
    #         return temp_file_path
    #     except Exception as e:
    #         logging.error("Error saving blob to temporary file: %s", e)
    #         return None
    #     finally:
    #         if temp_file:
    #             temp_file.close()

def save_blob_to_tempfile(blob_data, file_extension='.jpg'):
    temp_file_path = None
    try:
        random_number = random.randint(100000, 999999) 
        temp_file_name = f"tempfile_{random_number}{file_extension}"
        temp_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__))+"/temp", temp_file_name)     
        with open(temp_file_path, 'wb') as f:
            f.write(blob_data)       
        os.chmod(temp_file_path, 0o777)     
        logging.info(f"Tempfile saved to: {temp_file_path}")
        return temp_file_path
    except Exception as e:
        logging.error("Error saving blob to file: %s", e)
    return None


def find_jaccard_similarity(array1,array2):
    intersection = len(set(array1).intersection(set(array2)))
    union = len(set(array2).union(set(array2)))
    return intersection / union if union != 0 else 0


# def clean_emojis(text):
#      return ''.join(char for char in text if not emoji.demojize(char).startswith(':'))


def clean_emojis(text):
    emoji_pattern = re.compile("["
                               u"\U0001F600-\U0001F64F"  # emoticons
                               u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                               u"\U0001F680-\U0001F6FF"  # transport & map symbols
                               u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                               u"\U0001F1F2-\U0001F1F4"  # Macau flag
                               u"\U0001F1E6-\U0001F1FF"  # flags (other)
                               u"\U0001F191-\U0001F251"  # other symbols
                               "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)


def download_image(image_url):
    folder_path = "temp/"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            full_path = os.path.join(folder_path, timestamp + ".jpg")
            with open(full_path, "wb") as f:
                content_type = response.headers.get('content-type')
                if content_type in ['image/webp', 'image/png']:
                    # Convert WebP or PNG to JPEG using Pillow
                    img = Image.open(io.BytesIO(response.content))
                    img = img.convert("RGB")
                    img.save(f, "JPEG")        
                    # Get the content of the newly saved JPEG file
                    f.flush()  # Flush the write buffer
                    os.fsync(f.fileno())  # Synchronize the file with disk
                    with open(full_path, "rb") as converted_f:
                        converted_content = converted_f.read()              
                    return converted_content
                else:
                    f.write(response.content)
                    f.flush()  # Flush the write buffer
                    os.fsync(f.fileno())  # Synchronize the file with disk
                    return response.content
        else:
            logging.error(f"Failed to download the image from URL: {image_url} - HTTP Status Code: {response.status_code}")
            return None
    except Exception as e:
        logging.error("An error occurred while saving image to temp/: %s", str(e))
        return None
    

def get_image_resolution(image_path):
    with Image.open(image_path) as img:
        width, height = img.size
    return width, height


def is_proper_quality(image_path, aspect_ratio_range, min_height):
    with Image.open(image_path) as img:
        width, height = img.size
        aspect_ratio = width / height    
    if height < min_height:
        logging.info(f"Image did not pass resolution check.")
        return False
    min_aspect_ratio, max_aspect_ratio = aspect_ratio_range
    if aspect_ratio < min_aspect_ratio or aspect_ratio > max_aspect_ratio:
        logging.info(f"Image did not pass aspect ratio check.")
        return False
    return True, "Image resolation and aspect ration requiremetns met!"


def calculate_overall_rating(rating, likes):
    # Normalize rating to a scale of 0 to 1
    normalized_rating = rating / 100.0
    # Normalize number of likes to a scale of 0 to 1
    max_likes = 1000  # Assuming a maximum of 1000 likes
    normalized_likes = min(likes / max_likes, 1.0)
    # Assign weights
    weight_rating = 0.2
    weight_likes = 0.8
    # Calculate overall rating
    overall_rating = (weight_rating * normalized_rating) + (weight_likes * normalized_likes)
    overall_rating_formatted = "{:.3f}".format(overall_rating)
    return overall_rating_formatted


def convert_image_to_thumbnail(image_data, scale_percentage):
    try:
        # Open the image from byte data
        image = Image.open(io.BytesIO(image_data))
        # Handle image modes that need conversion
        if image.mode == 'P':
            if image.info.get('transparency') is not None:
                image = image.convert('RGBA')
            else:
                image = image.convert('RGB')
        elif image.mode == 'RGBA':
            image = image.convert('RGB')
        # Calculate new dimensions
        new_width = int(image.width * (scale_percentage / 100))
        new_height = int(image.height * (scale_percentage / 100))
        # Resize the image
        thumbnail = image.resize((new_width, new_height), Image.BILINEAR)
        # Save thumbnail as JPEG to a bytes buffer
        buffer = io.BytesIO()
        thumbnail.save(buffer, format="JPEG")
        return buffer.getvalue()
    except Exception as e:
        logging.error(f"Error converting image to thumbnail: {e}")
        return None

#TODO: method call that send keys with random delay and simulates user typing, should get element as input and text 
# # Loop through each character in the text
# for char in text:
#     # Send one character at a time
#     input_field.send_keys(char)
#     # Add a delay (adjust the sleep duration as needed)
#     time.sleep(0.1)  # Adjust the sleep duration as needed


