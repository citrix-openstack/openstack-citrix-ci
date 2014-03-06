import unittest
import logging
import mock
import Queue

from osci import db
from osci import job_queue
from osci import job
from osci import filesystem_services
from osci import utils
from osci import swift_upload
from osci import constants


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

        j1,j2, = job.Job.getAllWhere(q.db)
        if j1.state == constants.OBSOLETE:
            old_j = j1
            new_j = j2
        else:
            old_j = j2
            new_j = j1
        self.assertTrue(new_j.queued)
        self.assertEquals(new_j.state, constants.QUEUED)
        self.assertEquals(old_j.state, constants.OBSOLETE)
        self.assertEquals(old_j.node_id, 666)

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

    def test_delete_thread_obsolete(self):
        q = self._make_queue()
        q.addJob('refs/changes/61/65261/7', 'project', 'commit1')
        q.addJob('refs/changes/61/65262/7', 'project', 'commit2')
        q.addJob('refs/changes/61/65263/7', 'project', 'commit3')
        with q.db.get_session() as session:
            jobs = session.query(job.Job).all()
            jobs[0].state = constants.OBSOLETE
            jobs[0].node_id = 0
            jobs[1].state = constants.RUNNING
            jobs[1].node_id = 1
            jobs[2].state = constants.OBSOLETE
            jobs[2].node_id = 2
        q.nodepool.node_ids.extend([1, 2])

        # Only node 2 should be deleted
        dnt = job_queue.DeleteNodeThread(q)
        dnt.add_missing_jobs()
        self.assertFalse(dnt.deleteNodeQueue.empty())
        j = dnt.deleteNodeQueue.get()
        self.assertTrue(dnt.deleteNodeQueue.empty())
        self.assertEquals(2, j.node_id)


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

        t = job.Job()
        t.node_id = 12
        t.retrieveResults = mock.Mock()
        t.retrieveResults.return_value = "jobresult"
        t.change_num = 98
        t.change_ref = 'refs/changes/1/2/3'
        t.id = 33

        q.uploadResults(t)

        self.assertEquals(
            {}, q.filesystem.contents, msg="Filesystem not cleaned up")
        self.assertEquals(
            [12], q.nodepool.node_ids, msg="Node must still exist")
        self.assertEquals(
            constants.COLLECTED, t.state, msg="Node must be collected")
        q.uploader.upload.assert_called_once_with(
            "RANDOMPATH-98", "1/2/3"
        )


class FakeQueue(object):
    def __init__(self):
        self.items = []

    def put(self, stuff):
        self.items.append(stuff)

class TestProcessResults(unittest.TestCase, QueueHelpers):
    def test_empty_run(self):
        q = self._make_queue()
        q.collectResultsThread = mock.Mock(spec=job_queue.CollectResultsThread)

        q.processResults()

    def test_running_jobs_collected(self):
        q = self._make_queue()
        with q.db.get_session() as session:
            j = job.Job()
            session.add(j)
            j.state = constants.RUNNING
        q.collectResultsThread = mock.Mock(spec=job_queue.CollectResultsThread)
        collect_q = q.collectResultsThread.collectJobs = FakeQueue()

        q.processResults()

        self.assertEquals(
            [j], collect_q.items
        )

        with q.db.get_session() as session:
            j, = session.query(job.Job).all()

        self.assertEquals(constants.COLLECTING, j.state)
