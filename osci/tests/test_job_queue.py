import unittest
import logging
import mock

from osci import db
from osci import job_queue
from osci import job
from osci import filesystem_services
from osci import utils
from osci import swift_upload


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
            filesystem=filesystem_services.FakeFilesystem(),
            uploader=None,
            executor=None)


class TestInit(unittest.TestCase, QueueHelpers):
    def test_nodepool_can_be_injected(self):
        q = job_queue.JobQueue(
            database="database",
            nodepool="nodepool",
            filesystem="filesystem",
            uploader="uploader",
            executor="executor")

        self.assertEquals("database", q.db)
        self.assertEquals("nodepool", q.nodepool)
        self.assertEquals("filesystem", q.filesystem)
        self.assertEquals("uploader", q.uploader)
        self.assertEquals("executor", q.executor)

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

    def test_job_has_results(self):
        q = self._make_queue()
        q.executor = mock.Mock(spec=utils.execute_command)
        q.executor.return_value = ("code", "fail_stdout", "fail_stderr")
        q.uploader = mock.Mock(spec=swift_upload.SwiftUploader)
        q.nodepool.node_ids = [12]

        t = mock.Mock(spec=job.Job)
        t.node_id = 12
        t.retrieveResults.return_value = "jobresult"
        t.change_num = 98
        t.change_ref = 'refs/changes/1/2/3'
        t.id = 33

        q.uploadResults(t)

        self.assertEquals(
            {}, q.filesystem.contents, msg="Filesystem cleaned up")
        self.assertEquals(
            [], q.nodepool.node_ids, msg="Node deleted")
        q.uploader.upload.assert_called_once_with(
            "RANDOMPATH-98", "1/2/3"
        )
