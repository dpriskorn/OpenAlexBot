import logging
from datetime import datetime, timezone
from typing import Set, Optional, List, Union
from urllib.parse import unquote

import langdetect as langdetect  # type: ignore
import pandas as pd  # type: ignore
from openalexapi import OpenAlex, Work
from pandas import DataFrame, Series  # type: ignore
from purl import URL  # type: ignore
from pydantic import BaseModel, EmailStr
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
    The column "query_string" is then processed row by row
    It supports both "naked" dois and with prefix.
    """
    dataframe: Optional[DataFrame]
    dois: Optional[Set[str]]
    email: EmailStr
    filename: str
    doi_series: Optional[Series]

    def __drop_empty_values__(self):
        self.dataframe = self.dataframe.dropna()
        if config.loglevel == logging.DEBUG:
            self.dataframe.info()

    def __unquote_dois__(self):
        if "doi" in self.dataframe.columns:
            logger.debug("Found 'doi' column")
            self.doi_series = self.dataframe['doi'].transform(lambda x: unquote(x))
            if config.loglevel == logging.DEBUG:
                self.doi_series.info()
                # self.doi_series.sample(5)
        else:
            raise ValueError(f"No 'doi' column found in {self.filename}")

    def __check_and_extract_from_doi_series__(self):
        if self.doi_series is None:
            raise ValueError(f"doi_series was None")
        if len(self.doi_series) > 0:
            dois: List[str] = self.dataframe["doi"].values
            self.dois = set(dois)
        else:
            raise ValueError("No rows in the doi column")

    def __found_using_cirrussearch__(self, doi: str) -> bool:
        if doi is None:
            raise ValueError("Did not get what we need")
        result = self.__call_cirrussearch_api__(query_string=doi)
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

    def __call_cirrussearch_api__(self, query_string: str) -> dict:
        """This calls the cirrussearch API.
        :param query_string can be a doi or use special filters like "haswbstatement:P31=QID"
        """
        params = dict(
            # format="json",
            action="query",
            list="search",
            # srprop=None,
            srlimit=1,
            srsearch=query_string
        )
        return mediawiki_api_call_helper(
            data=params,
            allow_anonymous=True
        )

    def __get_first_qid_from_cirrussearch__(self, query_string: str) -> Union[str, bool]:
        if query_string is None:
            raise ValueError("Did not get what we need")
        result = self.__call_cirrussearch_api__(query_string=query_string)
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

    def __prepare_authors__(self, work: Work) -> Optional[List[Claim]]:
        """
        This method prepares the author claims.
        Unfortunately OpenAlex neither has numerical positions on authors
        nor first and last names separation.

        Neither Crossref nor OpenAlex has numerical ordinals.
        We copy the current praxis at WD and assign numerals trusting the order of OpenAlex
        """
        if work is None:
            raise ValueError("did not get what we need")
        logger.info("Preparing author claims")
        authors = []
        logger.info(f"Found {len(work.authorships)} authorships to process")
        ordinal = 1
        for authorship in work.authorships:
            if authorship.author.orcid is not None:
                id = authorship.author.id
                name = authorship.author.display_name
                orcid = authorship.author.orcid_id
                # The positions are one of (first, middle, last)
                position = authorship.author_position
                # We ignore authorship.institutions for now
                logger.info(f"Found author with name '{name}', position {position}, orcid {orcid} and id '{id}'")
                series_ordinal = datatypes.String(
                    prop_nr=Property.SERIES_ORDINAL.value,
                    value=str(ordinal)
                )
                qid = self.__get_first_qid_from_cirrussearch__(query_string=orcid)
                if qid:
                    author = datatypes.Item(
                        prop_nr=Property.AUTHOR.value,
                        value=qid,
                        qualifiers=[series_ordinal],
                        references=[self.__prepare_reference_claim__(id=id, work=work)]
                    )
                else:
                    author = datatypes.String(
                        prop_nr=Property.AUTHOR_NAME_STRING.value,
                        value=name,
                        qualifiers=[series_ordinal],
                        references=[self.__prepare_reference_claim__(id=id, work=work)]
                    )
                authors.append(author)
                ordinal += 1
        return authors

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

    def __prepare_instance_of__(self, work: Work, reference: List[Claim]):
        if (work, reference) is None:
            raise ValueError("did not get what we need")
        type_qid = WorkTypeToQid(work=work)
        type_qid = type_qid.get_qid()
        if type_qid is not None:
            return datatypes.Item(
                prop_nr=Property.INSTANCE_OF.value,
                value=type_qid,
                references=[reference]
            )
        else:
            raise ValueError(f"type_qid was None")

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
        # TODO convert redacted from OpenAlex work to claim
        # TODO convert oa status from OpenAlex work to claim?
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
        item.add_claims(
            self.__prepare_single_value_claims__(doi=doi, work=work, reference=reference),
        )
        if config.loglevel == logging.DEBUG:
            logger.debug("Printing the item json")
            print(item.get_json())
        return item

    def __prepare_published_in__(self, work: Work, reference: List[Claim]):
        """This method performs entity linking between host_venue in OpenAlex and Wikidata
        host_venues are often journals
        """
        if (work, reference) is None:
            raise ValueError("did not get what we need")
        logger.info("Getting Host Venue details from OA")
        # Lookup using the ISSN-L e.g. https://api.openalex.org/works/doi:10.1016/j.eurpsy.2017.01.1921
        # has 0924-9338
        issn_l = work.host_venue.issn_l
        if issn_l is None:
            raise ValueError(f"issn_l of {work.id} was None")
        result = self.__get_first_qid_from_cirrussearch__(f"haswbstatement:P7363={issn_l}")
        if result is not None:
            published_in = datatypes.Item(
                prop_nr=Property.PUBLISHED_IN.value,
                value=result,
                references=[reference]
            )
            return published_in
        else:
            raise ValueError(f"Venue with ISSN-L {issn_l} not found in Wikidata")

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

    def __prepare_single_value_claims__(self, doi: str, work: Work, reference: List[Claim]):
        if (work, doi, reference) is None:
            raise ValueError("did not get what we need")
        logger.info("Preparing other claims")
        doi = datatypes.ExternalID(
            prop_nr=Property.DOI.value,
            value=doi.lower(),  # This is a community norm in Wikidata
            references=[reference]
        )
        instance_of = self.__prepare_instance_of__(work=work, reference=reference)
        publication_date = datatypes.Time(
            prop_nr=Property.PUBLICATION_DATE.value,
            time=datetime.strptime(work.publication_date, "%Y-%m-%d").strftime("+%Y-%m-%dT%H:%M:%SZ"),
            references=[reference]
        )
        published_in = self.__prepare_published_in__(work=work, reference=reference)
        title = datatypes.MonolingualText(
            prop_nr=Property.TITLE.value,
            text=work.title,
            language="en",
            references=[reference]
        )
        # DISABLED because OpenAlex does not have this information currently
        # language_of_work = datatypes.Item(
        #     prop_nr=Property.LANGUAGE_OF_WORK.value,
        #     value=,
        #     references=[]
        # )
        if work.biblio.issue is not None:
            issue = datatypes.String(
                prop_nr=Property.ISSUE.value,
                value=work.biblio.issue,
                references=[reference]
            )
        else:
            issue = None
        if work.biblio.volume is not None:
            volume = datatypes.String(
                prop_nr=Property.VOLUME.value,
                value=work.biblio.volume,
                references=[reference]
            )
        else:
            volume = None
        if work.biblio.first_page is not None and work.biblio.last_page is not None:
            pages = datatypes.String(
                prop_nr=Property.PAGES.value,
                value=f"{work.biblio.first_page}-{work.biblio.last_page}",
                references=[reference]
            )
        else:
            pages = None
        list_of_claims = []
        for claim in (
                doi,
                instance_of,
                issue,
                pages,
                publication_date,
                published_in,
                title,
                volume,
        ):
            if claim is not None:
                list_of_claims.append(claim)
        if len(list_of_claims) > 0:
            return list_of_claims
        else:
            return None

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
            logger.debug(f"Working on query_string: '{doi}'")
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
        if config.loglevel == logging.DEBUG:
            self.dataframe.info()

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
        self.__drop_empty_values__()
        self.__unquote_dois__()
        self.__check_and_extract_from_doi_series__()
        self.__process_dois__()

    class Config:
        arbitrary_types_allowed = True
