# import json
from unittest import TestCase

from pydantic import ValidationError

from openalexbot import OpenAlexBot


# from openalexapi import Work
# from wikibaseintegrator import WikibaseIntegrator


class TestOpenAlexBot(TestCase):
    def test_read_csv_no_doi_column_upper(self):
        oab = OpenAlexBot(email="test@example.com", filename="test_data/test_doi_uppercase.csv")
        oab.__read_csv__()
        oab.__drop_empty_values__()
        with self.assertRaises(ValueError):
            oab.__unquote_dois__()

    def test_read_csv_no_doi_column_lower(self):
        oab = OpenAlexBot(email="test@example.com", filename="test_data/test_doi_lowercase.csv")
        oab.__read_csv__()
        oab.__drop_empty_values__()
        oab.__unquote_dois__()
        oab.__check_and_extract_from_doi_series__()
        if len(oab.dois) != 1:
            self.fail()

    def test_found_using_cirrussearch_true(self):
        oab = OpenAlexBot(email="test@example.com", filename="test_data/test_doi_lowercase.csv")
        result = oab.__found_using_cirrussearch__(doi="10.7717/peerj.4375")
        if not result:
            self.fail()

    def test_found_using_cirrussearch_false(self):
        oab = OpenAlexBot(email="test@example.com", filename="test_data/test_doi_lowercase.csv")
        result = oab.__found_using_cirrussearch__(doi="xxx10.7717/peerj.4375xxx")
        if result:
            self.fail()

    def test_import_without_email(self):
        with self.assertRaises(ValidationError):
            oa = OpenAlexBot(filename="test_data/10_dois.csv")

    def test_import_with_invalid_email(self):
        with self.assertRaises(ValidationError):
            oa = OpenAlexBot(email=1, filename="test_data/10_dois.csv")


    def test_import_with_valid_email(self):
        oa = OpenAlexBot(email="test@example.com", filename="test_data/10_dois.csv")

        # oa.start()
