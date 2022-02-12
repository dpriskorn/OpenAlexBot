import logging
from datetime import datetime, timezone
from typing import Set, Optional

import pandas as pd
from openalexapi import OpenAlex, Work
from pydantic import BaseModel
from rich import print
from wikibaseintegrator import WikibaseIntegrator, wbi_config, wbi_login
from wikibaseintegrator import datatypes
from wikibaseintegrator.wbi_helpers import mediawiki_api_call_helper

import config
from openalexbot.enums import StatedIn, Property

logging.basicConfig(level=config.loglevel)
logger = logging.getLogger(__name__)


class OpenAlexBot(BaseModel):
    """This class takes a CSV as input
    The column "DOI" is then processed row by row"""
    filename: str
    dois: Optional[Set]

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

    def __import_new_item__(self, doi: str, work: Work, wbi: WikibaseIntegrator):
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
            value=doi,
            references=[reference]
        )
        instance_of = datatypes.Item(
            prop_nr=Property.INSTANCE_OF.value,
            # TODO make this dynamic according to work.type
            value="Q13442814"  # hardcoded scholarly article for now
        )
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
            print("debug exit before write")
            exit()
        new_item = item.write(summary="New item imported from OpenAlex")
        print(f"Added new item {self.entity_url(new_item.id)}")

    def __read_csv__(self):
        df = pd.read_csv(self.filename)
        dois = df["DOI"].values
        self.dois = set(dois)

    def __process_dois__(self):
        if len(self.dois) > 0:
            oa = OpenAlex()
            wbi_config.config["USER_AGENT_DEFAULT"] = config.user_agent
            wbi = WikibaseIntegrator(login=wbi_login.Login(
                user=config.bot_username,
                password=config.password
            ))
            processed_dois = set()
            for doi in self.dois:
                if doi not in processed_dois:
                    work = oa.get_single_work(f"doi:{doi}")
                    #print(work.dict())
                    if not self.__found_using_cirrussearch__(doi):
                        self.__import_new_item__(doi=doi, work=work, wbi=wbi)
                    else:
                        print(f"DOI: '{doi}' is already in Wikidata, skipping")
                processed_dois.add(doi)
        else:
            print("No DOIs found in the CSV")

    def entity_url(self, qid):
        return f"{wbi_config.config['WIKIBASE_URL']}/wiki/{qid}"

    def start(self):
        self.__read_csv__()
        self.__process_dois__()
