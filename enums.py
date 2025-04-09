from enum import Enum

class Speed(Enum):
    SLOW = 1
    MEDIUM = 2
    FAST = 3


class Type(Enum):
    STREAM="streams"
    VIDEO="videos"

class Format(Enum):
    VIDEO = "VIDEO",
    AUDIO = "AUDIO"


class Ytl_Dlp_Clients(Enum):
    ANDROID = "android"
    ANDROID_EMBED = "android_embed"
    WEB = "web"
    WEB_EMBEDDED_PLAYER = "web_embedded_player"
    TVHTML5_SIMPLY_EMBEDDED_PLAYER = "tvhtml5_simply_embedded_player"
    TVHTML5 = "tvhtml5"
    IOS = "ios"
    IOS_MESSAGES_EXTENSION = "ios_messages_extension"
    MWEB = "mweb"
    YTMUSIC = "ytmusic"
    YTMUSIC_ANDROID = "ytmusic_android"
    YTMUSIC_IOS = "ytmusic_ios"
    ANDROID_MUSIC = "android_music"
    WEB_REMIX = "web_remix"
    ANDROID_CREATOR = "android_creator"