#     def test__prepare_new_item__(self):
#         oab = OpenAlexBot(filename="test_data/test.csv")
#         test_json = json.loads("""
#
# {
#
#     "id": "https://openalex.org/C2777127463",
#     "wikidata": "https://www.wikidata.org/wiki/Q10862618",
#     "display_name": "Saddle",
#     "level": 2,
#     "description": "region surrounding the highest point of the lowest point on the line tracing the drainage divide (the col) connecting the peaks",
#     "works_count": 5019,
#     "cited_by_count": 59405,
#     "ids": {
#         "openalex": "https://openalex.org/C2777127463",
#         "wikidata": "https://www.wikidata.org/wiki/Q10862618",
#         "wikipedia": "https://en.wikipedia.org/wiki/Saddle%20%28landform%29",
#         "mag": 2777127463
#     },
#     "image_url": "https://upload.wikimedia.org/wikipedia/commons/e/ef/Bergsattel.jpg",
#     "image_thumbnail_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ef/Bergsattel.jpg/100px-Bergsattel.jpg",
#     "international": {
#         "display_name": {
#             "an": "cuello",
#             "ary": "تيزي",
#             "ast": "collada",
#             "be-tarask": "седлавіна",
#             "bg": "седловина",
#             "ca": "collada",
#             "cs": "horské sedlo",
#             "de": "Bergsattel",
#             "en": "saddle",
#             "eo": "montselo",
#             "es": "collado de montaña",
#             "eu": "Lepo (geografia)",
#             "fr": "col de montagne",
#             "gl": "portela",
#             "it": "sella",
#             "ja": "鞍部",
#             "lb": "Col",
#             "lv": "sedliene",
#             "mk": "седло",
#             "nl": "zadel",
#             "pl": "przełęcz",
#             "ro": "Șa",
#             "rue": "Сѣдло (география)",
#             "sk": "horské sedlo",
#             "sl": "Sedlo (geografija)",
#             "sv": "sadelpass",
#             "uk": "сідловина",
#             "zh": "鞍部"
#         },
#         "description": {
#             "ast": "accidente xeográficu",
#             "ca": "part més baixa, i bastant plana, que es troba entre dos cims o dues elevacions del terreny",
#             "de": "zwischen zwei Bergen die tiefstgelegene Route zwischen beiden Erhebungen hindurch",
#             "en": "region surrounding the highest point of the lowest point on the line tracing the drainage divide (the col) connecting the peaks",
#             "es": "punto más bajo de una línea de cumbres comprendido entre dos elevaciones",
#             "fr": "point le plus bas sur la ligne de crête le moins haut entre deux versants de montagne",
#             "gl": "punto máis baixo dunha liña de cumes comprendido entre dúas elevacións",
#             "zh": "一种地形"
#         }
#     },
#     "ancestors": [
#         {
#             "id": "https://openalex.org/C126255220",
#             "wikidata": "https://www.wikidata.org/wiki/Q141495",
#             "display_name": "Mathematical optimization",
#             "level": 1
#         },
#         {
#             "id": "https://openalex.org/C78519656",
#             "wikidata": "https://www.wikidata.org/wiki/Q101333",
#             "display_name": "Mechanical engineering",
#             "level": 1
#         },
#         {
#             "id": "https://openalex.org/C66938386",
#             "wikidata": "https://www.wikidata.org/wiki/Q633538",
#             "display_name": "Structural engineering",
#             "level": 1
#         },
#         {
#             "id": "https://openalex.org/C127413603",
#             "wikidata": "https://www.wikidata.org/wiki/Q11023",
#             "display_name": "Engineering",
#             "level": 0
#         },
#         {
#             "id": "https://openalex.org/C33923547",
#             "wikidata": "https://www.wikidata.org/wiki/Q395",
#             "display_name": "Mathematics",
#             "level": 0
#         }
#     ],
#     "related_concepts": [
#         {
#             "id": "https://openalex.org/C186633575",
#             "wikidata": null,
#             "display_name": "Maxima and minima",
#             "level": 2,
#             "score": 1.7713
#         },
#         {
#             "id": "https://openalex.org/C50128577",
#             "wikidata": null,
#             "display_name": "Mountain pass",
#             "level": 2,
#             "score": 1.71707
#         },
#         {
#             "id": "https://openalex.org/C2681867",
#             "wikidata": null,
#             "display_name": "Saddle point",
#             "level": 2,
#             "score": 1.40614
#         },
#         {
#             "id": "https://openalex.org/C2778848561",
#             "wikidata": null,
#             "display_name": "Summit",
#             "level": 2,
#             "score": 0.85786
#         }
#     ],
#     "counts_by_year": [
#         {
#             "year": 2022,
#             "works_count": 9,
#             "cited_by_count": 387
#         },
#         {
#             "year": 2021,
#             "works_count": 192,
#             "cited_by_count": 6670
#         },
#         {
#             "year": 2020,
#             "works_count": 201,
#             "cited_by_count": 5797
#         },
#         {
#             "year": 2019,
#             "works_count": 227,
#             "cited_by_count": 4881
#         },
#         {
#             "year": 2018,
#             "works_count": 182,
#             "cited_by_count": 4312
#         },
#         {
#             "year": 2017,
#             "works_count": 212,
#             "cited_by_count": 3837
#         },
#         {
#             "year": 2016,
#             "works_count": 198,
#             "cited_by_count": 3456
#         },
#         {
#             "year": 2015,
#             "works_count": 196,
#             "cited_by_count": 3313
#         },
#         {
#             "year": 2014,
#             "works_count": 202,
#             "cited_by_count": 2993
#         },
#         {
#             "year": 2013,
#             "works_count": 174,
#             "cited_by_count": 2513
#         },
#         {
#             "year": 2012,
#             "works_count": 172,
#             "cited_by_count": 2124
#         }
#     ],
#     "works_api_url": "https://api.openalex.org/works?filter=concepts.id:C2777127463",
#     "updated_date": "2022-01-30",
#     "created_date": "2018-01-05"
#
# }
# """)
#         work = Work(**test_json)
#         wbi = WikibaseIntegrator()
#         item = oab.__prepare_new_item__(query_string="10.7717/peerj.4375", work=work, wbi=wbi)
#         print(item.get_json())
