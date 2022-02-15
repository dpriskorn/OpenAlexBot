import logging
from datetime import datetime, timezone
from typing import Set, Optional, List, Union

import langdetect as langdetect
import pandas as pd
from openalexapi import OpenAlex, Work
from pandas import DataFrame
from purl import URL
from pydantic import BaseModel
from rich import print
from wikibaseintegrator import WikibaseIntegrator, wbi_config, wbi_login, entities
from wikibaseintegrator import datatypes
from wikibaseintegrator.models import Claim
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
    email: Optional[str]
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
        if doi is None:
            raise ValueError("Did not get what we need")
        result = self.__call_cirrussearch_api__(doi=doi)
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

    def __call_cirrussearch_api__(self, doi: str) -> dict:
        params = dict(
            # format="json",
            action="query",
            list="search",
            # srprop=None,
            srlimit=1,
            srsearch=doi
        )
        return mediawiki_api_call_helper(
            data=params,
            allow_anonymous=True
        )

    def __get_first_qid_from_cirrussearch__(self, doi: str) -> Union[str, bool]:
        if doi is None:
            raise ValueError("Did not get what we need")
        result = self.__call_cirrussearch_api__(doi=doi)
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
        if (doi, work, wbi) is None:
            raise ValueError("Did not get what we need")
        self.__upload_new_item__(item=self.__prepare_new_item__(doi=doi, work=work, wbi=wbi))

    def __prepare_cites_works__(self, work: Work, reference: List[Claim]):
        if (work, reference) is None:
            raise ValueError("did not get what we need")
        logger.info("Preparing cites works claims")
        oa = OpenAlex(email=self.email)
        cites_works: List[datatypes.Item] = []
        for referenced_work_url in work.referenced_works:
            referenced_work = oa.get_single_work(referenced_work_url)
            # print(referenced_work.dict())
            doi = referenced_work.ids.doi_id
            if doi is not None:
                if self.__found_using_cirrussearch__(doi):
                    qid = self.__get_first_qid_from_cirrussearch__(doi)
                    logger.info(f"qid found for this reference: {qid}")
                    # exit()
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
        # if config.loglevel == logging.DEBUG:
        #     print(cites_works)
        return cites_works

    @staticmethod
    def __prepare_reference_claim__(id: str = None, work: Work = None) -> List[Claim]:
        if work is None:
            raise ValueError("did not get what we need")
        logger.info("Preparing reference claim")
        # Prepare reference
        if id is not None:
            id_without_prefix = URL(id).path_segment(0)
            logger.info(f"Using OpenAlex id: {id_without_prefix} extracted from {id}")
            openalex_id = datatypes.ExternalID(
                prop_nr=Property.OPENALEX_ID.value,
                value=id_without_prefix
            )
        else:
            # Fallback to the work id as id
            logger.info(f"Using OpenAlex id: {work.id_without_prefix}")
            openalex_id = datatypes.ExternalID(
                prop_nr=Property.OPENALEX_ID.value,
                value=work.id_without_prefix
            )
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
        claims = []
        for claim in (retrieved_date, stated_in, openalex_id):
            if claim is not None:
                claims.append(claim)
        return claims

    def __prepare_authors__(self, work: Work) -> Optional[List[Claim]]:
        """This method prepares the author claims.
        Unfortunately OpenAlex neither has numerical positions on authors
        nor first and last names separation."""
        if work is None:
            raise ValueError("did not get what we need")
        logger.info("Preparing author claims")
        authors = []
        logger.info(f"Found {len(work.authorships)} authorships to process")
        for authorship in work.authorships:
            if authorship.author.orcid is not None:
                id = authorship.author.id
                name = authorship.author.display_name
                # The positions are one of (first, middle, last)
                position = authorship.author_position
                logger.info(f"Found author with name '{name}', position {position} and id '{id}'")
                # We ignore authorship.institutions for now
                series_ordinal = datatypes.String(
                    prop_nr=Property.SERIES_ORDINAL.value,
                    value=position
                )
                author = datatypes.String(
                    prop_nr=Property.AUTHOR_NAME_STRING.value,
                    value=name,
                    qualifiers=[series_ordinal],
                    references=[self.__prepare_reference_claim__(id=id, work=work)]
                )
                authors.append(author)
        return authors

    def __prepare_subjects__(self, work: Work) -> Optional[List[Claim]]:
        """This method prepares the concept aka main subject claims."""
        if work is None:
            raise ValueError("did not get what we need")
        logger.info("Preparing subject claims")
        subjects = []
        for concept in work.concepts:
            if concept.wikidata_id is not None:
                qid = concept.wikidata_id
                label = concept.display_name
                id = concept.id
                logger.info(f"Found concept with name '{label}' and wikidata id '{qid}'")
                subject = datatypes.Item(
                    prop_nr=Property.MAIN_SUBJECT.value,
                    value=qid,
                    references=[self.__prepare_reference_claim__(id=id, work=work)]
                )
                subjects.append(subject)
        return subjects

    def __prepare_other_claims__(self, doi: str, work: Work, reference: List[Claim]):
        if (work, doi, reference) is None:
            raise ValueError("did not get what we need")
        logger.info("Preparing other claims")
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
        publication_date = datatypes.Time(
            prop_nr=Property.PUBLICATION_DATE.value,
            time=datetime.strptime(work.publication_date, "%Y-%m-%d").strftime("+%Y-%m-%dT%H:%M:%SZ")
        )
        # DISABLED because OpenAlex does not have this information currently
        # language_of_work = datatypes.Item(
        #     prop_nr=Property.LANGUAGE_OF_WORK.value,
        #     value=,
        #     references=[]
        # )
        self.__prepare_authors__(work=work)
        if work.biblio.issue is not None:
            issue = datatypes.String(
                prop_nr=Property.ISSUE.value,
                value=work.biblio.issue
            )
        else:
            issue = None
        list_of_claims = []
        for claim in (doi, instance_of, title, publication_date, issue):
            if claim is not None:
                list_of_claims.append(claim)
        if len(list_of_claims) > 0:
            return list_of_claims
        else:
            return None

    def __prepare_new_item__(
            self, doi: str, work: Work, wbi: WikibaseIntegrator
    ) -> entities.Item:
        """This method converts OpenAlex data into a new Wikidata item"""
        if (doi, work, wbi) is None:
            raise ValueError("Did not get what we need")
        # TODO language of display name using langdetect and set dynamically
        detected_language = langdetect.detect(work.display_name)
        logger.info(f"Detected language {detected_language} for '{work.display_name}'")
        item = wbi.item.new()
        item.labels.set(detected_language, work.display_name)
        item.descriptions.set("en", f"scientific article from {work.publication_year}")
        # Prepare claims
        # First prepare the reference needed in other claims
        reference = self.__prepare_reference_claim__(work=work)
        authors = self.__prepare_authors__(work=work)
        cites_works = self.__prepare_cites_works__(work=work, reference=reference)
        subjects = self.__prepare_subjects__(work=work)
        if len(subjects) > 0:
            item.add_claims(subjects)
        if len(authors) > 0:
            item.add_claims(authors)
        if len(cites_works) > 0:
            item.add_claims(cites_works)
        # TODO convert more data from OpenAlex work to claims
        item.add_claims(
            self.__prepare_other_claims__(doi=doi, work=work, reference=reference),
        )
        if config.loglevel == logging.DEBUG:
            logger.debug("Printing the item json")
            print(item.get_json())
        return item

    def __process_dois__(self):
        if self.email is None:
            raise ValueError("self.email was None")
        oa = OpenAlex(email=self.email)
        wbi_config.config["USER_AGENT_DEFAULT"] = config.user_agent
        if config.use_test_wikidata:
            wbi_config.config["WIKIBASE_URL"] = "http://test.wikidata.org"
        wbi = WikibaseIntegrator(login=wbi_login.Login(
            user=config.bot_username,
            password=config.password
        ), )
        processed_dois = set()
        for doi in self.dois:
            logger.debug(f"Working on doi: '{doi}'")
            doi = doi.replace("https://doi.org/", "")
            if "http" in doi:
                raise ValueError(f"http found in this DOI after "
                                 f"removing the prefix: {doi}")
            if doi not in processed_dois:
                work = oa.get_single_work(f"doi:{doi}")
                if work is not None:
                    logger.info(f"Found Work in OpenAlex with id {work.id}")
                    # print(work.dict())
                    if not self.__found_using_cirrussearch__(doi):
                        logger.info("Starting import")
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
        if item is None:
            raise ValueError("Did not get what we need")
        if config.upload_enabled:
            new_item = item.write(summary="New item imported from OpenAlex")
            print(f"Added new item {self.entity_url(new_item.id)}")
            if config.press_enter_to_continue:
                input("press enter to continue")
        else:
            print("skipped upload")

    @staticmethod
    def entity_url(qid):
        return f"{wbi_config.config['WIKIBASE_URL']}/wiki/{qid}"

    def start(self):
        self.__read_csv__()
        self.__check_and_extract_doi_column__()
        self.__process_dois__()

    class Config:
        arbitrary_types_allowed = True
