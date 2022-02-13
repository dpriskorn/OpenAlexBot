import logging
from datetime import datetime, timezone
from typing import Set, Optional, List, Union

import pandas as pd
from openalexapi import OpenAlex, Work
from pandas import DataFrame
from pydantic import BaseModel
from rich import print
from wikibaseintegrator import WikibaseIntegrator, wbi_config, wbi_login, entities
from wikibaseintegrator import datatypes
from wikibaseintegrator.wbi_helpers import mediawiki_api_call_helper

import config
from openalexbot.enums import StatedIn, Property
from openalexbot.work_type_to_qid import WorkTypeToQid

logging.basicConfig(level=config.loglevel)
logger = logging.getLogger(__name__)


class OpenAlexBot(BaseModel):
    """
    This class takes a CSV as input
    The column "doi" is then processed row by row
    It supports both "naked" dois and with prefix.
    """
    dataframe: Optional[DataFrame]
    dois: Optional[Set[str]]
    filename: str

    def __check_and_extract_doi_column__(self):
        if "doi" in self.dataframe.columns:
            logger.debug("Found 'doi' column")
            if len(self.dataframe) > 0:
                dois: List[str] = self.dataframe["doi"].values
                self.dois = set(dois)
            else:
                raise ValueError("No rows in the dataframe")
        else:
            raise ValueError("No 'doi' column found")

    def __found_using_cirrussearch__(self, doi: str) -> bool:
        # Lookup using CirrusSearch
        result = mediawiki_api_call_helper(
            mediawiki_api_url=f"https://www.wikidata.org/w/api.php?format=json&action=query&"
                              f"list=search&srprop=&srlimit=10&srsearch={doi}",
            allow_anonymous=True
        )
        # logger.info(f"result from CirrusSearch: {result}")
        if config.loglevel == logging.DEBUG:
            print(result)
        if "query" in result:
            query = result["query"]
            if "search" in query:
                search = query["search"]
                if len(search) > 0:
                    # Found 1 match!
                    # qid = search[0]["title"]
                    return True
                    # exit()
                else:
                    return False

    def __get_first_qid_from_cirrussearch__(self, doi: str) -> Union[str, bool]:
        # Lookup using CirrusSearch
        result = mediawiki_api_call_helper(
            mediawiki_api_url=f"https://www.wikidata.org/w/api.php?format=json&action=query&"
                              f"list=search&srprop=&srlimit=10&srsearch={doi}",
            allow_anonymous=True
        )
        # logger.info(f"result from CirrusSearch: {result}")
        if config.loglevel == logging.DEBUG:
            print(result)
        if "query" in result:
            query = result["query"]
            if "search" in query:
                search = query["search"]
                if len(search) > 0:
                    # Found match!
                    qid = search[0]["title"]
                    return qid
                else:
                    return False

    def __import_new_item__(
            self, doi: str, work: Work, wbi: WikibaseIntegrator
    ):
        self.__upload_new_item__(item=self.__prepare_new_item__(doi=doi, work=work, wbi=wbi))

    def __prepare_new_item__(
            self, doi: str, work: Work, wbi: WikibaseIntegrator
    ) -> entities.Item:
        # TODO language of display name using langdetect and set dynamically
        item = wbi.item.new()
        item.labels.set("en", work.display_name)
        item.descriptions.set("en", f"scientific article from {work.publication_year}")
        # Prepare reference
        retrieved_date = datatypes.Time(
            prop_nr="P813",  # Fetched today
            time=datetime.utcnow().replace(
                tzinfo=timezone.utc
            ).replace(
                hour=0,
                minute=0,
                second=0,
            ).strftime("+%Y-%m-%dT%H:%M:%SZ")
        )
        stated_in = datatypes.Item(
            prop_nr="P248",
            value=StatedIn.OPENALEX.value
        )
        reference = [
            retrieved_date,
            stated_in
        ]
        # Prepare claims
        title = datatypes.MonolingualText(
            prop_nr=Property.TITLE.value,
            text=work.title,
            language="en",
            references=[reference]
        )
        doi = datatypes.ExternalID(
            prop_nr=Property.DOI.value,
            value=doi.lower(),  # This is a community norm in Wikidata
            references=[reference]
        )
        type_qid = WorkTypeToQid(work=work)
        type_qid = type_qid.get_qid()
        instance_of = datatypes.Item(
            prop_nr=Property.INSTANCE_OF.value,
            value=type_qid,
            references=[reference]
        )
        if len(work.referenced_works) > 0:
            logger.info(f"Working on references now")
            oa = OpenAlex()
            cites_works: List[datatypes.Item] = []
            for referenced_work_url in work.referenced_works:
                referenced_work = oa.get_single_work(referenced_work_url)
                # print(referenced_work.dict())
                doi = referenced_work.ids.doi_id
                if doi is not None:
                    if self.__found_using_cirrussearch__(doi):
                        qid = self.__get_first_qid_from_cirrussearch__(doi)
                        cites_work = datatypes.Item(
                            prop_nr=Property.CITES_WORK.value,
                            value=qid,
                            references=[reference]
                        )
                        cites_works.append(
                            cites_work
                        )
                    else:
                        # TODO decide whether to import transitive references also
                        logger.warning(f"Reference DOI '{doi}' not found in Wikidata")
                else:
                    # TODO decide whether to import these
                    logger.warning(f"DOI was None for OpenAlex ID {referenced_work_url} "
                                   f"with ids {referenced_work.ids}, skipping")
            logger.debug(f"Generated {len(cites_works)} cited works")
            if config.loglevel == logging.DEBUG:
                print(cites_works)
            if len(cites_works) > 0:
                item.add_claims(cites_works)
        # TODO convert more data from OpenAlex work to claims
        item.add_claims(
            [
                title,
                doi,
                instance_of
            ],
            # This means that if the value already exist we will update it.
            # action_if_exists=ActionIfExists.APPEND
        )
        if config.loglevel == logging.DEBUG:
            print(item.get_json())
        return item

    def __process_dois__(self):
        oa = OpenAlex()
        wbi_config.config["USER_AGENT_DEFAULT"] = config.user_agent
        wbi = WikibaseIntegrator(login=wbi_login.Login(
            user=config.bot_username,
            password=config.password
        ))
        processed_dois = set()
        for doi in self.dois:
            logger.debug(f"doi: '{doi}'")
            doi = doi.replace("https://doi.org/", "")
            if "http" in doi:
                raise ValueError(f"http found in this DOI after "
                                 f"removing the prefix: {doi}")
            if doi not in processed_dois:
                work = oa.get_single_work(f"doi:{doi}")
                if work is not None:
                    # print(work.dict())
                    if not self.__found_using_cirrussearch__(doi):
                        self.__import_new_item__(doi=doi, work=work, wbi=wbi)
                    else:
                        print(f"DOI: '{doi}' is already in Wikidata, skipping")
                    if config.press_enter_to_continue:
                        input("press enter to continue")
                else:
                    if self.__found_using_cirrussearch__(doi):
                        print(f"DOI '{doi}' found in Wikidata but not in OpenAlex")
                    else:
                        print(f"DOI '{doi}' not found in OpenAlex and Wikidata")
                processed_dois.add(doi)

    def __read_csv__(self):
        self.dataframe = pd.read_csv(self.filename)

    def __upload_new_item__(self, item: entities.Item):
        if config.upload_enabled:
            new_item = item.write(summary="New item imported from OpenAlex")
            print(f"Added new item {self.entity_url(new_item.id)}")
        else:
            print("skipped upload")

    def entity_url(self, qid):
        return f"{wbi_config.config['WIKIBASE_URL']}/wiki/{qid}"

    def start(self):
        self.__read_csv__()
        self.__check_and_extract_doi_column__()
        self.__process_dois__()

    class Config:
        arbitrary_types_allowed = True
