import unittest

from osci import db


class TestDB(unittest.TestCase):
    def test_database_initialisation(self):
        database = db.DB("sqlite://")
        database.create_schema()

        # Check that the table is created
        with database.get_session() as session:
            self.assertEquals(
                [], session.execute("SELECT * FROM test").fetchall())

    def test_execute_an_insert(self):
        database = db.DB("sqlite://")

        with database.get_session() as session:
            session.execute("CREATE TABLE A (col VARCHAR)")
            session.execute("INSERT INTO A VALUES (12)")

            self.assertEquals(
                [("12",)], session.execute("SELECT * FROM A").fetchall())

    def test_mapping_includes_constraint(self):
        database = db.DB("sqlite://")
        database.create_schema()

        with database.get_session() as session:
            session.execute(
                "INSERT INTO test (project_name, change_num) VALUES"
                "('proj', 'chang')")

            with self.assertRaises(db.IntegrityError):
                session.execute(
                    "INSERT INTO test (project_name, change_num) VALUES"
                    "('proj', 'chang')")
