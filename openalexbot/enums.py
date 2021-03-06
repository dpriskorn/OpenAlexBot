from enum import Enum


class Property(Enum):
    AUTHOR = "P50"
    AUTHOR_NAME_STRING = "P2093"
    CITES_WORK = "P2860"
    DOI = "P356"
    INSTANCE_OF = "P31"
    ISSUE = "P433"
    LANGUAGE_OF_WORK = "P407"
    MAIN_SUBJECT = "P921"
    OPENALEX_ID = "P10283"
    PAGES = "P304"
    PMID = "P698"
    PUBLICATION_DATE = "P577"
    PUBLISHED_IN = "P1433"
    SERIES_ORDINAL = "P1545"  # aka author position
    STATED_AS = "P1932"
    TITLE = "P1476"
    VOLUME = "P478"


class StatedIn(Enum):
    OPENALEX = "Q107507571"
