import logging
from typing import Set, Optional

import pandas as pd
from openalexapi import OpenAlex, Work
from pydantic import BaseModel
from rich import print
from wikibaseintegrator import WikibaseIntegrator, wbi_config, wbi_login
from wikibaseintegrator.models import LanguageValue
from wikibaseintegrator.wbi_helpers import search_entities

import config

logging.basicConfig(level=config.loglevel)
logger = logging.getLogger(__name__)


class OpenAlexBot(BaseModel):
    """This class takes a CSV as input
    The column "DOI" is then processed row by row"""
    filename: str
    dois: Optional[Set]

    def __import_new_item__(self, work: Work, wbi: WikibaseIntegrator):
        # TODO language of display name using langdetect and set dynamically
        item = wbi.item.new(labels=LanguageValue(language="en", value=work.display_name),
                            descriptions=LanguageValue(
                                language="en",
                                value=f"scientific article from {work.publication_year}"))

        # TODO convert data from OpenAlex work to claims
        # item.add_claims(None)
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
                    print(work.dict())
                    result = search_entities(doi)
                    logger.info(f"result from CirrusSearch: {result}")
                    # exit()
                    if len(result) == 0:
                        self.__import_new_item__(work=work, wbi=wbi)
                    processed_dois.add(doi)
        else:
            print("No DOIs found in the CSV")

    def entity_url(self, qid):
        return f"{wbi_config.config['WIKIBASE_URL']}wiki/{qid}"

    def start(self):
        self.__read_csv__()
        self.__process_dois__()
