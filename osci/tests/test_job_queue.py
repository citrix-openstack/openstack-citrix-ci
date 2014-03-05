import unittest
import logging
import mock

from osci import db
from osci import job_queue
from osci import job
from osci import filesystem_services


class FakeNodePool(object):
    def __init__(self):
        self.node_ids = []

    def deleteNode(self, node_id):
        assert node_id in self.node_ids, "node %s does not exist" % node_id
        self.node_ids = [id for id in self.node_ids if id != node_id]


class QueueHelpers(object):
    def _make_queue(self):
        database = db.DB('sqlite://')
        database.create_schema()

        return job_queue.JobQueue(
            database=database,
            nodepool=FakeNodePool(),
            filesystem=filesystem_services.FakeFilesystem())


class TestInit(unittest.TestCase, QueueHelpers):
    def test_nodepool_can_be_injected(self):
        q = job_queue.JobQueue(
            database="database", nodepool="nodepool", filesystem=None)

        self.assertEquals("database", q.db)
        self.assertEquals("nodepool", q.nodepool)

    def test_add_test(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        test, = job.Job.getAllWhere(q.db)
        self.assertTrue(test.queued)

    def test_add_test_if_job_already_exists(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')
        with q.db.get_session() as session:
            j, = session.query(job.Job).all()
            j.node_id = 666
        q.nodepool.node_ids.append(666)

        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        j, = job.Job.getAllWhere(q.db)
        self.assertTrue(j.queued)
        self.assertEquals([], q.nodepool.node_ids)

    def test_get_queued_items_non_empty(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit')

        self.assertEquals(1, len(q.get_queued_enabled_jobs()))

    def test_get_queued_items_non_empty_disabled(self):
        q = self._make_queue()

        q.addJob('refs/changes/61/65261/7', 'project', 'commit')
        q.jobs_enabled = False
        self.assertEquals(0, len(q.get_queued_enabled_jobs()))

    def test_get_queued_items_empty(self):
        q = self._make_queue()
        self.assertEquals(0, len(q.get_queued_enabled_jobs()))


class TestUploadResults(unittest.TestCase, QueueHelpers):
    def test_job_has_no_results(self):
        q = self._make_queue()

        t = mock.Mock(spec=job.Job)
        t.retrieveResults.return_value = False

        q.uploadResults(t)

        self.assertEquals({}, q.filesystem.contents)