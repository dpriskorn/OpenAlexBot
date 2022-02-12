from enum import Enum


class Property(Enum):
    MAIN_SUBJECT = "P921"
    DETERMINATION_METHOD = "P459"
    STATED_AS = "P1932"
    TITLE = "P1476"


class StatedIn(Enum):
    OPENALEX = "Q107507571"
