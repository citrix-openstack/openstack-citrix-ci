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
        q = job_queue.JobQueue(database="database", nodepool="nodepool")

        self.assertEquals("database", q.db)
        self.assertEquals("nodepool", q.nodepool)

    def test_add_test(self):
        database = db.DB('sqlite://')
        database.create_schema()

        q = job_queue.JobQueue(database=database, nodepool=None)
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        j, = job.Job.getAllWhere(database)
        self.assertTrue(j.queued)

    def test_add_test_if_job_already_exists(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.JobQueue(database=database, nodepool=nodepool)
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        with database.get_session() as session:
            j, = session.query(job.Job).all()
            j.node_id = 666

        nodepool.node_ids.append(666)

        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        j, = job.Job.getAllWhere(database)
        self.assertTrue(j.queued)
        self.assertEquals([], nodepool.node_ids)

    def test_get_queued_items_non_empty(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.JobQueue(database=database, nodepool=nodepool)
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        self.assertEquals(1, len(q.get_queued_enabled_jobs()))

    def test_get_queued_items_non_empty_disabled(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.JobQueue(database=database, nodepool=nodepool)
        q.jobs_enabled = False
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        self.assertEquals(0, len(q.get_queued_enabled_jobs()))

    def test_get_queued_items_empty(self):
        database = db.DB('sqlite://')
        database.create_schema()
        nodepool = FakeNodePool()

        q = job_queue.JobQueue(database=database, nodepool=nodepool)

        self.assertEquals(0, len(q.get_queued_enabled_jobs()))
