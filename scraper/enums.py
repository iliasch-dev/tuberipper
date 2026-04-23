from enum import Enum

class Speed(Enum):
    SLOW = 1
    MEDIUM = 2
    FAST = 3


class Type(Enum):
    STREAM = "streams"
    VIDEO = "videos"

class Format(Enum):
    VIDEO = "VIDEO",
    AUDIO = "AUDIO"


class Ytl_Dlp_Clients(Enum):
    # Clients that reliably expose bestaudio streams
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"
    ANDROID_MUSIC = "android_music"
    YTMUSIC_ANDROID = "ytmusic_android"
