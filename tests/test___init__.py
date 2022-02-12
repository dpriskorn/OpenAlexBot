from unittest import TestCase

from openalexbot import OpenAlexBot


class TestOpenAlexBot(TestCase):
    def test_start(self):
        oab = OpenAlexBot(filename="test.csv")
        oab.start()
        #self.fail()
