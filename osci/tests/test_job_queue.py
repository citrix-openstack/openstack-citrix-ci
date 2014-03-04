import unittest
import logging

from osci import db
from osci import job_queue
from osci import job


class TestInit(unittest.TestCase):
    def test_nodepool_can_be_injected(self):
        q = job_queue.TestQueue(database="database", nodepool="nodepool")

        self.assertEquals("database", q.db)
        self.assertEquals("nodepool", q.nodepool)

    def test_add_test(self):
        database = db.DB('sqlite://')
        database.create_schema()

        logging.getLogger('sqlalchemy').setLevel(logging.DEBUG)

        q = job_queue.TestQueue(database=database, nodepool=None)
        q.addTest('refs/changes/61/65261/7', 'project', 'commit')

        test, = job.Test.getAllWhere(database)
        self.assertTrue(test.queued)
