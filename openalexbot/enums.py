from enum import Enum


class Property(Enum):
    MAIN_SUBJECT = "P921"
    STATED_AS = "P1932"
    TITLE = "P1476"
    DOI = "P356"
    INSTANCE_OF = "P31"
    OPENALEX_ID = ""
    PMID = "P698"
    CITES_WORK = "P2860"
    ISSUE = "P433"
    PAGES = "P304"
    VOLUME = "P478"
    PUBLISHED_IN = "P1433"
    PUBLICATION_DATE = "P577"
    LANGUAGE_OF_WORK = "P407"


class StatedIn(Enum):
    OPENALEX = "Q107507571"
