import logging

import pandas as pd
from openalexapi import OpenAlex
from pydantic import BaseModel
from rich import print
from wikibaseintegrator import WikibaseIntegrator, wbi_config
from wikibaseintegrator.models import LanguageValue
from wikibaseintegrator.wbi_helpers import search_entities

import config

logging.basicConfig(level=config.loglevel)
logger = logging.getLogger(__name__)


class OpenAlexBot(BaseModel):
    """This class takes a CSV as input
    The column "DOI" is then processed row by row"""
    filename: str

    def start(self):
        df = pd.read_csv(self.filename)
        dois = df["DOI"].values
        dois = set(dois)
        processed_dois = set()
        oa = OpenAlex()
        wbi_config.config["USER_AGENT_DEFAULT"] = config.user_agent
        wbi = WikibaseIntegrator(login=None)
        for doi in dois:
            if doi not in processed_dois:
                work = oa.get_single_work(f"doi:{doi}")
                print(work.dict())
                result = search_entities(doi)
                logger.info(f"result from CirrusSearch: {result}")
                processed_dois.add(doi)
                # exit()
                if len(result) == 0:
                    # TODO language of display name using langdetect and set dynamically
                    item = wbi.item.new(labels=LanguageValue(language="en", value=work.display_name),
                                        descriptions=LanguageValue(
                                            language="en",
                                            value=f"scientific article from {work.publication_year}"))
                    # TODO convert data from OpenAlex work to claims
                    #item.add_claims(None)
                    item.write(summary="New item imported from OpenAlex")