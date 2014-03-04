import unittest
import logging

from osci import db
from osci import job_queue
from osci import job


class FakeNodePool(object):
    def __init__(self):
        self.node_ids = []

    def deleteNode(self, node_id):
        assert node_id in self.node_ids, "node %s does not exist" % node_id
        self.node_ids = [id for id in self.node_ids if id != node_id]


class TestInit(unittest.TestCase):
    def test_nodepool_can_be_injected(self):
        q = job_queue.TestQueue(database="database", nodepool="nodepool")

        self.assertEquals("database", q.db)
        self.assertEquals("nodepool", q.nodepool)

    def test_add_test(self):
        database = db.DB('sqlite://')
        database.create_schema()

        q = job_queue.TestQueue(database=database, nodepool=None)
        q.addTest('refs/changes/61/65261/7', 'project', 'commit')

        test, = job.Test.getAllWhere(database)
        self.assertTrue(test.queued)

    def test_add_test_if_job_already_exists(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.TestQueue(database=database, nodepool=nodepool)
        q.addTest('refs/changes/61/65261/7', 'project', 'commit')

        session = database.get_session()
        test, = session.query(job.Test).all()
        test.node_id = 666
        nodepool.node_ids.append(666)
        session.commit()

        q.addTest('refs/changes/61/65261/7', 'project', 'commit')

        test, = job.Test.getAllWhere(database)
        self.assertTrue(test.queued)
        self.assertEquals([], nodepool.node_ids)

    def test_get_queued_items_non_empty(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.TestQueue(database=database, nodepool=nodepool)
        q.addTest('refs/changes/61/65261/7', 'project', 'commit')

        self.assertEquals(1, len(q.get_queued_enabled_tests()))

    def test_get_queued_items_non_empty_disabled(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.TestQueue(database=database, nodepool=nodepool)
        q.tests_enabled = False
        q.addTest('refs/changes/61/65261/7', 'project', 'commit')

        self.assertEquals(0, len(q.get_queued_enabled_tests()))

    def test_get_queued_items_empty(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.TestQueue(database=database, nodepool=nodepool)

        self.assertEquals(0, len(q.get_queued_enabled_tests()))
