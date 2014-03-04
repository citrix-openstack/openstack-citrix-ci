import unittest

from osci import db


class TestDB(unittest.TestCase):
    def test_database_initialisation(self):
        database = db.DB("sqlite://")
        database.create_database_and_schema()

        # Check that the table is created
        self.assertEquals([], database.query("SELECT * FROM test"))

    def test_execute_an_insert(self):
        database = db.DB("sqlite://")

        database.execute("CREATE TABLE A (col VARCHAR)")
        database.execute("INSERT INTO A VALUES (12)")

        self.assertEquals([("12",)], database.query("SELECT * FROM A"))

