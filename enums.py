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